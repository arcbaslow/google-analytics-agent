---
name: ga4
description: "Multi-agent toolkit for Google Analytics 4. Read side: data quality, funnel, segments, attribution, event taxonomy, key events, property configuration. Write side: edit events, manage audiences, custom dimensions and metrics, key events, saved segments, and saved custom reports. Talks to the Data API and Admin API; designed for properties without BigQuery export. Triggers on: ga4, google analytics, funnel, drop-off, conversion rate, audience, segment, custom report, custom dimension, key event."
user-invokable: true
argument-hint: "[command] [property-id] [options]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Multi-Agent Toolkit

**Invocation:** `/ga4 $1 $2` where `$1` is the command and `$2` is the property ID or argument.

**Scripts:** Located at the plugin root `scripts/` directory.

Multi-agent toolkit for analyzing and managing Google Analytics 4
properties. The analysis side covers data quality, funnels, segments,
attribution, event taxonomy, key events, and property configuration. The
management side covers event rules, audiences, custom dimensions and
metrics, key events, saved segments, and saved custom reports. All work
runs against the Data API and Admin API; nothing depends on a BigQuery
export.

## Quick Reference

Read commands:

| Command | What it does |
|---------|-------------|
| `/ga4 audit <property-id>` | Full audit with parallel agent delegation, benchmarks, markdown output by default |
| `/ga4 context <property-id>` | Profile the property's live site: vertical, platform, framework, sitemap shape |
| `/ga4 funnel <property-id>` | Step-by-step funnel drop-off (configurable steps; ecomm preset available) |
| `/ga4 segments <property-id>` | Funnel drop-off cohort breakdowns |
| `/ga4 events <property-id>` | Event taxonomy validation (configurable schema) |
| `/ga4 conversions <property-id>` | Key events configuration audit |
| `/ga4 attribution <property-id>` | Channel attribution at each funnel step |
| `/ga4 quality <property-id>` | Data quality and integrity check |
| `/ga4 property <property-id>` | Property configuration audit |
| `/ga4 benchmarks [--vertical V]` | Inspect bundled industry benchmark bands |

Write / config commands (need `analytics.edit` scope):

| Command | What it does |
|---------|-------------|
| `/ga4 events-edit <property-id> [--stream <id>]` | Add, modify, delete EventEditRule / EventCreateRule |
| `/ga4 audiences <property-id>` | Create, list, archive audiences |
| `/ga4 custom-defs <property-id>` | Add or archive custom dimensions and metrics |
| `/ga4 key-events <property-id>` | Create or delete key events (conversions) |

Local-definition commands (no API write):

| Command | What it does |
|---------|-------------|
| `/ga4 segment-defs ...` | Save / list / delete reusable segment filter expressions |
| `/ga4 report ...` | Save / list / run custom Data API reports |

Auth:

| Command | What it does |
|---------|-------------|
| `/ga4 auth` | Print the gcloud command to authenticate (or run OAuth fallback) |
| `/ga4 properties` | List accessible GA4 properties |

## Command Routing

| Input | Route to |
|-------|----------|
| `audit <id>` | ga4-audit skill |
| `context <id>` | ga4-context skill |
| `funnel <id>` | ga4-funnel skill |
| `segments <id>` | ga4-segments skill |
| `events <id>` | ga4-events skill |
| `conversions <id>` | ga4-conversions skill |
| `attribution <id>` | ga4-attribution skill |
| `quality <id>` | ga4-quality skill |
| `property <id>` | ga4-property skill |
| `benchmarks [--vertical V]` | Run `python scripts/ga4_benchmarks.py` |
| `events-edit <id> ...` | ga4-events-edit skill |
| `audiences <id> ...` | ga4-audiences skill |
| `custom-defs <id> ...` | ga4-custom-defs skill |
| `key-events <id> ...` | ga4-key-events skill |
| `segment-defs ...` | ga4-segment-defs skill |
| `report ...` | ga4-custom-report skill |
| `auth` | Run `python scripts/ga4_auth.py --adc` (or `--oauth` as fallback) |
| `properties` | Run `python scripts/ga4_auth.py --properties` |

## Natural Language Routing

