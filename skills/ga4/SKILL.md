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
| `/ga4 benchmarks [--vertical V]` | Inspect bundled heuristic bands and evidence status |

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
| `conversions <id>` | Verify auth, spawn `ga4-conversions` agent (see Consolidated read commands) |
| `attribution <id>` | Verify auth, spawn `ga4-attribution` agent (see Consolidated read commands) |
| `quality <id>` | Verify auth, spawn `ga4-quality` agent (see Consolidated read commands) |
| `property <id>` | Verify auth, spawn `ga4-property` agent |
| `benchmarks [--vertical V]` | Run `python scripts/ga4_benchmarks.py` |
| `events-edit <id> ...` | ga4-events-edit skill |
| `audiences <id> ...` | ga4-audiences skill |
| `custom-defs <id> ...` | ga4-custom-defs skill |
| `key-events <id> ...` | ga4-key-events skill |
| `segment-defs ...` | ga4-segment-defs skill |
| `report ...` | ga4-custom-report skill |
| `auth` | Run `python scripts/ga4_auth.py --adc` (or `--oauth` as fallback) |
| `properties` | Run `python scripts/ga4_auth.py --properties` |

## Consolidated read commands

These commands route straight from this router to their agent (there is no
separate skill file). Verify auth first in every case
(`python scripts/ga4_auth.py --check`).

- **quality**: spawn the `ga4-quality` agent. It emits a confidence label
  (High / Medium / Low / Very Low) that downstream agents reference. Save the
  label to `.ga4-cache/<property-id>/quality-confidence.json` so later runs
  can read it without re-running the quality audit.
- **conversions**: spawn the `ga4-conversions` agent. After analysis, if at
  least one key event is configured, offer: "Want to see attribution at each
  funnel step? Use `/ga4 attribution <property-id>`".
- **attribution**: first check at least one key event is configured
  (`python scripts/ga4_admin.py --property <id> --key-events --json`); if none,
  return "no key events configured, configure at least `purchase` as a key
  event first". Otherwise spawn the `ga4-attribution` agent. Default window 28
  days; for conversion-lag analysis the agent may extend to 90 days internally.
- **property**: spawn the `ga4-property` agent.

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
- Override with `--days N` on date-window commands; configuration reads have no date window.

## Funnel Definition

The funnel skill accepts arbitrary `--steps event1,event2,...`. A
convenience preset for the e-commerce purchase funnel is available:

```
view_item -> add_to_cart -> begin_checkout -> add_payment_info -> purchase
```

The `ga4-events` agent validates that each step in any chosen funnel exists
and fires correctly. For e-commerce flows, an opt-in `--check-postpayment`
flag compares aggregate event counts. Treat its result as a hypothesis;
counts do not establish event order. Review omitted steps explicitly.

## Currency

Reports use the property's configured currency. There is no `--base-currency`
CLI flag. `ga4_utils.normalize_currency` is a Python helper with a static
mid-2025 fallback table; it is not an automatic reporting conversion or a
current exchange-rate source.

## Benchmarks

Findings that include a `metric` / `metric_value` pair are auto-enriched
with unverified heuristic comparisons by `scripts/ga4_benchmarks.py`. The
benchmark vertical is read from the property context (`ga4-context`),
overridable via `--vertical`. Available verticals: ecommerce, saas,
media, lead_gen, finance, travel, education, nonprofit, other.

## Markdown output

The audit CLI defaults to markdown. Saved custom reports default to JSON;
request `--format md` explicitly. The standalone report renderer defaults
to HTML. The
report includes a Property Context section (from `ga4-context`), the
data-confidence label, benchmark verdicts inline with findings, and a
collapsed raw-JSON appendix per agent. Pass `--format html` or
`--format pdf` for the other renderings.

## After Analysis

After any analysis command, offer:
- "Generate a custom report? Use `/ga4 report run <name>`"
- "Run a full audit? Use `/ga4 audit <property-id>`"

