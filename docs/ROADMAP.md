# Roadmap

Reviewed 2026-09-30 against master `aec65cb` (package 0.5.3). File and line
references below refer to that baseline, not to later edits on `roadmap-work`.
The owner authorized this bounded feature run. Writes still require one
reviewed proposal and `y/N` per operation. No live property was used.

Effort estimates are engineering days including mocked tests and documentation.
Risk describes the change, not the severity of the existing defect. Now is the
initial implementation scope for this branch. The owner's follow-up to work
through the roadmap authorizes the bounded Next work recorded below. Larger
design and semantic questions retain their stated decision requirements.

## Implementation status

All Now items were completed locally on `roadmap-work`. The entries below
retain the baseline problem and planned scope so the changes can be reviewed.
The first two Next items are now implemented: supported Admin calls use explicit
beta clients and matching message types, with a minimum/current dependency
matrix in CI, and explicit CLI/MCP reads expose report metadata and Core
compatibility. Later items remain proposals. See [verification](VERIFICATION.md)
for the baseline/final checks, environment and limits of each run.

| Item | Implementation commit |
| --- | --- |
| N1: interactive approval for all 15 Admin writers | `b0caabd` |
| N2: response scrubbing and one filtered saved-report path | `7b3cf94` |
| N3: cache recovery, empty results, errors and column order | `3e5d4d9` |
| N3 follow-up: reproduced Windows timestamp skew | `ccb0c61` |
| N4: real Admin resource contracts and unsupported checks | `15dab92` |
| N5: redirect validation | `af730fc` |
| N6: incomplete quality checks and optional metadata | `583f771` |
| N7: wrapper corrections and benchmark evidence labels | `d36ad80` |
| N8: read-only reporting identity | `091d723` |
| Next: verified Google clients and explicit API surfaces | `74a3335` |

The final cache read accepts up to one second of filesystem clock skew.
A synthetic Windows probe reproduced negative ages as small as 0.24
microseconds; deterministic tests cover skew, future timestamps and expiry.
No live API was involved in that reproduction.

## Baseline and evidence

Installed `.[dev]` in a fresh venv using Python 3.12.14 on Windows.
`.github/workflows/tests.yml` requires lint, format, mypy and coverage on
Python 3.10–3.13. Locally: Ruff passed; format passed (36 files); mypy passed
(13 source files); pytest passed (366 tests, 95.41% coverage, floor 93%).
Coverage includes tests. Production-only line coverage from the same run was
91.68% (2249/2453 statements). Mypy leaves untyped function bodies unchecked.

Tests ran with an external pytest guard: synthetic credential-file IO stayed
in memory, ADC discovery was disabled, and socket connections were blocked.
No credentials or `.secrets/` were inspected or staged. See the final review
record for commands and results. The other Python versions and Ubuntu were
not run locally.

Every adapter has tests. Coverage alone does not establish API compatibility:
`test_ga4_admin_read.py` stubs serialization and uses unrestricted mocks.
Baseline uncovered paths include event-rule reorder/delete-create, audience
get/metadata update, several CLI dispatch branches, and PDF rendering. Existing
proto integration tests cover several writes, but not every request contract.
The review read all adapters, tests relevant to these paths, runtime instructions,
skills, agents, hooks (currently empty), workflow files and docs.

## Now

### N1. Enforce confirmation at the Admin adapter boundary

Direct Python and CLI writes currently have no prompt; MCP `confirm=true` is
caller-controlled and can execute without an earlier preview. Add a shared
gate to every existing write, print the proposed operation and resolved
arguments, require an interactive `y/N`, and reject ambiguous CLI actions.
Fail closed on EOF, interruption or noninteractive input. MCP stdio cannot
consume terminal input safely: preserve previews and return a structured
confirmation-required result for attempted writes. Do not add a bypass flag.

Why: an agent mistake must not alter audiences, rules or key events silently.
Evidence: `scripts/ga4_admin.py:258`, `scripts/ga4_admin.py:483`,
`scripts/ga4_mcp.py:206`, and `SECURITY.md:16`. Effort: 1–2 days.
Risk: medium; unattended writes intentionally stop working. Test every writer
for rejection and acceptance, including direct imports and MCP attempts.

### N2. Close response and cache privacy gaps

