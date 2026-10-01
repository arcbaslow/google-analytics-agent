# CLAUDE.md

Instructions for Claude Code working with `google-analytics-agent`. Most
of the universal guidance lives in [AGENTS.md](AGENTS.md); this file
covers Claude Code-specific notes only.

## Skills and subagents

Claude Code loads `skills/ga4/SKILL.md` as the top-level router. It
exposes `/ga4 <command>` and routes to:

- `conversions`, `attribution`, `quality`, `property` are router-hosted commands with no skill directory of their own (the router verifies auth and spawns the matching agent directly).

The `ga4-audit` orchestrator runs context first, quality and property checks
in parallel, then events before the remaining analysis. Every other audit
command can call `ga4-context` first when it needs the inferred vertical
for benchmark enrichment.

Each skill either calls a Python script directly or spawns a subagent
defined under `agents/`. After events, funnel, key-event and segment checks
run in parallel. Attribution follows only when key events are configured.
This ordering matches the Python orchestrator.

## When to use Bash vs the Skills

Skills are sugar for the same Python adapters. If a user invokes `/ga4
audit`, use the skill. If a user asks a one-off question that maps to a
single script flag (e.g. "list the audiences on property X"), call the
script directly via the Bash tool instead of spawning a subagent for it:

```
python scripts/ga4_admin.py --property X --list-audiences --json
```

## Confirmation before writes

For every Admin API write, the subagent (or you, if invoking directly)
must show the resolved JSON or change, ask `y/N`, then run the command.
Skill bodies wire this in; don't bypass.

## Auth

Default path is gcloud Application Default Credentials:

```
python scripts/ga4_auth.py --check
python scripts/ga4_auth.py --adc            # prints the gcloud command
python scripts/ga4_auth.py --adc --write    # with analytics.edit
```

Run the printed command, then `--check` again. Write features need the
`analytics.edit` scope.

## Reports and benchmarks

The audit CLI defaults to markdown. The standalone renderer defaults to
HTML; select markdown with `scripts/ga4_report.py --format md`. Saved custom
reports default to JSON; select `--format md` explicitly. The report attaches the property
context (from `ga4-context`), the data-confidence label, and benchmark
band verdicts to every finding that carries a `metric` / `metric_value`
pair. Benchmarks live in `scripts/ga4_benchmarks.py` (nine verticals).
Pass `--format html` or `--format pdf` when the user wants those.

## Style for commits and output

- No marketing copy. Plain factual statements.
- No `feat:` / `fix:` / `chore:` Conventional Commits prefixes in commits.
- No `Co-Authored-By:` trailers, no `Generated with...` footers, no emoji.
- Commit message style: short imperative sentence, sentence-case acceptable.

## Asset role (2026-08)

Shipped and public. Maintenance mode: bugfixes, Google API version bumps,
and docs only - the active OSS build slot belongs to capi-kit. Role:
portfolio proof for the measurement practice; the README should keep a link
to Good Labs services. New features need an explicit owner decision.

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

Funnel reports accept 2-10 unique steps and retain missing steps by default. --drop-missing explicitly changes the requested funnel. --check-postpayment is advisory and never removes steps. Validation uses the complete requested date window. Numbered API step names are normalized; breakdown rates use the named dimension and RESERVED_TOTAL rows, never summed segment populations. Missing totals or malformed rows produce an error instead of fabricated rates.

Read operations share a 100-request budget, including retries and Admin pages; a full audit shares it across workers. Python callers can use ga4_transport.read_budget(max_requests=N), with N from 1 to 1000. Transient reads have at most three attempts with a 30-second RPC timeout and GAPIC retries disabled. Auth, permission and quota failures are not retried. CLI/MCP and partial Admin errors expose stable categories; partial failures are not successful checks or cached results. Admin writes do not use this retry helper.

API cache entries expire after 15 minutes and are isolated by resolved account/token identity, granted or declared scopes, and quota project. Only hashes are stored; credential files are never opened by the cache. Unidentified clients use a process-local random namespace. Every successful Admin write invalidates all API queries for that property across namespaces. Locked generation checks prevent older in-flight reads from refilling invalidated entries. Cache I/O failure disables reuse in the current process; other processes can remain stale until expiry if the shared disk cannot be updated. Role revocations cannot be verified offline. Context uses a separate 24-hour expiry and the same identity isolation; --refresh still forces refresh. Run python scripts/ga4_utils.py --cleanup-cache to remove only expired toolkit cache JSON files, including legacy entries; unrelated files and generation markers are retained.

Use ga4_admin.py --property ID --user-provided-data to read alpha UPD settings, or --consent-diagnostics for UPD and reporting identity plus the remaining manual evidence. MCP exposes user_provided_data_settings and consent_diagnostics. Older clients return unsupported for missing methods. Disabled boolean values are preserved. These reads do not establish per-event consent, consent-mode correctness, modeled-data completeness or legal compliance; inspect tag/CMP configuration and aggregate export privacy_info separately. No consent setting is changed.

Key-event capacity uses the API custom flag: default key events do not consume the custom limit. At the Standard boundary, creation reads the current property service level: Standard permits 30 custom key events and Analytics 360 permits 50. Unknown service levels defer enforcement to the API. Auth --check --write reports edit-scope evidence and rejects missing or unknown edit scopes; declared scopes are distinguished from granted scopes and do not establish a property role. Legacy OAuth never adds unconsented scopes to stored credentials. Each write still requires its own y/N approval.

MCP propose_admin_write saves one exact Admin proposal for an expiring, single-use terminal approval. The user must run its approval_command and answer the existing y/N prompt themselves; agents must not supply approval. admin_proposal_status only reads the outcome. There is no MCP execute tool, and confirm=true remains insufficient. Refused or failed proposals cannot be replayed; applied:null means the result is unknown. See docs/APPROVALS.md.

Advertising conversions use the separate ga4_advertising.py alpha adapter and MCP advertising_report/conversion_metadata. Require explicit dates, select DATA_DRIVEN or LAST_CLICK, and discover conversionActions IDs from alpha metadata. Do not substitute key events or session-acquisition metrics. Check complete and section_verified; eligibility and live access remain unverified. Reads are bounded and uncached. See docs/ADVERTISING.md.

BigQuery evidence is optional: install .[bigquery] and use ga4_bigquery.py with explicit billing/source projects, dataset, location and dates. It estimates fixed aggregate queries by default; --execute can incur charges and requires explicit user authorization. Enforce --max-bytes (default 1 GiB), inspect unknown job outcomes before resubmitting, and never export individual rows. MCP bigquery_dry_run cannot execute. See docs/BIGQUERY.md for parameter coverage, consent, freshness and first-entry funnel semantics.

Use ga4_explore.py --realtime for uncached minute-range reports or --comparisons JSON with --date-ranges JSON for named same-property groups and dates. MCP exposes realtime_report/comparison_report. Realtime has no pagination; inspect complete and quota. Minute bounds over 29 require GA360. Preserve comparison/date columns and never sum overlapping user populations. See docs/EXPLORATION.md.
