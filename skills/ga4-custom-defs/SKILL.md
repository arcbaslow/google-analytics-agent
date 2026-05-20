---
name: ga4-custom-defs
description: "Create or archive GA4 custom dimensions and custom metrics via the Admin API. Use when adding catalog brand/category dimensions for ecomm, exposing a custom event parameter as a reportable field, or cleaning up old definitions to free quota."
user-invokable: true
argument-hint: "<property-id> [--add-dim --parameter-name P --display-name D --scope EVENT|USER|ITEM] [--add-metric --parameter-name P --display-name D --measurement-unit STANDARD|...] [--archive-dim NAME] [--archive-metric NAME]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Custom Dimensions and Metrics

Scope required: `analytics.edit`.

## Limits (standard properties, GA4 360 in parens)

- Event-scoped custom dimensions: 50 (125)
- User-scoped custom dimensions: 25 (100)
- Item-scoped custom dimensions: 10 (25)
- Custom metrics: 50 (125)

Before creating, list current definitions to check headroom:

```
python scripts/ga4_admin.py --property X --custom-defs --json
```

## Commands

| Intent | Command |
|--------|---------|
| Add event-scoped dimension | `python scripts/ga4_admin.py --property X --add-custom-dim --parameter-name brand --display-name "Brand" --scope EVENT` |
| Add item-scoped dimension | `python scripts/ga4_admin.py --property X --add-custom-dim --parameter-name item_brand --display-name "Item brand" --scope ITEM` |
| Add custom metric | `python scripts/ga4_admin.py --property X --add-custom-metric --parameter-name shipping_value --display-name "Shipping value" --measurement-unit CURRENCY` |
| Archive dimension | `python scripts/ga4_admin.py --archive-custom-dim properties/X/customDimensions/123 --json` |
| Archive metric | `python scripts/ga4_admin.py --archive-custom-metric properties/X/customMetrics/123 --json` |

## Validation

The script validates `parameter_name` before calling the API:

- Must start with a letter
- May contain letters, digits, underscores
- Length ≤ 40 (event-scoped) or 24 (user-scoped)
- Scope must be `EVENT`, `USER`, or `ITEM`

## When to use

- **EVENT**: per-event metadata that varies across hits (logged_in_status, plan_tier, payment_provider, content_topic, video_quality)
- **USER**: durable user attributes that rarely change (membership_tier, signup_cohort, internal_user_id)
- **ITEM**: per-product / per-line-item catalog metadata used in ecomm `items[]` arrays (brand, supplier, category_path)

## Cleanup

Archived definitions cannot be undone, but the slot is freed. Use the
`ga4-property` agent to identify definitions with no data flowing.