Scrub Admin reads/writes, cache reads/writes, context, rendered reports, MCP
responses and CLI errors. Route saved-segment reports through `run_report`
once; they currently make an unfiltered request and then use an unsanitized
private-client path. Normalize camelCase and custom-dimension PII keys; cover
encoded emails and numeric identifiers in known sensitive fields without
destroying numeric metrics or GA resource names.

Why: exports and cached property metadata can contain personal information.
Evidence: `scripts/ga4_utils.py:75`, `scripts/ga4_admin.py:68`,
`scripts/ga4_definitions.py:166`, `scripts/ga4_definitions.py:216`,
`scripts/ga4_context.py:56`, `scripts/ga4_report.py:124`,
`scripts/ga4_mcp.py:71`. Effort: 2–3 days. Risk: medium; false positives and
missed unstructured identifiers remain possible. Tests must cover cached,
uncached, segmented, error, JSON, CSV, Markdown and HTML paths.

### N3. Make the 15-minute cache safe to reuse

Use atomic replacement; treat malformed/unreadable/expired cache files as
misses; cache empty lists; avoid caching errors; preserve requested column
order in report keys. Keep write invalidation explicit and test that failed
writes do not claim success. The 0.5.3 key-event/custom-definition invalidation
is present and passes tests; do not reimplement it as a new feature.

Why: interrupted cache writes and cached permission/quota failures should not
break or poison subsequent reads. Evidence: `scripts/ga4_utils.py:48`,
`scripts/ga4_utils.py:60`, `scripts/ga4_admin.py:149`,
`scripts/ga4_data.py:148`, `scripts/test_ga4_admin_write.py:170`.
Effort: 1 day. Risk: low. Cross-process invalidation races and credential
isolation are separate Next work.

### N4. Stop reporting nonexistent Admin capabilities

Detect web streams using real serialized snake_case fields. Return explicit
unsupported results for data filters and Search Console links instead of
calling nonexistent methods. Fetch retention from its own endpoint when
auditing retention, not from a nonexistent field on Property. Surface
unavailable checks as such. Keep alpha-only reads on the alpha client.

Why: property audits currently skip real checks or disguise missing API
coverage as transient failures. Evidence: `scripts/ga4_admin.py:128`,
`:149`, `:210`; `scripts/ga4_audit.py:498`; installed Admin 0.30.1 class
inspection confirms both missing methods. The [Admin reference][admin-ref]
does not list either method; [retention settings][retention] is a separate
resource. Effort: 1–2 days. Risk: low; unsupported checks remain manual.

### N5. Revalidate website redirects

The context fetcher checks the original URL but urllib follows redirects
without applying that check to the destination. Validate every redirect
before fetching it, using mocked redirect tests.

Why: a site's response must not redirect the profiler into a private network.
Evidence: `scripts/ga4_context.py:166` and
`scripts/test_ga4_context_fetch_guard.py:72`. Confirmed by reading the opener
path; no network exploit was attempted. Effort: 0.5 day. Risk: low; DNS
rebinding between validation and connection remains a separate transport
design question.

### N6. Report incomplete quality checks honestly

Failed sampling/source queries currently leave zero defaults and produce
high confidence. A zero sample rate is also replaced by 1.0 through `or`.
Record incomplete checks, lower confidence, and retain a genuine zero.
Expose thresholding, empty reasons, restrictions and truncation metadata
with `--include-metadata`; avoid calling thresholding proof of removed rows.

Why: operators should not act on a high-confidence label when the API failed
or data is incomplete. Evidence: `scripts/ga4_audit.py:82`,
`scripts/ga4_data.py:187`, [response metadata][response-meta].
Effort: 1 day. Risk: low; metadata additions are additive. September 2026
truncation fields must be optional for older installed clients.

### N7. Correct wrapper claims and label benchmark evidence

Replace deprecated conversion names, remove unsupported flags/examples and
outdated quota/attribution advice, and reconcile the three runtime files with
the CLI. Mark benchmark results as unverified heuristics, including in report
annotations; retain numeric tables for compatibility rather than inventing
new percentiles. Update contributor check commands.

Why: wrappers must not ask agents to query nonexistent fields or present
invented population percentiles as measured evidence. Evidence:
`agents/ga4-conversions.md:18`, `agents/ga4-attribution.md:26`,
`skills/ga4-custom-report/SKILL.md:25`, `skills/ga4/SKILL.md:203`,
`scripts/ga4_benchmarks.py:9`; sources below. Effort: 1–2 days.
Risk: low; no numerical threshold changes while their intent is unresolved.

