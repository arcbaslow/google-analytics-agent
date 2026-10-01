# AGENTS.md

Instructions for agentic coding tools (Codex, Aider, Continue, etc.)
working with `google-analytics-agent`. The Claude Code runtime uses
`CLAUDE.md`; Gemini CLI uses `GEMINI.md`; this file covers everything
else.

## What this project is

A multi-agent toolkit for Google Analytics 4. The interface is a set of
Python scripts under `scripts/` that call the GA4 Data and Admin APIs.
Skills and subagents in `skills/` and `agents/` are Claude Code-specific
sugar; the Python scripts are the source of truth and work the same
everywhere.

## Authentication (do this first)

The user authenticates once via gcloud Application Default Credentials.
You should never ask the user to register their own Cloud OAuth client
unless they explicitly cannot install gcloud.

```
python scripts/ga4_auth.py --check          # verify creds resolve
python scripts/ga4_auth.py --adc            # print the gcloud command if not authed
python scripts/ga4_auth.py --adc --write    # same, with analytics.edit
python scripts/ga4_auth.py --properties     # list accessible properties
```

If `--check` fails, print the output of `--adc` (or `--adc --write` if the
user wants write features) and tell them to run that gcloud command.

Write features (`events-edit`, `audiences`, `custom-defs`, `key-events`)
need the `analytics.edit` scope.

## Universal CLI

Every feature is a Python CLI. Same flags across runtimes.

### Context

| Command | Purpose |
|---------|---------|
| `python scripts/ga4_context.py --property X --analyze --json` | Extract web-stream URL, fetch homepage/robots/sitemap, infer vertical/platform/framework, cache result |
| `python scripts/ga4_context.py --property X --refresh --json` | Force re-analysis |
| `python scripts/ga4_context.py --property X --show --json` | Print cached context |
| `python scripts/ga4_context.py --url https://example.com --analyze --json` | One-off URL analysis |

### Benchmarks

| Command | Purpose |
|---------|---------|
| `python scripts/ga4_benchmarks.py --list-verticals` | List shipped verticals |
| `python scripts/ga4_benchmarks.py --vertical ecommerce --all-metrics` | Print every metric's band for a vertical |
| `python scripts/ga4_benchmarks.py --compare bounce_rate 0.72 --vertical ecommerce` | Single-value comparison |

### Reports

| Command | Purpose |
|---------|---------|
| `python scripts/ga4_report.py --property X --inputs a.json,b.json --format md --output audit.md` | Render markdown audit (no emoji) with context + benchmarks |
| `python scripts/ga4_report.py --property X --inputs ... --format html --output audit.html` | HTML version |
| `python scripts/ga4_report.py --property X --inputs ... --format pdf --output audit.pdf` | PDF via WeasyPrint |
| `python scripts/ga4_definitions.py --run-report NAME --property X --format md --output report.md` | Markdown for a saved custom report |

### Read

| Command | Purpose |
|---------|---------|
| `python scripts/ga4_data.py --property X --report eventCount --dimensions eventName --days 28 --json` | Generic runReport |
| `python scripts/ga4_data.py --property X --funnel-report --steps event1,event2,event3 --days 28 --json` | Funnel report |
| `python scripts/ga4_events.py --property X --list-events --days 7 --json` | Distinct events |
| `python scripts/ga4_events.py --property X --check-events e1,e2 --days 7 --json` | Presence check |
| `python scripts/ga4_events.py --property X --event-params purchase --days 7 --json` | Per-parameter coverage for one event |
| `python scripts/ga4_funnel.py --property X --steps e1,e2,e3 --days 28 --json` | Funnel with rates and leakiest-step |
| `python scripts/ga4_admin.py --property X --details --json` | Property summary |
| `python scripts/ga4_admin.py --property X --streams --json` | Data streams |
| `python scripts/ga4_admin.py --property X --custom-defs --json` | Custom dimensions and metrics |
| `python scripts/ga4_admin.py --property X --key-events --json` | Key events |
| `python scripts/ga4_admin.py --property X --attribution-settings --json` | Attribution model |
| `python scripts/ga4_admin.py --property X --list-audiences --json` | Audiences |
| `python scripts/ga4_admin.py --property X --stream Y --list-event-rules --json` | EventEditRule / EventCreateRule |