The 15-minute query cache uses atomic replacement. Empty results are cached;
corrupt, expired, unreadable and error-bearing entries are misses. Failed
cache writes do not fail API reads. If disk invalidation fails after an Admin
write, a warning is emitted and this process bypasses that entry; other
processes can remain stale until expiry. Concurrent read/write races and
separation by credential principal remain open work in docs/ROADMAP.md.

Benchmark tables and comparisons are labeled `source_status: unverified_heuristic`.
Their p25/p50/p75 names are legacy band labels, not verified population
percentiles. Do not present them as evidence of industry performance or use
them alone to set severity. See [the source review](../../docs/ROADMAP.md).

Cache freshness tolerates up to one second of filesystem clock skew; larger
future timestamps and entries aged 15 minutes or more are misses.

Read the selected reporting identity with
`python scripts/ga4_admin.py --property X --reporting-identity --json`
or MCP `reporting_identity(property_id)`. This alpha read uses the 15-minute
cache and response scrubber. Older SDKs without the method return
`status: unsupported`. Report the selected mode as context for user counts;
there is no identity write or universal recommendation to switch modes.

Google clients: require Data 0.18.16+ and Admin 0.23.0+ (both below 1.0).
Supported Admin calls use explicit beta clients and matching message types;
alpha-only methods keep explicit alpha imports. Reporting identity needs
Admin 0.25.0+ and otherwise returns `status: unsupported`. CI tests minimum
and current Data/Admin clients; newer optional response fields remain optional.

Discover report fields with `ga4_data.py --property X --metadata --json` or
MCP `report_metadata(property_id)`. For an explicit Core report preflight,
use `ga4_data.py --property X --check-compatibility --metrics sessions --dimensions date --json`
or MCP `check_compatibility(property_id, metrics, dimensions)`.
Compatibility is uncached and does not validate funnels or realtime. Metadata
uses the 15-minute cache; successful custom-definition and key-event writes
invalidate it. Both reads scrub responses. No report triggers these reads
automatically. See docs/REPORT_FIELDS.md for filters and limits.

Use ga4_admin.py --property ID --user-provided-data to read alpha UPD settings, or --consent-diagnostics for UPD and reporting identity plus remaining manual evidence. MCP exposes user_provided_data_settings and consent_diagnostics. Settings do not prove event consent; inspect tag/CMP configuration and aggregate export privacy_info separately.

Advertising conversions use the separate ga4_advertising.py alpha adapter and MCP advertising_report/conversion_metadata. Require explicit dates, select DATA_DRIVEN or LAST_CLICK, and discover conversionActions IDs from alpha metadata. Do not substitute key events or session-acquisition metrics. Check complete and section_verified; eligibility and live access remain unverified. Reads are bounded and uncached. See docs/ADVERTISING.md.

BigQuery evidence is optional: install .[bigquery] and use ga4_bigquery.py with explicit billing/source projects, dataset, location and dates. It estimates fixed aggregate queries by default; --execute can incur charges and requires explicit user authorization. Enforce --max-bytes (default 1 GiB), inspect unknown job outcomes before resubmitting, and never export individual rows. MCP bigquery_dry_run cannot execute. See docs/BIGQUERY.md for parameter coverage, consent, freshness and first-entry funnel semantics.

Use ga4_explore.py --realtime for uncached minute-range reports or --comparisons JSON with --date-ranges JSON for named same-property groups and dates. MCP exposes realtime_report/comparison_report. Realtime has no pagination; inspect complete and quota. Minute bounds over 29 require GA360. Preserve comparison/date columns and never sum overlapping user populations. See docs/EXPLORATION.md.

Read dated context with ga4_admin.py --annotations or --change-history, supplying --property, --start-date and --end-date; history also requires --account. MCP tools are reporting_annotations/change_history. These bounded, uncached reads are not causal evidence. History requires analytics.edit scope despite being read-only, and omits actor emails and before/after snapshots. Older clients may not support annotations. See docs/CHANGE_HISTORY.md.

Account/property discovery through ga4_auth.py --properties also uses the bounded read transport, including every account-summary page. Quota failures are not retried and partial lists are not returned as complete.