### N8. Add a read-only reporting-identity inspection

After the fixes, expose `getReportingIdentitySettings` through the Admin CLI
and MCP with the same cache and scrubbing as other reads. Report the returned
identity rather than recommending one universally. No identity write.

Why: identity choice helps explain differences in user counts and modeled
reports. Evidence: [official alpha method][identity-api], absent from
`scripts/ga4_admin.py` at baseline. Effort: 0.5–1 day. Risk: low; alpha
availability and older client libraries need an explicit unsupported result.

## Next

On 2026-10-01 the owner authorized all remaining Next and Later implementation,
including the larger adapters and approval workflow. Rejected actions that
violate the write/privacy constraints remain rejected. Each implemented item
is marked below; live property verification remains excluded.

| Item | Operator value and evidence | Effort | Risk and reason deferred |
| --- | --- | --- | --- |
| Completed: verify minimum supported Google clients and use explicit beta clients | Reproduced missing EventEditRule/KeyEvent in Admin 0.22.0 and undecodable sampling metadata in Data 0.18.0. Require Admin 0.23.0 and Data 0.18.16; use explicit beta clients/types for supported calls. [Data library history][data-library], [Admin library history][admin-library], `pyproject.toml`, `constraints/minimum-google.txt` | 2 days | Medium; CI now covers minimum/current clients across Python 3.10–3.13. Local checks use Windows/Python 3.12 only. Identity remains optional below Admin 0.25.0 |
| Completed: metadata discovery and compatibility preflight | Explicit CLI/MCP reads expose available fields and Core compatibility. [getMetadata][metadata], [checkCompatibility][compatibility], `ga4_data.py`, [usage](REPORT_FIELDS.md) | 1–2 days | Low; metadata uses the scrubbed 15-minute cache and invalidates after custom-definition/key-event writes; compatibility is uncached. No automatic extra report request. Live custom-field availability remains unverified |
| Bounded pagination and saved-report schema | `run_report` issues one request; reports beyond the default limit are incomplete. Saved `dimension_filter`, `metric_filter`, `order_bys`, `limit`, `default_format` are stored but ignored (`ga4_data.py:127`, `ga4_definitions.py:166`). [runReport][run-report] | 2–4 days | Medium; agree on row/token limits, truncation semantics and supported definition contract first |
| Completed: correct metric meaning in parameter and cohort audits | Positive aggregate revenue is not 100% parameter coverage (`ga4_events.py:94`); `keyEvents / sessions` is event frequency, not session key-event rate (`ga4_audit.py:578`). [Schema][schema] defines `sessionKeyEventRate` | 2 days | Medium; intended metric and compatibility with current findings need a decision; leave calculations alone this run |
| Funnel result contract and missing-step policy | `_compute_rates` assumes exact step names and derives breakdown from any non-count column (`ga4_funnel.py:133`, `:218`). Missing steps are removed, changing the question. Compare real proto fixtures with [funnel response][funnel-api] | 2 days | Medium; numbered names/RESERVED_TOTAL aggregation and desired missing-step behavior need explicit fixtures and policy |
| Read error taxonomy and quota budgets | MCP handles auth but not quota uniformly; aggregate Admin errors can look like successful checks. Add structured auth/permission/quota distinctions, bounded read retries and request budgets. `ga4_mcp.py:71`, `ga4_admin.py:210`, [quotas][data-quotas] | 2–3 days | Medium; do not replay writes or stack retries on top of GAPIC defaults |
| Cache identity and concurrency | Shared cache is keyed by property/query, not principal or granted role. In-flight reads can refill stale state after invalidation. Context has no TTL. `ga4_utils.py:43`, `ga4_context.py:566` | 2–3 days | Medium; needs namespace and lock/generation design without reading credentials; separate context refresh policy from API TTL |
| Consent and user-provided-data diagnostics | Admin UPD setting is not evidence of per-event consent. Read settings and explain what requires tag inspection or export evidence. [Consent][consent], [UPD API addition][admin-news], [export privacy fields][bq-schema] | 2–3 days | Medium; no automatic consent changes and no individual-level exports |
| Key-event limits and scopes | Hardcoded 30 applies without checking service level; auth check only resolves credentials, does not verify granted edit scope. `ga4_admin.py:27`, `ga4_auth.py:153`, `ga4_audit.py:377`; [configuration limits][configuration-limits] | 1–2 days | Medium; verify standard/360 and automatically marked events before changing limit enforcement |
| MCP approval bound to a proposal | Preserve useful writes without trusting a caller's boolean. Need a human approval channel bound to exact operation, target and payload; refusal/timeout/replay tests | 3–5 days | High; changes transport contract. Until then use interactive CLI, one write at a time (N1) |
| Production coverage and contract tests | Exclude tests from the coverage denominator with a justified new floor; use real proto messages and client specs for all adapters. Baseline is 91.68% production vs 95.41% CI | 1–2 days | Low; avoid silently moving CI's floor or claiming coverage proves live API behavior |

