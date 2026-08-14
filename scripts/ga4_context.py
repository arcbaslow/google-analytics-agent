"""
Property-context extractor.

Reads the data streams on a GA4 property, pulls the web stream's
`defaultUri`, fetches the homepage (and robots.txt / sitemap.xml when
reachable), and infers:

  - framework and stack hints (Next.js, React, Vue, Svelte, plain HTML,
    Shopify, WooCommerce, Magento, WordPress, Webflow, Wix, Squarespace, ...)
  - SPA vs MPA
  - likely industry vertical (ecommerce, saas, media, lead-gen, finance,
    travel, education, nonprofit, other)
  - language, region, canonical host
  - rough catalogue size and page-type inventory from the sitemap

The result is stored under `~/.claude/ga4-context/<property-id>.json` so
every other agent can attach it to its findings.

CLI:
  python scripts/ga4_context.py --property <id> --analyze --json
  python scripts/ga4_context.py --property <id> --show --json
  python scripts/ga4_context.py --property <id> --refresh --json
  python scripts/ga4_context.py --url https://example.com --analyze --json
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CONTEXT_DIR = Path.home() / ".claude" / "ga4-context"
FETCH_TIMEOUT_SECONDS = 12
USER_AGENT = "google-analytics-agent/0.3 (+context-extractor)"
MAX_HTML_BYTES = 800_000  # ~800 KB cap on homepage download
MAX_SITEMAP_URLS = 200  # surface the first N urls for analysis


# ---------- Storage ----------


def _ensure_dir():
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def save_context(property_id: str, context: dict[str, Any]) -> Path:
    _ensure_dir()
    path = CONTEXT_DIR / f"{property_id}.json"
    path.write_text(json.dumps(context, indent=2, default=str), encoding="utf-8")
    return path


def load_context(property_id: str) -> dict[str, Any] | None:
    path = CONTEXT_DIR / f"{property_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_context(property_id: str) -> dict[str, Any]:
    path = CONTEXT_DIR / f"{property_id}.json"
    if not path.exists():
        return {"status": "absent", "property_id": property_id}
    path.unlink()
    return {"status": "deleted", "property_id": property_id}


# ---------- URL extraction ----------


def extract_property_urls(property_id: str) -> list[dict[str, Any]]:
    """Pull `defaultUri` from each web stream on the property.

    Returns a list of {stream_id, stream_name, default_uri, type} entries
    so the caller can pick (most properties have one web stream)."""
    from ga4_admin import list_data_streams

    streams = list_data_streams(property_id)
    out = []
    for s in streams:
        stream_type = s.get("type_") or s.get("type") or ""
        web = s.get("webStreamData") or s.get("web_stream_data") or {}
        default_uri = web.get("defaultUri") or web.get("default_uri")
        out.append(
            {
                "stream_id": s.get("name", "").split("/")[-1],
                "stream_name": s.get("displayName") or s.get("display_name"),
                "default_uri": default_uri,
                "type": stream_type,
                "raw": s,
            }
        )
    return out


# ---------- HTTP helpers ----------


class UnsafeFetchTarget(ValueError):
    """A URL that this module refuses to fetch."""


def _resolves_to_private(host: str) -> bool:
    """True if any address the host resolves to is not publicly routable.

    Resolution happens here rather than at the string level because
    `internal.example.com` can be a public name pointing at 10.0.0.5, and a
    metadata endpoint can be reached through a DNS name just as easily as
    through 169.254.169.254 directly.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable. Let the fetch fail normally rather than guessing.
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            continue
        if not ip.is_global or ip.is_link_local or ip.is_private or ip.is_loopback:
            return True
    return False


