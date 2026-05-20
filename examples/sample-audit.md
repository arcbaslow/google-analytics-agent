# GA4 Audit — property 123456789

_Generated 2026-05-21 00:03_  
_Data confidence: **medium**_  
_Benchmark vertical: **ecommerce**_  

## Property Context

- Primary web stream: `Web` (`9876543210`)
- URL: https://riverbedoutfitters.example
- Homepage status: 200
- Title: Riverbed Outfitters
- Language: en-US
- Server header: `cloudflare`
- Inferred vertical: **ecommerce**
- Inferred framework: nextjs
- Inferred platform: shopify
- Rendering: SPA
- Sitemap page types: product: 1240, category: 312, blog_post: 210, policy: 18, other: 62
- Sitemap URLs (sampled): 1842

_Riverbed Outfitters | vertical: ecommerce | platform: shopify | framework: nextjs | SPA | lang=en-US_

## Executive Summary

- **ga4-context**: Riverbed Outfitters | vertical: ecommerce | platform: shopify | framework: nextjs | SPA | lang=en-US
- **ga4-quality**: data confidence medium; direct share 24.5%; sampling 0.8%
- **ga4-events**: 38 distinct events, 5/5 ecomm-preset events present
- **ga4-funnel**: funnel steps view_item -> add_to_cart -> begin_checkout -> add_payment_info -> purchase, overall CR 2.10%
- **ga4-segments**: stub — run `/ga4 segments <property-id>` (or the Claude Code skill) for cohort breakdowns
- **ga4-conversions**: 3 key event(s) configured
- **ga4-attribution**: attribution scan against `purchase`
- **ga4-property**: property configuration scan complete

## Action Plan

### High

- **High (direct)/(none) share** _(source: ga4-quality)_ (value 0.245, vertical ecommerce, p25 0.1 / p50 0.2 / p75 0.32, band p50_to_p75, interpretation poor)
  - 24.5% of sessions attributed to direct. Audit UTM tagging on payment redirects, partner links, and email campaigns.
- **purchase.currency coverage below 95%** _(source: ga4-events)_
  - purchase fires with currency on only 88% of events in the 7-day window. Storefront checkout-success template likely missing currency in the dataLayer push.
- **Leakiest step: view_item -> add_to_cart** _(source: ga4-funnel)_
  - 142,580 users lost at this step (64% of total funnel loss). Investigate PDP gallery load time and add-to-cart button visibility on mobile.
- **Direct share on primary conversion above 30%** _(source: ga4-attribution)_ (value 0.342, vertical ecommerce, p25 0.1 / p50 0.2 / p75 0.32, band above_p75, interpretation critical)
  - 34.2% of purchase events attribute to direct. UTM tagging gaps on the payment-gateway redirect-back path are the most likely cause.
- **Data retention shorter than 14 months** _(source: ga4-property)_
  - Event-data retention is TWO_MONTHS. For multi-month cohort analysis set to FOURTEEN_MONTHS in Admin -> Data Settings -> Data Retention.

### Medium

- **Visible sampling on 28-day session report** _(source: ga4-quality)_ (value 0.008, vertical ecommerce, p25 0 / p50 0.01 / p75 0.05, band p25_to_p50, interpretation average)
  - Sampling rate 0.8%. Verify high-stakes findings on a shorter window.

### Low

- **Overall funnel conversion rate** _(source: ga4-funnel)_ (value 0.021, vertical ecommerce, p25 0.012 / p50 0.023 / p75 0.042, band p25_to_p50, interpretation poor)
  - View-to-purchase: 2.10% across the 28-day window.

## Per-Agent Output

### ga4-context

Riverbed Outfitters | vertical: ecommerce | platform: shopify | framework: nextjs | SPA | lang=en-US

<details>
<summary>raw output</summary>

```json
{
  "note": "see Property Context section"
}
```

</details>

### ga4-quality

data confidence medium; direct share 24.5%; sampling 0.8%

<details>
<summary>raw output</summary>

```json
{
  "sampling_pct": 0.008,
  "direct_share": 0.245,
  "not_set_share": 0.014,
  "confidence_label": "medium"
}
```

</details>

### ga4-events

38 distinct events, 5/5 ecomm-preset events present

<details>
<summary>raw output</summary>

```json
{
  "distinct_event_count": 38,
  "ecomm_events_present": [
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "add_payment_info",
    "purchase"
  ]
}
```

</details>

### ga4-funnel

funnel steps view_item -> add_to_cart -> begin_checkout -> add_payment_info -> purchase, overall CR 2.10%

<details>
<summary>raw output</summary>

```json
{
  "window_days": 28,
  "overall_cr": 0.021,
  "rates": {
    "aggregate": {
      "overall_conversion_pct": 2.1
    }
  }
}
```

</details>

### ga4-segments

stub — run `/ga4 segments <property-id>` (or the Claude Code skill) for cohort breakdowns

<details>
<summary>raw output</summary>

```json
{
  "hint": "cohort analysis is LLM-driven in the full Claude skill; this driver omits it"
}
```

</details>

### ga4-conversions

3 key event(s) configured

<details>
<summary>raw output</summary>

```json
{
  "key_event_count": 3,
  "key_event_names": [
    "purchase",
    "add_to_cart",
    "generate_lead"
  ]
}
```

</details>

### ga4-attribution

attribution scan against `purchase`

<details>
<summary>raw output</summary>

```json
{
  "attribution_settings": {
    "reporting_attribution_model": "DATA_DRIVEN"
  },
  "primary_event_direct_share": 0.342
}
```

</details>

### ga4-property

property configuration scan complete

<details>
<summary>raw output</summary>

```json
{
  "streams": [
    {
      "displayName": "Web",
      "webStreamData": {
        "defaultUri": "https://riverbedoutfitters.example"
      }
    }
  ]
}
```

</details>

---

_Generated by google-analytics-agent._