## Later

| Item | Operator value and evidence | Effort | Risk and reason deferred |
| --- | --- | --- | --- |
| Alpha advertising conversion reports | Distinguish Ads conversions, key events and session acquisition. [Data API news][data-news] adds `conversionSpec`, model selection and metadata sections; not all properties qualify | 4–6 days | High; new reporting semantics and alpha access, not a rename of current attribution output |
| BigQuery evidence adapter | Exact event-parameter completeness, consent aggregates and sequential analysis could use [export schema][bq-schema] | 1–2 weeks | High; adds credentials, query costs and a second data model. Existing link inspection does not inspect export freshness |
| Realtime and comparisons | Realtime tagging checks and same-property comparisons are useful and offered by peers below; [Data reference][run-report] exposes comparison fields | 2–4 days | Medium; separate freshness/cache policy and date/filter UX |
| Read annotations and change history | Correlate configuration changes with reported anomalies; [Admin news][admin-news] documents annotation resources | 2–3 days | Medium; avoid causal claims and avoid adding annotation writes before approval work |
| Audience templates | New lifecycle templates could improve proposals, but [December 2025 release notes][archive] do not establish that every UI template can be reproduced by public Audience filters | 2–4 days | Medium; validate filter semantics and proto examples before shipping templates |

## API and product research

The public reporting surface remains versioned `v1beta` for core reports and
`v1alpha` for funnels. The Admin public reference exposes alpha and beta, not
a generally interchangeable stable v1. Package version numbers are distinct
from API surface versions. [Data report][run-report], [funnel][funnel-api],
[Admin reference][admin-ref].

| Adapter methods/resources | Verified surface |
| --- | --- |
| Account summaries, Property, streams, custom dimensions/metrics, key events, Google Ads links | Admin beta and alpha |
| Audience list/get/create/update/archive; event create/edit rules and reorder | Admin alpha |
| Enhanced measurement, attribution settings, SA360/DV360 links, BigQuery links | Admin alpha |
| Retention settings | Admin beta and alpha, separate from Property |
| Reporting identity and user-provided-data settings | Admin alpha |
| Data filters and Search Console links | No corresponding public methods found in reference or installed client |

This inventory was checked against [Admin resources][admin-ref] and the
installed client classes without constructing authenticated clients.
At baseline, `google.analytics.admin.AnalyticsAdminServiceClient` re-exported
alpha, despite some source comments describing beta. The Next compatibility
change uses explicit beta imports for supported calls and matching types;
alpha-only calls retain explicit alpha imports.

The baseline permitted Data `>=0.18.0,<1`, Admin `>=0.22.0,<1`; installation resolved
Data 0.23.2 (published September 24, 2026) and Admin 0.30.1 (June 25, 2026).
Both fit the current ranges. [Data package][data-package], [Admin package][admin-package].
Upstream histories show recent regenerated clients, Python compatibility
changes, and deprecated `credentials_file` constructor arguments. This repo
uses credential objects, not that deprecated argument. The removed UA
configuration methods are not called here. The follow-up reproduced failures
at those old lower bounds. Data 0.18.16 introduced sampling metadata; Admin
0.23.0 introduced event-edit rules (beta key events arrived in 0.22.9).
Those are the new tested floors. Reporting identity arrived in Admin 0.25.0
and retains an unsupported result on earlier supported clients. The matrix
tests these Data/Admin floors and current resolution, not all intermediate
versions or minimum transitive dependencies.
[Data library history][data-library], [Admin library history][admin-library].