### Write (need `analytics.edit` scope)

| Command | Purpose |
|---------|---------|
| `python scripts/ga4_admin.py --property X --stream Y --add-edit-rule path.json --json` | Create an EventEditRule from a JSON definition |
| `python scripts/ga4_admin.py --property X --stream Y --add-create-rule path.json --json` | Create an EventCreateRule |
| `python scripts/ga4_admin.py --rule-name <full> --delete-edit-rule --json` | Delete an EventEditRule |
| `python scripts/ga4_admin.py --property X --create-audience path.json --json` | Create an audience |
| `python scripts/ga4_admin.py --audience-name <full> --archive-audience --json` | Archive an audience |
| `python scripts/ga4_admin.py --property X --add-custom-dim --parameter-name P --display-name D --scope EVENT --json` | Create a custom dimension |
| `python scripts/ga4_admin.py --property X --add-custom-metric --parameter-name P --display-name D --measurement-unit STANDARD --json` | Create a custom metric |
| `python scripts/ga4_admin.py --archive-custom-dim <full> --json` | Archive a custom dimension |
| `python scripts/ga4_admin.py --property X --add-key-event purchase --json` | Mark an event as a key event |
| `python scripts/ga4_admin.py --delete-key-event <full> --json` | Unmark a key event |

### Local definitions (no API write)

| Command | Purpose |
|---------|---------|
| `python scripts/ga4_definitions.py --save-segment "name" --field F --op OP --value V` | Save a reusable filter expression |
| `python scripts/ga4_definitions.py --save-segment-json "name" path.json` | Save a raw FilterExpression |
| `python scripts/ga4_definitions.py --list-segments` | List stored segments |
| `python scripts/ga4_definitions.py --save-report name path.json` | Save a custom report definition |
| `python scripts/ga4_definitions.py --list-reports` | List stored reports |
| `python scripts/ga4_definitions.py --run-report name --property X [--format md\|html\|pdf\|json\|csv] [--segment NAME] [--output path]` | Run a stored report |

## Confirmation before writes

For every Admin API write (audiences, event rules, custom defs, key
events), print the resolved JSON or proposed change first, then ask the
user `y/N` before executing. Do not chain writes without confirmation.

## Funnels

Use an explicit ordered list of event names supplied by the user via `--steps event1,event2,...`. The e-commerce purchase funnel
(`view_item -> add_to_cart -> begin_checkout -> add_payment_info ->
purchase`) is the CLI default when `--steps` is omitted and is also available via
`--preset ecomm` in `ga4_funnel.py`. Missing steps are currently dropped;
review the returned step list before interpreting the rates.

The `--check-postpayment` flag (opt-in, e-commerce-only) runs a heuristic
that compares `add_payment_info` and `purchase` counts. It cannot establish
event order or prove a payment-gateway redirect problem. It is off by default.

## Caching and PII

The scripts cache responses on disk at `~/.claude/ga4-cache/` for 15
minutes per unique query. Admin writes drop the cached reads they change,
so subsequent reads normally refresh it; concurrent requests and disk failures
can still leave another process stale. PII keys (`email`, `phone`, ID-like fields) are
scrubbed from responses before any analysis. Both are implemented in
`scripts/ga4_utils.py`.

## When the user asks for analysis

Default workflow:

1. Run `ga4_auth.py --check` first; if it fails, surface the `--adc`
   command and stop.
2. Run `ga4_context.py --property X --analyze --json` to profile the
   live site (vertical, platform, framework, sitemap). Cache result for
   downstream agents.
3. For broad audits ("audit my GA4", "give me an overview"), run the
   quality and property checks next, then events, then funnel / key-event /
   segment checks in parallel. Attribution follows when key events exist.
4. For targeted questions, call the relevant script directly.
5. Parse JSON output. Use `--json` where supported, or `--format json`
   for the audit and saved reports. Local-definition lists already emit JSON.
