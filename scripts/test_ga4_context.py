"""Tests for ga4_context: storage, URL extraction, signature heuristics, sitemap parsing."""

import urllib.error
from pathlib import Path

import pytest

import ga4_admin
import ga4_context


@pytest.fixture(autouse=True)
def _redirect_context_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_context, "CONTEXT_DIR", tmp_path / "ga4-context")


# ---------- Storage round-trip ----------


def test_save_and_load_context(tmp_path):
    ctx = {"property_id": "123", "site": {"summary": "test"}}
    path = ga4_context.save_context("123", ctx)
    assert Path(path).exists()
    loaded = ga4_context.load_context("123")
    assert loaded["site"]["summary"] == "test"


def test_load_missing_returns_none():
    assert ga4_context.load_context("missing") is None


def test_delete_context_removes_file():
    ga4_context.save_context("p1", {"x": 1})
    out = ga4_context.delete_context("p1")
    assert out["status"] == "deleted"
    assert ga4_context.load_context("p1") is None


def test_delete_absent_returns_absent():
    out = ga4_context.delete_context("never")
    assert out["status"] == "absent"


# ---------- Signature heuristics ----------

NEXTJS_HTML = """<!doctype html><html lang="en"><head><title>Acme</title>
<meta name="generator" content="Next.js"></head>
<body><div id="__next"></div>
<script src="/_next/static/_buildManifest.js"></script>
</body></html>"""

SHOPIFY_HTML = """<!doctype html><html lang="en"><head><title>Shop</title></head>
<body>
<script src="https://cdn.shopify.com/shopifycloud/some.js"></script>
<script>window.Shopify = {};</script>
<a href="/cart">Cart</a>
<button>Add to cart</button>
</body></html>"""

WORDPRESS_HTML = """<!doctype html><html lang="en"><head>
<link rel="stylesheet" href="/wp-content/themes/x/style.css">
<meta name="generator" content="WordPress 6.4">
</head><body>
<article>blog post content here</article>
<a href="/blog/some-post">read more</a>
</body></html>"""


def test_nextjs_signature_detected():
    fws = ga4_context._match_signatures(NEXTJS_HTML, ga4_context._FRAMEWORK_SIGNATURES)
    assert fws and fws[0][0] == "nextjs"


def test_shopify_platform_and_ecommerce_vertical():
    plats = ga4_context._match_signatures(SHOPIFY_HTML, ga4_context._PLATFORM_SIGNATURES)
    verticals = ga4_context._match_signatures(SHOPIFY_HTML, ga4_context._VERTICAL_SIGNATURES)
    assert plats and plats[0][0] == "shopify"
    assert verticals and verticals[0][0] == "ecommerce"


def test_wordpress_platform_and_media_vertical():
    plats = ga4_context._match_signatures(WORDPRESS_HTML, ga4_context._PLATFORM_SIGNATURES)
    verticals = ga4_context._match_signatures(WORDPRESS_HTML, ga4_context._VERTICAL_SIGNATURES)
    assert plats and plats[0][0] == "wordpress"
    assert verticals and verticals[0][0] == "media"


# ---------- Extractors ----------


def test_extract_title():
    assert ga4_context._extract_title(NEXTJS_HTML) == "Acme"
    assert ga4_context._extract_title("<html><body>no title</body></html>") is None


def test_extract_lang():
    assert ga4_context._extract_lang(NEXTJS_HTML) == "en"


def test_extract_meta_generator():
    assert ga4_context._extract_meta(NEXTJS_HTML, "generator") == "Next.js"


def test_extract_jsonld_returns_dicts():
    html = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Test"}</script>
</head><body></body></html>"""
    items = ga4_context._extract_jsonld(html)
    assert items[0]["@type"] == "Product"


def test_extract_jsonld_handles_arrays():
    html = """<html><head>
<script type="application/ld+json">[{"@type":"Article"},{"@type":"Person"}]</script>
</head></html>"""
    items = ga4_context._extract_jsonld(html)
    assert {x["@type"] for x in items} == {"Article", "Person"}


# ---------- robots.txt + sitemap ----------


def test_parse_robots_picks_sitemap_lines():
    text = """User-agent: *