Data changes: April 23, 2026 added alpha advertising conversion reporting;
September 14 added truncation reasons and alpha conversational `properties.chat`
with a separate scope. Existing `runReport`/funnel methods remain documented.
Deprecated `conversions`/`isConversionEvent` names survived in a baseline agent
example; N7 replaces them with `keyEvents`/`isKeyEvent`.
[Data API changelog][data-news].

Admin changes: April 14, 2026 added UPD reads; June 18 added reporting-identity
updates and `PropertySummary.can_edit`. Identity reads arrived August 2025,
just outside this review's past-year window. `ConversionEvent` remains
deprecated in favor of `KeyEvent`. The repo has no affected UA calls.
[Admin API changelog][admin-news].

Names checked in the [official dimensions/metrics schema][schema]: `eventCount`,
`sessions`, `activeUsers`, `totalUsers`, `totalRevenue`, `itemRevenue`,
`itemsPurchased`, `keyEvents`, `engagementRate`, `eventName`, `date`,
`sessionSource`, `sessionMedium`, `sessionDefaultChannelGroup`, `deviceCategory`,
`newVsReturning`, `country`, `landingPagePlusQueryString`, `currencyCode`,
`transactionId`, `week`, `isKeyEvent`, `sessionKeyEventRate` are listed.
`paymentType` and `daysSinceFirstSession` are not standard names in that
reference. A registered custom dimension must be discovered for that property;
parameter presence in tagging does not make a standard reporting dimension.
Names alone do not establish valid combinations; that requires compatibility
checks or mocked contracts backed by the official method schema.

Past-year product changes relevant to the proposals:

- October 2, 2025: benchmarking added absolute metrics. November 5: UPD's role
  shifted toward activation and Ads conversions. December 1: high-value and
  disengaged-purchaser audience templates. December 12: Analytics Advisor.
  These are product changes, not proof of new public adapter methods. [2025 archive][archive].
- August 11, 2026: conversion click/view windows became more configurable;
  September 29: app conversion reporting/management expanded. September 21:
  hostname include filters launched. July 30: aggregate-identifier diagnostics.
  Existing instructions must not describe one legacy lookback policy as
  universal. API support and property eligibility require separate checks.
  [2026 releases][product-news].
- Current key-event attribution windows differ from conversion-management
  windows, and reporting-model changes do not affect session/user-scoped
  traffic dimensions. N7 removes unsupported lag and DDA-volume claims.
  [Attribution settings][attribution-help].
- Reporting identity is User-ID/device ID/modeling, not the old Google Signals
  identity description in `agents/ga4-property.md`. Consent mode is not proved
  by a homepage fetch. [Identity][identity-help], [consent documentation][consent].
- BigQuery has explicit `privacy_info` fields and a different event-level
  schema; the repo only reads link configuration. No specific past-year
  export-schema migration affecting this adapter was established. [Export schema][bq-schema].

## Benchmark provenance

No reproducible source was found for the exact p25/p50/p75 cells in
`ga4_benchmarks.py`. The baseline supplied publisher names but no URL, cohort,
sample size, date, calculation or metric mapping per cell. The `other` table
is described as an average without a derivation. This is an evidence gap,
not proof that every value is false.

- [Unbounce][unbounce] publishes landing-page conversion medians (6.6% overall),
  not this repo's session/funnel tables or full percentile matrix.
