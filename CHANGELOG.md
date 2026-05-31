# Changelog

## 0.5.0

- Replace the deterministic audit's segments stub with a real `ga4-segments`
  agent: per-cohort conversion-rate breakdowns across `deviceCategory`,
  `newVsReturning`, and `sessionDefaultChannelGroup`, flagging cohorts that
  convert materially below the property average (benchmarked), with an
  engagement-rate fallback when no key events are configured, plus evaluation
  of saved segment filters. The agent never raises out to the orchestrator.
- Centralize filter building in `ga4_data.build_dimension_filter` and let
  `run_report` apply a prebuilt `filter_dict` (used by the segments agent for
  saved segments; `ga4_definitions.build_filter_from_definition` now delegates).
- Cover the CLI entry points (`main()` dispatch) of every script. Coverage is
  now ~95% and the CI floor is raised to 93%.

## 0.4.2

- Fix the Admin API write path: `_dict_to_proto` called
  `json_format.ParseDict` directly on a proto-plus message, which raises
  `AttributeError: Unknown field ... DESCRIPTOR`. Every definition-loading
  write (`create_event_edit_rule`, `update_event_edit_rule`,
  `create_event_create_rule`, `create_audience`, `update_audience_metadata`)
  failed at runtime. Parse into the underlying protobuf via `proto_cls.pb()`
  and wrap the result; camelCase/snake_case input and unknown-field tolerance
  are preserved.
- Fix the same proto-plus `ParseDict` defect in
  `ga4_definitions.build_filter_from_definition`: applying a saved segment
  whose filter is a raw Data API `FilterExpression` (rather than the shorthand
  field/op/value shape) to a custom report run raised the same
  `DESCRIPTOR` error.
- Add offline integration tests that replay recorded API payloads through the
  real client code with only the gRPC client mocked: the Data API read path
  (`run_report` / `run_funnel_report`), the audit orchestrator end-to-end
  against healthy and problem scenarios, and the Admin API write path through
  the real proto-plus round-trip. The write-path tests cover the regression
  above.
- Cover the MCP server's dry-run/confirm contract for every write tool: a
  write tool must make no Admin API call without `confirm=true`, and must
  dispatch to the right adapter when confirmed.
- Add coverage for the event parameter-coverage validator
  (`ga4_events.event_params_coverage`) and the saved-report runner
  (`ga4_definitions.run_report_def` format dispatch, segment application, and
  filter building).
- Add coverage for the auth resolver (`ga4_auth`): ADC source tagging, token
  expiry math, legacy-credential IO and refresh, the OAuth fallback, quota
  project setting, `check_auth`, and `list_properties`.
- Add coverage for the Admin API read surfaces (`ga4_admin`): cache
  short-circuiting, the `list_key_events`/`list_conversion_events` fallback,
  enhanced-measurement attachment and error capture, per-call error wrapping,
  and platform-link aggregation.
- Add coverage for the site profiler (`ga4_context`): stream-URL extraction,
  the never-raising `_fetch` (HTTP/URL error branches), meta/JSON-LD extractor
  edges, summary building, and `analyze_website` branches (scheme-less URL,
  JSON-LD `@type` lists, sitemap fallback).
- Raise the CI coverage floor to 85% (total is now ~86%) and enable the
  `no_implicit_optional`, `warn_redundant_casts`, `warn_unused_ignores`, and
  `warn_unused_configs` mypy checks.

## 0.4.1

- Publish to PyPI as `google-analytics-agent` via an automated release
  workflow (`.github/workflows/release.yml`) using PyPI Trusted Publishing
  (OIDC, no stored token). A `release: published` event builds the sdist
  and wheel, runs `twine check`, and publishes from the `pypi` environment;
  `scripts/check_release_version.py` guards that the release tag matches the
  packaged version. A `workflow_dispatch` trigger provides a manual fallback.
- Widen the MCP server auth guard: expired or reauth-required credentials
  (`RefreshError`, and API errors whose message requests reauthentication)
  now surface as a structured `auth_required` response with a remediation
  hint instead of an unhandled exception.