6. Pass each agent's structured output to `ga4_report.py --format md`
   for the final user-facing artifact. Use the inferred vertical from
   step 2 (or an explicit override) so findings carry benchmark verdicts.
7. Finish with a prioritized action plan: Critical > High > Medium > Low.

### Benchmark-aware findings

When emitting an analysis finding that has a comparable numeric (bounce
rate, engagement rate, conversion rate, direct share, sampling, etc.),
include both `metric` and `metric_value` keys on the finding object:

```json
{"severity": "High", "title": "...", "detail": "...",
 "metric": "direct_share", "metric_value": 0.42}
```

The reporter calls `ga4_benchmarks.compare()` against the inferred
vertical and appends a band + interpretation phrase to the finding line.

## When the user asks for a write

1. Identify the smallest change that satisfies the ask.
2. Show the resolved JSON / proposed change.
3. Ask `apply? [y/N]`.
4. Run the command on `y`, skip on `n`.
5. Print the resource name returned by the API.

## Style

- No marketing copy in output or commits.
- No `feat:` / `fix:` / `chore:` Conventional Commits prefixes.
- No `Co-Authored-By:` trailers, no `Generated with...` footers.
- Plain imperative commit messages, sentence-case acceptable.
- Don't generalize the tool's framing toward any single industry — funnel
  analysis here works for e-commerce, lead-gen, SaaS, content, anything
  expressible as an ordered list of GA4 events.

Every Admin write is gated inside `ga4_admin.py`: it prints a scrubbed proposal
and asks `y/N` for that operation. Run it in an interactive terminal; piped
input, EOF and cancellation refuse the write. There is no bypass flag. MCP
stdio tools provide previews; `confirm=true` returns `confirmation_required`
without terminal approval. Never chain writes.

PII scrubbing also applies to Admin responses, cached data, context, MCP and
rendered reports. Sensitive camelCase/custom-dimension keys and encoded email
values are redacted; numeric metrics and GA resource names are retained.
Scrubbing is a defensive filter, not a guarantee that arbitrary free text is
anonymous. Saved-segment reports use one normal cached, scrubbed Data API call.

The 15-minute query cache uses atomic replacement. Empty results are cached;
corrupt, expired, unreadable and error-bearing entries are misses. Failed
cache writes do not fail API reads. If disk invalidation fails after an Admin
write, a warning is emitted and this process bypasses that entry; other
processes can remain stale until expiry. Concurrent read/write races and
separation by credential principal remain open work in docs/ROADMAP.md.

Property retention is read from `getDataRetentionSettings`. Enhanced
measurement recognizes the API's snake_case web-stream fields. Data filters
and Search Console links return `status: unsupported`: inspect these in GA4
Admin, and never interpret an unavailable check as an empty configuration.

The context fetcher validates every redirect destination before following it.
Private, loopback, link-local and non-HTTP(S) redirects are refused. DNS
rebinding between address validation and connection remains an open limitation.

Quality output includes `checks_complete` and `incomplete_checks`. Failed or
empty checks cap confidence at low; a measured zero sample rate stays zero.
`ga4_data.py --include-metadata` retains available thresholding, empty-result,
restriction and truncation details. A thresholding flag alone does not prove
that rows were removed. New metadata fields depend on the installed SDK.

Benchmark tables and comparisons are labeled `source_status: unverified_heuristic`.
Their p25/p50/p75 names are legacy band labels, not verified population
percentiles. Do not present them as evidence of industry performance or use
them alone to set severity. See [the source review](docs/ROADMAP.md).

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

Parameter aggregate metrics return `coverage_pct: null` with `status: not_measurable`; positive revenue is not proof of complete tagging. Segment audits use the API `sessionKeyEventRate` and label findings `session_key_event_rate`.

Reports accept --limit (default 10000, maximum 250000), --page-size and --max-pages (default 10, maximum 100), --start-date/--end-date, --metric-filter JSON and --order-bys JSON. Responses expose complete, pages_fetched and incomplete_reason; do not treat partial results as totals. Partial results are not cached. Saved reports validate their schema, apply these options plus dimension_filter, and honor default_format unless --format overrides it. A saved segment is ANDed with the report filter. See docs/REPORT_FIELDS.md.
