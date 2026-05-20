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
| `python scripts/ga4_definitions.py --list-segments --json` | List stored segments |
| `python scripts/ga4_definitions.py --save-report name path.json` | Save a custom report definition |
| `python scripts/ga4_definitions.py --list-reports --json` | List stored reports |
| `python scripts/ga4_definitions.py --run-report name --property X [--format html\|pdf\|json\|csv] [--segment NAME] [--output path]` | Run a stored report |

## Confirmation before writes

For every Admin API write (audiences, event rules, custom defs, key
events), print the resolved JSON or proposed change first, then ask the
user `y/N` before executing. Do not chain writes without confirmation.

## Funnels

The default funnel is whatever ordered list of event names the user
supplies via `--steps event1,event2,...`. The e-commerce purchase funnel
(`view_item -> add_to_cart -> begin_checkout -> add_payment_info ->
purchase`) is available as a preset via `--preset ecomm` in `ga4_funnel.py`.

The `--check-postpayment` flag (opt-in, e-commerce-only) runs a heuristic
that detects an `add_payment_info` event firing after the payment-gateway
redirect-back. It is off by default.

## Caching and PII

The scripts cache responses on disk at `~/.claude/ga4-cache/` for 15
minutes per unique query. PII keys (`email`, `phone`, ID-like fields) are
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
   data quality script next, then the events script, then funnel /
   attribution / property in parallel if your runtime supports it.
4. For targeted questions, call the relevant script directly.
5. Always pass `--json` and parse the structured output. Never rely on
   the human-readable form.
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
