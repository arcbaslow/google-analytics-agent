---
name: ga4-custom-report
description: "Saved custom GA4 reports executed against the Data API runReport. Stored locally as JSON definitions (~/.claude/ga4-definitions/reports/). Render to JSON, CSV, HTML, or PDF. GA4 has no Explorations API; this skill replaces ad-hoc one-off runReport calls with named, reusable, version-controllable definitions."
user-invokable: true
argument-hint: "[--save <name> <def.json>] [--list] [--run <name> --property <id> [--days N] [--format html|pdf|json|csv] [--segment NAME] [--output PATH]]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Custom Reports

Persist a Data API runReport definition once, run it many times with a single
command. Supports segment overlay via the `ga4-segments` skill.

Storage: `~/.claude/ga4-definitions/reports/<slug>.json`

## Definition shape

```json
{
  "name": "channel-by-week",
  "description": "Weekly active users and sessions by channel group",
  "metrics": ["activeUsers", "sessions"],
  "dimensions": ["sessionDefaultChannelGroup", "week"],
  "dimension_filter": null,
  "metric_filter": null,
  "order_bys": [{"metric": "activeUsers", "desc": true}],
  "limit": 250,
  "default_days": 28,
  "default_format": "html"
}
```

## Commands

| Intent | Command |
|--------|---------|
| Save | `python scripts/ga4_definitions.py --save-report channel-by-week definition.json` |
| List | `python scripts/ga4_definitions.py --list-reports --json` |
| Delete | `python scripts/ga4_definitions.py --delete-report channel-by-week --json` |
| Run (HTML) | `python scripts/ga4_definitions.py --run-report channel-by-week --property 123 --format html --output out.html` |
| Run with segment | `python scripts/ga4_definitions.py --run-report channel-by-week --property 123 --segment branded-traffic --format pdf --output out.pdf` |

## Output formats

- `json` — full Data API response with rows + sampling metadata
- `csv` — flattened rows, no metadata
- `html` — single-report Manrope-styled HTML (same look as audit report)
- `pdf` — HTML rendered via WeasyPrint

## Useful starter reports

- **funnel-by-channel** — purchase funnel events broken down by channel group
- **landing-page-revenue** — landing page × purchase value
- **device-conversion** — sessions and conversions by device category
- **search-terms** — site search keyword volume

For each, save a definition once with `--save-report`, then re-run weekly.
