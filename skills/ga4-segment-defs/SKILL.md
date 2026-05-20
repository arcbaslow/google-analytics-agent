---
name: ga4-segment-defs
description: "Saved GA4 segment definitions stored as local JSON. GA4 has no stored Segment resource — segments only exist inside Explorations. This skill saves filter expressions to ~/.claude/ga4-definitions/segments/ and applies them as dimensionFilter on Data API runReport calls. Use for reusable cohorts on the public API. For stored cohorts that work in GA4 reports and Google Ads, use ga4-audiences. For funnel drop-off cohort analysis, use ga4-segments."
user-invokable: true
argument-hint: "[--save <name> --field F --op OP --value V] [--save-json <name> <path>] [--list] [--delete <name>]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Saved Segment Definitions

GA4 has no public Segment API. We persist filter expressions locally and inject
them into `runReport` calls — same effect for analytics, but they do not
propagate to the GA4 UI or to Google Ads. Users who need cohorts visible inside
GA4 should use the `ga4-audiences` skill instead. For funnel drop-off cohort
analysis (read-only), use `ga4-segments`.

Storage: `~/.claude/ga4-definitions/segments/<slug>.json`

No API call is made by this skill; auth is only needed when a segment is
applied to a runReport via `ga4-custom-report`.

## Commands

| Intent | Command |
|--------|---------|
| Save shorthand | `python scripts/ga4_definitions.py --save-segment "branded-traffic" --field sessionSource --op CONTAINS --value brand` |
| Save IN-list | `python scripts/ga4_definitions.py --save-segment "us-and-canada" --field country --op IN_LIST --values "United States,Canada"` |
| Save raw expression | `python scripts/ga4_definitions.py --save-segment-json "complex" path/to/filter.json` |
| List | `python scripts/ga4_definitions.py --list-segments --json` |
| Delete | `python scripts/ga4_definitions.py --delete-segment "branded-traffic" --json` |

## Shorthand operators

`EXACT`, `CONTAINS`, `BEGINS_WITH`, `IN_LIST`. For NOT, AND, OR groups, save as
raw JSON.

## Raw expression shape

A Data API `FilterExpression` dict, e.g.

```json
{
  "and_group": {
    "expressions": [
      {"filter": {"field_name": "deviceCategory", "string_filter": {"value": "mobile", "match_type": "EXACT"}}},
      {"filter": {"field_name": "sessionSource", "string_filter": {"value": "brand", "match_type": "CONTAINS"}}}
    ]
  }
}
```

## Applying a segment

Run a saved custom report with a segment applied:

```
python scripts/ga4_definitions.py --run-report channel-by-week --property 123 --segment "branded-traffic" --format html --output channel-branded.html
```