Disallow: /admin
Disallow: /private
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-news.xml
"""
    out = ga4_context._parse_robots(text)
    assert out["sitemaps"] == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap-news.xml",
    ]
    assert out["disallow_directives"] == 2


def test_parse_sitemap_classifies_page_types():
    text = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/products/a</loc></url>
  <url><loc>https://example.com/products/b</loc></url>
  <url><loc>https://example.com/blog/intro</loc></url>
  <url><loc>https://example.com/checkout</loc></url>
  <url><loc>https://example.com/random</loc></url>
</urlset>"""
    out = ga4_context._parse_sitemap(text)
    assert out["page_types"]["product"] == 2
    assert out["page_types"]["blog_post"] == 1
    assert out["page_types"]["checkout"] == 1
    assert out["page_types"]["other"] == 1


def test_parse_sitemap_detects_index():
    idx = """<?xml version="1.0"?><sitemapindex>
<sitemap><loc>https://example.com/sm-a.xml</loc></sitemap>
<sitemap><loc>https://example.com/sm-b.xml</loc></sitemap>
</sitemapindex>"""
    out = ga4_context._parse_sitemap(idx)
    assert out["is_index"] is True


# ---------- analyze_website with mocked fetch ----------


def test_analyze_website_uses_mocked_fetch(monkeypatch):
    seen = []

    def fake_fetch(url, timeout=12, max_bytes=800_000):
        seen.append(url)
        if url.endswith("/robots.txt"):
            return 200, {"content-type": "text/plain"}, "Sitemap: https://example.com/sitemap.xml\n"
        if "sitemap.xml" in url:
            return (
                200,
                {"content-type": "application/xml"},
                ("<urlset><url><loc>https://example.com/products/a</loc></url></urlset>"),
            )
        return 200, {"content-type": "text/html", "server": "nginx"}, NEXTJS_HTML

    monkeypatch.setattr(ga4_context, "_fetch", fake_fetch)

    out = ga4_context.analyze_website("https://example.com")
    assert out["homepage"]["status"] == 200
    assert out["inferred"]["framework"] == "nextjs"
    assert out["inferred"]["is_spa"] is True
    assert out["sitemap"]["page_types"]["product"] == 1
    assert "Acme" in out["summary"]


# ---------- build_property_context end-to-end ----------


def test_build_property_context_no_web_stream(monkeypatch):
    monkeypatch.setattr(
        ga4_context,
        "extract_property_urls",
        lambda pid: [
            {
                "stream_id": "1",
                "stream_name": "iOS app",
                "default_uri": None,
                "type": "IOS_APP_DATA_STREAM",
            },
        ],
    )
    out = ga4_context.build_property_context("999")
    assert out["status"] == "no_web_stream"


def test_build_property_context_with_web_stream(monkeypatch):
    monkeypatch.setattr(
        ga4_context,
        "extract_property_urls",
        lambda pid: [
            {
                "stream_id": "1",
                "stream_name": "Web",
                "default_uri": "https://example.com",
                "type": "WEB_DATA_STREAM",
            },
        ],
    )
    monkeypatch.setattr(
        ga4_context,
        "analyze_website",
        lambda url: {"summary": "stub", "inferred": {"vertical": "ecommerce"}},
    )
    out = ga4_context.build_property_context("123")
    assert out["status"] == "ok"
    assert out["context"]["primary_stream"]["default_uri"] == "https://example.com"
    # And it persisted
    cached = ga4_context.load_context("123")
    assert cached is not None
    assert cached["site"]["inferred"]["vertical"] == "ecommerce"


def test_build_property_context_uses_cache(monkeypatch):
    ga4_context.save_context("123", {"site": {"summary": "cached"}})
    out = ga4_context.build_property_context("123")
    assert out["status"] == "cached"


# ---------- extract_property_urls ----------


def test_extract_property_urls_maps_camel_and_snake_fields(monkeypatch):
    streams = [
        {
            "name": "properties/123/dataStreams/9",
            "displayName": "Web",
            "type_": "WEB_DATA_STREAM",
            "webStreamData": {"defaultUri": "https://acme.example"},
        },
        {
            "name": "properties/123/dataStreams/10",
            "display_name": "iOS",
            "type": "IOS_APP_DATA_STREAM",
        },
    ]
    monkeypatch.setattr(ga4_admin, "list_data_streams", lambda pid: streams)

    out = ga4_context.extract_property_urls("123")
    assert out[0]["stream_id"] == "9"
    assert out[0]["stream_name"] == "Web"
    assert out[0]["default_uri"] == "https://acme.example"
    assert out[0]["type"] == "WEB_DATA_STREAM"
    assert out[1]["stream_id"] == "10"
    assert out[1]["default_uri"] is None
    assert out[1]["type"] == "IOS_APP_DATA_STREAM"