- [Contentsquare's 2025 explorer][contentsquare] uses a one-page-visit bounce
  definition and its own customer cohort. It does not establish GA4 engagement
  bounce percentiles for these nine verticals.
- [WordStream 2025][wordstream] describes paid-search campaign benchmarks,
  not all-channel GA4 property distributions.
- The code names Statista without a dataset title or link; its contribution
  cannot be verified. No proprietary data was retrieved or copied.

Retain the values as labeled unverified heuristics this run. Do not substitute
one publisher's median for fabricated quartiles. A future table needs a source,
license, observation period, denominator, cohort and reproducible transformation
for every entry; property history is the preferable default comparison.

## Comparable open-source projects

| Project | Verified offering | Decision here |
| --- | --- | --- |
| [Google Analytics MCP][google-mcp] | Experimental local MCP, core and funnel reports, realtime, property information and custom definitions | Realtime is useful Later; this repo already has MCP and funnels, so do not propose another MCP server |
| [surendranb/google-analytics-mcp][community-mcp] | Advertises schema discovery, server-side totals, realtime and dynamically loaded analytical playbooks | Metadata/preflight are worthwhile Next; remote skill loading and telemetry are not needed |
| [googleAnalyticsR][analytics-r] | R toolkit wrapping Analytics APIs, including GA4 support | Reference for a mature query interface; no reason to add R or replace the Python adapters |

Comparison is based on public project documentation/source, not installation,
benchmarking or a security audit of those projects. Their existence is not
evidence that their outputs are accurate.

## Considered and rejected; open questions

- Reject autonomous/batched Admin writes, `--yes`, and treating MCP
  `confirm=true` as human approval. They violate the owner's write constraint.
- Reject paid benchmark feeds, copied proprietary tables, a hosted dashboard,
  and a replacement agent framework. They add cost or change project shape.
- Defer `properties.chat`: new scope, AI output and a second conversational
  layer overlap the existing agent interface; no demonstrated need here.
- Do not add audience member exports. Individual identifiers conflict with
  the aggregate-analysis scope and require a different privacy design.
- Leave the post-payment heuristic and funnel step removal unchanged. Similar
  event totals do not establish ordering, but the intended opt-in policy needs
  an owner decision. Document the limitation instead of inventing certainty.
- Leave FX defaults unchanged: they are dated mid-2025 static estimates and
  are not wired to a real `--base-currency` flag. Currency history needs explicit
  dates/rate provenance before any financial comparison feature.
- The website fetch guard still has a DNS validation/connection race after
  redirect checks; full address pinning is a larger transport change.
- Live scopes, roles, quotas, propagation delays, API eligibility, property
  custom-field compatibility and end-to-end writes remain unverified by design.
- New cache writes are scrubbed and old entries are scrubbed when returned.
  Existing on-disk caches were not inspected or migrated; TTL expiry is not a
  disk-retention/deletion policy. A future cleanup policy should handle legacy
  entries without scanning credentials or removing unrelated files.

[admin-ref]: https://developers.google.com/analytics/devguides/config/admin/v1/rest
[retention]: https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1beta/properties/getDataRetentionSettings
[identity-api]: https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1alpha/properties/getReportingIdentitySettings
[response-meta]: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData
[data-news]: https://developers.google.com/analytics/devguides/reporting/data/v1/changelog
[admin-news]: https://developers.google.com/analytics/devguides/config/admin/v1/changelog
[data-library]: https://github.com/googleapis/google-cloud-python/blob/main/packages/google-analytics-data/CHANGELOG.md
[admin-library]: https://github.com/googleapis/google-cloud-python/blob/main/packages/google-analytics-admin/CHANGELOG.md
[data-package]: https://pypi.org/project/google-analytics-data/0.23.2/
[admin-package]: https://pypi.org/project/google-analytics-admin/0.30.1/
[schema]: https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema
[run-report]: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport
[funnel-api]: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1alpha/properties/runFunnelReport
[metadata]: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/getMetadata
[compatibility]: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/checkCompatibility
[data-quotas]: https://developers.google.com/analytics/devguides/reporting/data/v1/quotas
[archive]: https://support.google.com/analytics/answer/13420269?hl=en
[product-news]: https://support.google.com/analytics/answer/9164320?hl=en
[identity-help]: https://support.google.com/analytics/answer/10976610?hl=en
[consent]: https://support.google.com/analytics/answer/9976101?hl=en
[bq-schema]: https://support.google.com/analytics/answer/7029846?hl=en
[unbounce]: https://unbounce.com/conversion-benchmark-report/
[contentsquare]: https://csquad.contentsquare.com/benchmarks-explorer
[wordstream]: https://www.wordstream.com/blog/2025-google-ads-benchmarks
[google-mcp]: https://github.com/googleanalytics/google-analytics-mcp/blob/main/README.md
[community-mcp]: https://github.com/surendranb/google-analytics-mcp
[analytics-r]: https://github.com/MarkEdmondson1234/googleAnalyticsR
[attribution-help]: https://support.google.com/analytics/answer/10597962?hl=en
[configuration-limits]: https://support.google.com/analytics/answer/12229528?hl=en