- Report the installed package version in the MCP server handshake instead
  of the underlying SDK version.

## 0.4.0

- Add an MCP server (`scripts/ga4_mcp.py`, console entry point `ga4-mcp`)
  exposing 32 tools over stdio: the full read/analysis surface plus
  read-only admin reads and saved-definition tools. Write tools follow a
  dry-run-first contract — without `confirm=true` they return the exact
  change and make no API call.
- Package the project for distribution: console entry point, `[pdf]` and
  `[dev]` extras, and `uvx`/`pip install` support.
- Add CI and quality tooling: ruff lint + format check, mypy, and pytest
  with coverage across a Python 3.10–3.13 matrix; pre-commit config and
  Dependabot.
- Consolidate the `conversions`, `attribution`, `quality`, and `property`
  read commands into the `ga4` router (spawned directly, no separate skill
  directories). Every `/ga4 <command>` invocation is unchanged.

## 0.3.0

- Add `ga4-context` skill and `scripts/ga4_context.py`. Reads the
  property's web-stream URL, fetches the live site (homepage, robots.txt,
  sitemap.xml), infers vertical, platform, framework, SPA-vs-MPA, and
  page-type inventory. Result is cached under `~/.claude/ga4-context/`.
- Add `scripts/ga4_benchmarks.py` with p25/p50/p75 bands for nine
  verticals (ecommerce, saas, media, lead_gen, finance, travel,
  education, nonprofit, other) across ten metrics. `compare()` and
  `enrich_findings()` attach benchmark verdicts to any finding that
  declares a `metric` / `metric_value` pair.
- Add markdown audit renderer (`ga4_report.render_markdown`). Plain
  markdown, no emoji. Includes the property-context section and
  benchmark verdicts inline with findings.
- Add markdown output to custom-report runs (`--format md` on
  `ga4_definitions.py --run-report`).
- Add `scripts/ga4_audit.py` driver: one-command end-to-end audit from
  any runtime. Profiles the site, runs the analysis bundle (quality +
  events + funnel + conversions + property; conditional attribution),
  and renders the report.
- Add `examples/sample-audit.md` so users can see the output shape
  before running the tool.
- Update all skills and agents to consume the property context, emit
  benchmarkable findings, and surface the markdown report path.

## 0.2.0

- Rename project to `google-analytics-agent`.
- Add multi-runtime support: `AGENTS.md` (Codex), `GEMINI.md` (Gemini
  CLI), `CLAUDE.md` (Claude Code). Python adapters are the universal
  CLI; each runtime gets a thin instruction file.
- Switch default auth path to gcloud Application Default Credentials.
  Users no longer need to register their own OAuth client. Legacy
  client-secret flow kept as a documented fallback.
- Add Admin API write surfaces: EventEditRule / EventCreateRule CRUD
  with reorder, audiences CRUD, custom dimensions and metrics, key
  events (write side). All require the `analytics.edit` scope.
- Add `scripts/ga4_definitions.py` for local-stored segment filter
  expressions and custom report definitions under
  `~/.claude/ga4-definitions/`.
- Add single-report HTML and PDF renderers.
- Remove the prior e-commerce-and-KZ-market framing. Funnel steps are
  configurable; the e-commerce purchase funnel is one preset. The
  payment-gateway redirect-back heuristic is opt-in via
  `--check-postpayment`. PII deny-list and currency table broadened.
- Rename `ga4-ecomm-events` skill and agent to `ga4-events`.
- Rewrite `README.md` in plain technical tone (no marketing copy).
- Pin upper bounds on Python dependencies.

## 0.1.0

- Initial scaffold: GA4 Data API and Admin API wrappers, Python
  adapters under `scripts/`, specialist subagent definitions under
  `agents/`, slash-command skills under `skills/`. 15-minute disk
  cache, PII scrubber, sampling-aware confidence labels, HTML/PDF audit
  report.
- Funnel analysis built on `runFunnelReport` (v1alpha) with step
  validation, rate computation, and leakiest-step identification.
- Audit orchestrator with sequential gates and parallel fan-out.
