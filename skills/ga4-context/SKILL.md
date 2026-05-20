---
name: ga4-context
description: "Extracts the property's web-stream URL from GA4, then fetches and analyzes the live website (homepage, robots.txt, sitemap.xml) to infer the vertical, framework, platform (Shopify / WordPress / etc.), SPA-vs-MPA rendering, language, and a sitemap-derived page-type inventory. The resulting profile is cached under ~/.claude/ga4-context/ so every other audit attaches it automatically."
user-invokable: true
argument-hint: "<property-id> [--refresh] [--show] [--delete]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.3.0"
  category: ga4
---

# GA4: Property Context

The first thing the auditor needs to know is what the property *is*. The
GA4 API can't tell you that — the data stream only points at a URL. This
skill walks from the GA4 property to that URL, fetches the live site,
and produces a structured profile that every downstream agent can lean
on:

- inferred industry vertical (used to pick benchmark bands)
- inferred CMS / e-commerce platform (Shopify, WooCommerce, Magento,
  WordPress, Webflow, Wix, Squarespace, BigCommerce, Salesforce Commerce,
  HubSpot CMS, Ghost)
- inferred frontend framework (Next.js, Nuxt, React, Vue, Angular,
  Svelte, Astro, Gatsby, Remix)
- SPA vs MPA rendering
- canonical host, language, server header
- sitemap-derived page-type inventory (products, categories, blog posts,
  docs, pricing, auth, checkout, account, policy)

## Process

1. Verify auth: `python scripts/ga4_auth.py --check`
2. Run the analyzer:
   ```
   python scripts/ga4_context.py --property <id> --analyze --json
   ```
3. If the user asks for a refresh of a cached profile, pass `--refresh`.
4. Spawn the `ga4-context` agent only if the user wants a human-readable
   summary of the raw analysis. Otherwise the JSON output is enough — it
   is consumed directly by other skills.

## Direct commands

| Intent | Command |
|--------|---------|
| First-time analysis | `python scripts/ga4_context.py --property X --analyze --json` |
| Force re-analysis | `python scripts/ga4_context.py --property X --refresh --json` |
| Show cached context | `python scripts/ga4_context.py --property X --show --json` |
| Delete cached context | `python scripts/ga4_context.py --property X --delete --json` |
| One-off URL analysis | `python scripts/ga4_context.py --url https://example.com --analyze --json` |

## Output shape

```
{
  "property_id": "...",
  "primary_stream": {"stream_id": "...", "default_uri": "https://..."},
  "site": {
    "homepage": {"status": 200, "title": "...", "lang": "en", "server": "..."},
    "inferred": {"vertical": "ecommerce", "platform": "shopify",
                  "framework": "react", "is_spa": true},
    "sitemap": {"url_count_total_estimate": 1240,
                 "page_types": {"product": 800, "blog_post": 220, ...}},
    "summary": "Acme Store | vertical: ecommerce | platform: shopify | ..."
  }
}
```

## When to call this skill

- Automatically as the first step of `/ga4 audit` (the audit
  orchestrator calls it in parallel with the data-quality gate).
- Before any user-facing report so the "Property Context" section can
  be populated.
- Whenever the user changes the property's URL or migrates platform.

## Caveats

The fetch is a plain HTTP GET — no JS execution. SPA pages return their
shell HTML; framework detection still works (Next, Nuxt, React, Vue
leave server-side markers) but per-route content does not. For deeper
inspection use a headless-browser tool outside this skill.

The fetch obeys a 12-second timeout per URL, an 800 KB cap on the
homepage download, and the first 200 URLs of any sitemap. Sites that
block non-browser user agents will return a 4xx — the skill records
that gracefully and the context is still useful for downstream agents
(they just lose the inferred vertical, which the user can override on
the audit command line).