def assert_fetchable(url: str) -> None:
    """Reject anything that is not a public http(s) URL.

    This module fetches URLs that the audited site controls: the homepage is
    supplied by the operator, but `robots.txt` names its own `Sitemap:` target
    and we follow it. That makes the sitemap URL attacker-controlled input.

    Two things follow. The scheme has to be pinned, because urllib's default
    opener also handles `file://` and `ftp://`. And the host has to be
    publicly routable, because `http://169.254.169.254/...` is the cloud
    metadata endpoint on essentially every VPS provider, and the response
    would be written into the saved property context and read back into
    model context on the next audit.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeFetchTarget(f"refusing to fetch non-http(s) URL: {url!r}")
    if not parsed.hostname:
        raise UnsafeFetchTarget(f"refusing to fetch URL with no host: {url!r}")
    if _resolves_to_private(parsed.hostname):
        raise UnsafeFetchTarget(
            f"refusing to fetch {parsed.hostname!r}: resolves to a private, "
            "loopback, or link-local address"
        )


def _fetch(
    url: str, timeout: int = FETCH_TIMEOUT_SECONDS, max_bytes: int = MAX_HTML_BYTES
) -> tuple[int, dict[str, str], str]:
    """Fetch a URL and return (status, headers, body-as-text). Never raises;
    returns (-1, {}, error-message) on transport failure."""
    try:
        assert_fetchable(url)
    except UnsafeFetchTarget as e:
        return -1, {}, str(e)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            encoding = "utf-8"
            ctype = headers.get("content-type", "")
            m = re.search(r"charset=([\w-]+)", ctype, re.I)
            if m:
                encoding = m.group(1)
            try:
                body = raw.decode(encoding, errors="replace")
            except LookupError:
                body = raw.decode("utf-8", errors="replace")
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, ""
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return -1, {}, f"fetch_error: {e}"


# ---------- Heuristic analyzers ----------

_FRAMEWORK_SIGNATURES = [
    ("nextjs", [r'id="__next"', r"/_next/", r"_buildManifest\.js"]),
    ("nuxt", [r'id="__nuxt"', r"/_nuxt/", r"window\.__NUXT__"]),
    ("react", [r'id="root"', r"react-dom", r"react\.production\.min\.js"]),
    ("vue", [r'id="app"', r"vue\.runtime", r"data-server-rendered"]),
    ("angular", [r"ng-version=", r"app-root"]),
    ("svelte", [r"svelte-", r"sveltekit"]),
    ("astro", [r"astro-island", r"data-astro"]),
    ("gatsby", [r"___gatsby"]),
    ("remix", [r"__remixContext"]),
]

_PLATFORM_SIGNATURES = [
    ("shopify", [r"cdn\.shopify\.com", r"Shopify\.theme", r"window\.Shopify"]),
    ("woocommerce", [r"wp-content/plugins/woocommerce", r"woocommerce-"]),
    ("magento", [r"Magento_", r"mage/cookies", r"data-mage-init"]),
    ("salesforce_commerce", [r"demandware\.static", r"sfra"]),
    ("bigcommerce", [r"cdn11\.bigcommerce\.com", r"BCData"]),
    ("wordpress", [r"wp-content/", r"wp-includes/", r"wp-json"]),
    ("webflow", [r"webflow\.com", r"data-wf-"]),
    ("wix", [r"static\.wixstatic\.com", r"wix-code"]),
    ("squarespace", [r"static1\.squarespace\.com", r"squarespace-content"]),
    ("hubspot_cms", [r"hs-scripts\.com", r"hubspotusercontent"]),
    ("ghost", [r'<meta name="generator" content="Ghost']),
]

_VERTICAL_SIGNATURES = [
    (
        "ecommerce",
        [
            r'"@type"\s*:\s*"Product"',
            r"add[\s_-]?to[\s_-]?cart",
            r"\bcheckout\b",
            r"\bcart\b",
            r"\bsku\b",
            r"shop\.",
        ],
    ),
    (
        "saas",
        [
            r'"@type"\s*:\s*"SoftwareApplication"',
            r"\bsign\s*up\b",
            r"\bfree\s*trial\b",
            r"\bpricing\b",
            r"start\s*for\s*free",
        ],
    ),
    (
        "media",
        [
            r'"@type"\s*:\s*"NewsArticle"',
            r'"@type"\s*:\s*"Article"',
            r'"@type"\s*:\s*"BlogPosting"',
            r"\barticles?/",
            r"\bblog/",
        ],
    ),
    (
        "lead_gen",
        [
            r"\brequest[\s-]?a[\s-]?demo\b",
            r"\bcontact\s*sales\b",
            r"\bschedule\s*a\s*call\b",
            r"\bget\s*a\s*quote\b",
        ],
    ),
    (
        "finance",
        [
            r"\binvestor\b",
            r"\bcredit\s*card\b",
            r"\binterest\s*rate\b",
            r'"@type"\s*:\s*"FinancialService"',
        ],
    ),
    (
        "travel",
        [
            r"\bflights?\b",
            r"\bhotels?\b",
            r"\bbook\s*now\b",
            r"\bcheck[\s-]?in\b",
            r'"@type"\s*:\s*"LodgingBusiness"',
        ],
    ),
    (
        "education",
        [
            r"\bcourses?\b",
            r"\bsyllabus\b",
            r"\benroll(?:ment)?\b",
            r'"@type"\s*:\s*"Course"',
        ],
    ),
    (
        "nonprofit",
        [
            r"\bdonate\b",
            r"\bdonation\b",
            r'"@type"\s*:\s*"NGO"',
            r'"@type"\s*:\s*"NonprofitOrganization"',
        ],
    ),
]


def _match_signatures(text: str, table) -> list[tuple[str, int]]:
    text_lower = text.lower()
    hits = []
    for label, patterns in table:
        score = 0
        for p in patterns:
            if re.search(p, text_lower, re.I):
                score += 1
        if score:
            hits.append((label, score))
    hits.sort(key=lambda kv: -kv[1])
    return hits


def _extract_meta(html: str, name: str) -> str | None:
    pat = re.compile(
        rf'<meta\s+[^>]*?name=["\']{re.escape(name)}["\'][^>]*?content=["\']([^"\']+)["\']',
        re.I,
    )
    m = pat.search(html)
    if m:
        return m.group(1).strip()
    pat2 = re.compile(
        rf'<meta\s+[^>]*?content=["\']([^"\']+)["\'][^>]*?name=["\']{re.escape(name)}["\']',
        re.I,
    )
    m = pat2.search(html)
    return m.group(1).strip() if m else None


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip() if m else None


def _extract_lang(html: str) -> str | None:
    m = re.search(r'<html[^>]*?\blang=["\']([\w-]+)["\']', html, re.I)
    return m.group(1) if m else None


def _extract_canonical(html: str) -> str | None:
    m = re.search(
        r'<link\s+[^>]*?rel=["\']canonical["\'][^>]*?href=["\']([^"\']+)["\']', html, re.I
    )
    return m.group(1) if m else None


def _extract_jsonld(html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        blob = m.group(1).strip()
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, list):
                out.extend(x for x in parsed if isinstance(x, dict))
            elif isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def _parse_robots(text: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sitemaps = [ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sitemap:")]
    disallow_count = sum(1 for ln in lines if ln.lower().startswith("disallow:"))
    return {"sitemaps": sitemaps, "disallow_directives": disallow_count, "lines": len(lines)}


def _parse_sitemap(text: str, max_urls: int = MAX_SITEMAP_URLS) -> dict[str, Any]:
    urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, re.I | re.S)
    sample = urls[:max_urls]
    is_index = "<sitemapindex" in text.lower()
    page_types = _classify_page_types(sample)
    return {
        "is_index": is_index,
        "url_count_sampled": len(sample),
        "url_count_total_estimate": len(urls),
        "sample": sample[:50],
        "page_types": page_types,
    }


_PAGE_TYPE_RULES = [
    ("product", [r"/products?/", r"/p/", r"/item/", r"/shop/"]),
    ("category", [r"/categories?/", r"/c/", r"/collections?/"]),
    ("blog_post", [r"/blog/", r"/posts?/", r"/articles?/", r"/news/"]),
    ("docs", [r"/docs?/", r"/documentation/", r"/help/"]),
    ("pricing", [r"/pricing", r"/plans?\b"]),
    ("auth", [r"/login\b", r"/signin\b", r"/signup\b", r"/register\b"]),
    ("checkout", [r"/cart\b", r"/checkout\b", r"/basket\b"]),
    ("account", [r"/account\b", r"/profile\b", r"/dashboard\b"]),
    ("policy", [r"/privacy", r"/terms", r"/cookies", r"/legal"]),
]


def _classify_page_types(urls: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for u in urls:
        path = urllib.parse.urlparse(u).path.lower()
        matched = False
        for label, patterns in _PAGE_TYPE_RULES:
            if any(re.search(p, path) for p in patterns):
                counts[label] = counts.get(label, 0) + 1
                matched = True
                break
        if not matched:
            counts["other"] = counts.get("other", 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


# ---------- The analyzer ----------


def analyze_website(url: str) -> dict[str, Any]:
    """Fetch the URL plus robots.txt and sitemap.xml, return a context dict."""
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urllib.parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    status, headers, html = _fetch(url)
    home = {
        "url": url,
        "status": status,
        "server": headers.get("server"),
        "content_type": headers.get("content-type"),
        "cache_control": headers.get("cache-control"),
    }
    title = lang = canonical = generator = None
    jsonld_types: list[str] = []
    framework_hits: list[tuple[str, int]] = []
    platform_hits: list[tuple[str, int]] = []
    vertical_hits: list[tuple[str, int]] = []
    spa_hint = False
    body_html_length = 0

    if status == 200 and html:
        body_html_length = len(html)
        title = _extract_title(html)
        lang = _extract_lang(html)
        canonical = _extract_canonical(html)
        generator = _extract_meta(html, "generator")
        for d in _extract_jsonld(html):
            t = d.get("@type")
            if isinstance(t, str):
                jsonld_types.append(t)
            elif isinstance(t, list):
                jsonld_types.extend(x for x in t if isinstance(x, str))
        framework_hits = _match_signatures(html, _FRAMEWORK_SIGNATURES)
        platform_hits = _match_signatures(html, _PLATFORM_SIGNATURES)
        vertical_hits = _match_signatures(html, _VERTICAL_SIGNATURES)
        # SPA heuristic: visible body content is mostly an empty mount + JS
        body_m = re.search(r"<body[^>]*>(.*?)</body>", html, re.I | re.S)
        if body_m:
            body_inner = body_m.group(1)
            visible_text = re.sub(r"<script.*?</script>", "", body_inner, flags=re.I | re.S)
            visible_text = re.sub(r"<style.*?</style>", "", visible_text, flags=re.I | re.S)
            visible_text = re.sub(r"<[^>]+>", "", visible_text)
            spa_hint = len(visible_text.strip()) < 800 and len(body_inner) > 200

    home.update(
        {
            "title": title,
            "lang": lang,
            "canonical": canonical,
            "generator": generator,
            "html_bytes": body_html_length,
        }
    )

    robots_text = _fetch_safely(origin + "/robots.txt")
    robots = _parse_robots(robots_text) if robots_text else None

    sitemap_text = None
    sitemap_url = None
    if robots and robots["sitemaps"]:
        sitemap_url = robots["sitemaps"][0]
        sitemap_text = _fetch_safely(sitemap_url)
    if not sitemap_text:
        sitemap_url = origin + "/sitemap.xml"
        sitemap_text = _fetch_safely(sitemap_url)
    sitemap = _parse_sitemap(sitemap_text) if sitemap_text else None

    inferred_vertical = vertical_hits[0][0] if vertical_hits else "other"
    inferred_platform = platform_hits[0][0] if platform_hits else None
    inferred_framework = framework_hits[0][0] if framework_hits else None
    is_spa = spa_hint or inferred_framework in {
        "nextjs",
        "nuxt",
        "react",
        "vue",
        "angular",
        "svelte",
        "remix",
    }

    summary = _make_summary(home, inferred_vertical, inferred_platform, inferred_framework, is_spa)

    return {
        "url": url,
        "origin": origin,
        "homepage": home,
        "jsonld_types": jsonld_types,
        "framework_candidates": framework_hits,
        "platform_candidates": platform_hits,
        "vertical_candidates": vertical_hits,
        "robots": robots,
        "sitemap": sitemap,
        "sitemap_url": sitemap_url,
        "inferred": {
            "vertical": inferred_vertical,
            "platform": inferred_platform,
            "framework": inferred_framework,
            "is_spa": is_spa,
        },
        "summary": summary,
    }


def _fetch_safely(url: str) -> str | None:
    status, _h, body = _fetch(url)
    if status == 200 and body:
        return body
    return None


def _make_summary(home, vertical, platform, framework, is_spa) -> str:
    pieces = []
    if home.get("title"):
        pieces.append(home["title"])
    if vertical and vertical != "other":
        pieces.append(f"vertical: {vertical}")
    if platform:
        pieces.append(f"platform: {platform}")
    if framework:
        pieces.append(f"framework: {framework}")
    pieces.append("SPA" if is_spa else "MPA")
    if home.get("lang"):
        pieces.append(f"lang={home['lang']}")
    return " | ".join(pieces)


# ---------- High-level orchestration ----------


def build_property_context(property_id: str, force: bool = False) -> dict[str, Any]:
    """Top-level: read GA4 streams, pick the first web stream's URL,
    analyze the site, and persist a structured context dict."""
    if not force:
        existing = load_context(property_id)
        if existing:
            return {"status": "cached", "property_id": property_id, "context": existing}

    streams = extract_property_urls(property_id)
    web_streams = [s for s in streams if s.get("default_uri")]
    if not web_streams:
        ctx = {
            "property_id": property_id,
            "streams": streams,
            "error": "no web stream with defaultUri found on this property",
        }
        save_context(property_id, ctx)
        return {"status": "no_web_stream", "context": ctx}

    primary = web_streams[0]
    analysis = analyze_website(primary["default_uri"])

    context = {
        "property_id": property_id,
        "streams_count": len(streams),
        "web_streams_count": len(web_streams),
        "primary_stream": {
            "stream_id": primary.get("stream_id"),
            "stream_name": primary.get("stream_name"),
            "default_uri": primary.get("default_uri"),
        },
        "additional_streams": [
            {
                "stream_id": s.get("stream_id"),
                "stream_name": s.get("stream_name"),
                "default_uri": s.get("default_uri"),
            }
            for s in streams
            if s is not primary
        ],
        "site": analysis,
    }
    save_context(property_id, context)
    return {"status": "ok", "property_id": property_id, "context": context}


# ---------- CLI ----------


def main():
    parser = argparse.ArgumentParser(description="GA4 property context extractor")
    parser.add_argument("--property", help="GA4 property ID")
    parser.add_argument("--url", help="Analyze an arbitrary URL without GA4 lookup")
    parser.add_argument(
        "--analyze", action="store_true", help="Extract and analyze (uses cache by default)"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Force re-analysis even if a cached context exists"
    )
    parser.add_argument(
        "--show", action="store_true", help="Print the stored context for a property"
    )
    parser.add_argument("--delete", action="store_true", help="Delete the stored context")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.url:
            out = analyze_website(args.url)
        elif args.show:
            ctx = load_context(args.property)
            out = ctx if ctx else {"error": "no context cached for this property"}
        elif args.delete:
            out = delete_context(args.property)
        elif args.refresh or args.analyze:
            if not args.property:
                raise ValueError("--property required (or pass --url for a one-off analyze)")
            out = build_property_context(args.property, force=args.refresh)
        else:
            parser.print_help()
            return 1
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