# ---------- _fetch (never raises) ----------


class _FakeResp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self._body = body

    def read(self, n=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_success_decodes_with_charset(monkeypatch):
    resp = _FakeResp(
        200, {"Content-Type": "text/html; charset=utf-8", "Server": "nginx"}, b"<html>hi</html>"
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: resp)

    status, headers, body = ga4_context._fetch("https://example.com")
    assert status == 200
    assert "hi" in body
    assert headers["server"] == "nginx"


def test_fetch_http_error_returns_code_and_empty_body(monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError("https://x", 404, "Not Found", {"X-Test": "y"}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    status, _headers, body = ga4_context._fetch("https://x")
    assert status == 404
    assert body == ""


def test_fetch_url_error_returns_minus_one(monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    status, _headers, body = ga4_context._fetch("https://x")
    assert status == -1
    assert "fetch_error" in body


def test_fetch_safely_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(ga4_context, "_fetch", lambda url, **k: (404, {}, ""))
    assert ga4_context._fetch_safely("https://x/robots.txt") is None


# ---------- extractor edge branches ----------


def test_extract_meta_handles_reversed_attribute_order():
    html = '<meta content="WordPress 6.4" name="generator">'
    assert ga4_context._extract_meta(html, "generator") == "WordPress 6.4"


def test_extract_jsonld_skips_malformed_blocks():
    html = (
        '<script type="application/ld+json">{ not valid json }</script>'
        '<script type="application/ld+json">{"@type":"Organization"}</script>'
    )
    assert ga4_context._extract_jsonld(html) == [{"@type": "Organization"}]


# ---------- _make_summary ----------


def test_make_summary_includes_all_pieces():
    s = ga4_context._make_summary(
        {"title": "Acme", "lang": "en"}, "ecommerce", "shopify", "nextjs", True
    )
    assert "Acme" in s
    assert "vertical: ecommerce" in s
    assert "platform: shopify" in s
    assert "framework: nextjs" in s
    assert "SPA" in s
    assert "lang=en" in s


def test_make_summary_omits_other_vertical_and_marks_mpa():
    s = ga4_context._make_summary({}, "other", None, None, False)
    assert "vertical" not in s
    assert "MPA" in s


# ---------- analyze_website edge branches ----------


def test_analyze_website_normalizes_schemeless_url(monkeypatch):
    monkeypatch.setattr(
        ga4_context,
        "_fetch",
        lambda url, **k: (200, {"content-type": "text/html"}, "<html><body>x</body></html>"),
    )
    out = ga4_context.analyze_website("example.com")
    assert out["url"].startswith("https://example.com")
    assert out["origin"] == "https://example.com"


def test_analyze_website_collects_jsonld_type_list(monkeypatch):
    html = (
        '<html><body><script type="application/ld+json">'
        '{"@type":["Product","Offer"]}</script></body></html>'
    )

    def fake_fetch(url, **k):
        if url.endswith("/robots.txt") or "sitemap" in url:
            return 404, {}, ""
        return 200, {"content-type": "text/html"}, html

    monkeypatch.setattr(ga4_context, "_fetch", fake_fetch)
    out = ga4_context.analyze_website("https://example.com")
    assert set(out["jsonld_types"]) == {"Product", "Offer"}
    assert out["sitemap"] is None  # both robots and sitemap fell through to None


def test_analyze_website_falls_back_to_default_sitemap(monkeypatch):
    def fake_fetch(url, **k):
        if url.endswith("/robots.txt"):
            return 200, {"content-type": "text/plain"}, "User-agent: *\nDisallow: /admin\n"
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"content-type": "application/xml"},
                "<urlset><url><loc>https://example.com/pricing</loc></url></urlset>",
            )
        return 200, {"content-type": "text/html"}, "<html><body>x</body></html>"

    monkeypatch.setattr(ga4_context, "_fetch", fake_fetch)
    out = ga4_context.analyze_website("https://example.com")
    # robots.txt had no Sitemap: line, so analyze falls back to /sitemap.xml
    assert out["sitemap_url"].endswith("/sitemap.xml")
    assert out["sitemap"]["page_types"]["pricing"] == 1