For ad-hoc queries without explicit commands:
- "Where are users dropping off in the funnel?" -> ga4-funnel
- "Why is segment X converting lower?" -> ga4-segments
- "Are my events firing correctly?" -> ga4-events
- "Are my key events configured right?" -> ga4-conversions
- "Which channel converts best?" -> ga4-attribution
- "Is my GA4 data trustworthy?" -> ga4-quality
- "Audit my GA4 setup" -> ga4-property or ga4-audit (full)
- "Run a full analysis" -> ga4-audit
- "What does this property do / what's the site" -> ga4-context
- "How does this compare to the industry" -> ga4-benchmarks (or part of ga4-audit)
- "Rename an event / merge duplicate events" -> ga4-events-edit
- "Build an audience" -> ga4-audiences
- "Save this filter as a reusable segment" -> ga4-segment-defs
- "Set up a weekly report / build a custom report" -> ga4-custom-report
- "Add a custom dimension / archive an old metric" -> ga4-custom-defs
- "Mark this event as a key event" -> ga4-key-events

## Authentication

Before any analysis command, verify auth:
```bash
python scripts/ga4_auth.py --check
```

If auth fails, prefer Google's own ADC path — install gcloud and run:

```bash
python scripts/ga4_auth.py --adc          # prints the gcloud command
python scripts/ga4_auth.py --adc --write  # same, but include analytics.edit
```

Run the printed command, then `--check` again. For write features
(`events-edit`, `audiences`, `custom-defs`, `key-events`) the scope must
include `analytics.edit`.

Fallback (no gcloud available, e.g. CI):

```bash
python scripts/ga4_auth.py --oauth --client-secret-file <path>
```

Credentials sources, tried in order:
1. `GOOGLE_APPLICATION_CREDENTIALS` env var (service account / external account)
2. gcloud user ADC at `~/.config/gcloud/application_default_credentials.json`
3. Legacy OAuth at `~/.claude/ga4-credentials.json`

## Multi-Property

GA4 user credentials can access multiple properties. List them with:
```bash
python scripts/ga4_auth.py --properties
```

If the user has multiple properties configured, prompt which property to analyze.

## Reference Files

Load on-demand as needed (do NOT load all at startup):
- `references/recommended-events.md`: GA4 e-commerce event spec and required parameters (preset)
- `references/quotas.md`: Data API and Admin API quota tiers and backoff strategy
- `references/sampling-thresholds.md`: When GA4 samples, how to detect, mitigation

## Date Ranges

Default date ranges per analysis type:
- Funnel, segments, conversions, attribution, property: **28 days** (4 full weeks, controls weekday seasonality)
- Events (data quality sampling): **7 days**
- Override with `--days N` on any command

## Funnel Definition

The funnel skill accepts arbitrary `--steps event1,event2,...`. A
convenience preset for the e-commerce purchase funnel is available:

```
view_item -> add_to_cart -> begin_checkout -> add_payment_info -> purchase
```

The `ga4-events` agent validates that each step in any chosen funnel exists
and fires correctly. For e-commerce flows, an opt-in `--check-postpayment`
flag detects events that fire after a payment-gateway redirect-back and
suggests dropping them from the funnel.

## Currency

Reports use the property's own configured currency by default. The
`normalize_currency` helper in `ga4_utils.py` converts to a target currency
when comparing across properties; pass `--base-currency <code>` to set the
target (default: `USD`).

## Benchmarks

Findings that include a `metric` / `metric_value` pair are auto-enriched
with industry-benchmark verdicts by `scripts/ga4_benchmarks.py`. The
benchmark vertical is read from the property context (`ga4-context`),
overridable via `--vertical`. Available verticals: ecommerce, saas,
media, lead_gen, finance, travel, education, nonprofit, other.

## Markdown output

Audit and custom-report runs default to plain markdown (no emoji). The
report includes a Property Context section (from `ga4-context`), the
data-confidence label, benchmark verdicts inline with findings, and a
collapsed raw-JSON appendix per agent. Pass `--format html` or
`--format pdf` for the other renderings.

## After Analysis

After any analysis command, offer:
- "Generate a custom report? Use `/ga4 report run <name>`"
- "Run a full audit? Use `/ga4 audit <property-id>`"
