# Sample audit — condensed view

A trimmed first screen of the full markdown report in
[`sample-audit.md`](sample-audit.md): header, property context, executive
summary, and the first two action-plan items.

```
# GA4 Audit — property 123456789

_Generated 2026-05-21 00:03_
_Data confidence: **medium**_
_Benchmark vertical: **ecommerce**_

## Property Context

- URL: https://riverbedoutfitters.example
- Inferred vertical: **ecommerce**
- Inferred platform: shopify
- Inferred framework: nextjs
- Rendering: SPA
- Sitemap page types: product: 1240, category: 312, blog_post: 210, ...

## Executive Summary

- **ga4-quality**: data confidence medium; direct share 24.5%; sampling 0.8%
- **ga4-events**: 38 distinct events, 5/5 ecomm-preset events present
- **ga4-funnel**: view_item -> add_to_cart -> ... -> purchase, overall CR 2.10%
- **ga4-conversions**: 3 key event(s) configured

## Action Plan

### High

- **High (direct)/(none) share** _(source: ga4-quality)_
  (value 0.245, vertical ecommerce, p25 0.1 / p50 0.2 / p75 0.32,
  band p50_to_p75, interpretation poor)
  - 24.5% of sessions attributed to direct. Audit UTM tagging on
    payment redirects, partner links, and email campaigns.
- **Leakiest step: view_item -> add_to_cart** _(source: ga4-funnel)_
  - 142,580 users lost at this step (64% of total funnel loss).
    Investigate PDP gallery load time and add-to-cart visibility.
```
