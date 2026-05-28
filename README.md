# google-analytics-agent

[![tests](https://github.com/arcbaslow/google-analytics-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/arcbaslow/google-analytics-agent/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![version](https://img.shields.io/badge/version-0.3.0-blue.svg)](CHANGELOG.md)

## Quickstart

```
uv venv && uv pip install -r scripts/requirements.txt
python scripts/ga4_auth.py --adc        # run the printed gcloud command, then:
python scripts/ga4_auth.py --check
python scripts/ga4_audit.py --property <id> --output audit.md
```

Or run the MCP server in any MCP client: `uvx --from git+https://github.com/arcbaslow/google-analytics-agent ga4-mcp`

A multi-agent toolkit for Google Analytics 4. Talks to the GA4 Data API and
Admin API, profiles the property's live website, runs specialist analysis
subagents (funnel, segments, attribution, event taxonomy, data quality,
property configuration), benchmarks findings against industry bands, and
ships write surfaces for event rules, audiences, custom dimensions and
metrics, key events, plus local-stored segment and custom-report
definitions. Audits render to markdown by default (no emoji), with HTML
and PDF as alternatives.

Designed to work with three runtimes side by side:

- **Claude Code** — full skill and subagent integration via `skills/` and `agents/`
- **OpenAI Codex** — driven by `AGENTS.md` and the universal Python CLI
- **Gemini CLI** — driven by `GEMINI.md` and the universal Python CLI

The Python adapters under `scripts/` are the source of truth and work the
same on all three.

## What is google-analytics-agent?

A toolkit, not just an analyzer. It can:

- Profile the property's live website: read the web-stream URL from GA4,
  fetch the homepage / robots.txt / sitemap.xml, and infer vertical,
  platform (Shopify, WordPress, Magento, …), framework (Next.js, React,
  Vue, …), SPA-vs-MPA, language, and a sitemap-derived page-type
  inventory.
- Audit data quality, funnel drop-off, segment cohorts, event taxonomy,
  attribution, key events, and property configuration.
- Benchmark findings against industry bands. Nine verticals shipped
  (ecommerce, saas, media, lead_gen, finance, travel, education,
  nonprofit, other); metrics include bounce / engagement / pages-per-
  session / avg engagement time / conversion rate / cart abandonment /
  direct share / mobile share / sampling / not-set share.
- Edit GA4 configuration: rename/synthesize events via EventEditRule and
  EventCreateRule, create and archive audiences, manage custom dimensions
  and metrics, manage key events.
- Persist and reuse local definitions: saved segment filters and saved
  custom report specs (rendered to JSON / CSV / **markdown** / HTML /
  PDF).

Three layers:

- Python adapters under `scripts/` call the Data and Admin APIs, cache
  responses on disk for 15 minutes, scrub PII, and return structured JSON.
- Markdown agent definitions under `agents/` describe how an agent should
  analyze that JSON.
- Skills under `skills/` route `/ga4 ...` commands (in Claude Code) to the
  right agent or script. For Codex and Gemini CLI, the runtime-specific
  instruction files describe the same flow in their conventions.

### vs. the official Google GA4 MCP server

Google's official server exposes raw Data/Admin API access. This toolkit
adds, on top of that surface: an industry benchmark engine (nine
verticals), live-site context profiling (vertical / platform / framework
/ sitemap), a multi-agent audit orchestrator that produces a prioritized
action plan, and the same features across Claude Code, Codex, and Gemini
CLI as well as MCP.

## Requirements

- Python 3.10 or newer
- Google Cloud SDK (`gcloud`) for the default auth path, or a Cloud OAuth
  Desktop client for the fallback path
- GA4 property access at the Viewer level (read) or Editor level (write)
- WeasyPrint runtime libraries are only needed if you want PDF reports
  (markdown is the default audit format and does not need them):
  - Debian/Ubuntu: `apt install libpango-1.0-0 libpangoft2-1.0-0`
  - macOS: `brew install pango`
  - Windows: install the GTK 3 runtime — see WeasyPrint's
    [Windows installation notes](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows).
    Easiest path is the MSYS2 bundle; the standalone GTK installer also
    works. Skip this entirely if you only need markdown or HTML output.

## Install

From inside the project directory.

### Recommended: `uv`

```
uv venv
uv pip install -r scripts/requirements.txt
uv run python scripts/ga4_auth.py --check
```

[`uv`](https://github.com/astral-sh/uv) is a single-binary Python installer
and runner. One install of `uv` replaces the venv + pip dance and is
faster on cold-start.

### Optional extras

- `pip install -e ".[pdf]"` — adds WeasyPrint for PDF report rendering. Markdown is the default audit format and needs no extra system libs.
- `pip install -e ".[dev]"` — adds pytest + ruff for contributors.

### Plain venv (works everywhere)

```
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r scripts/requirements.txt
```

## Authenticate

The default path is gcloud Application Default Credentials. You do not need
to register your own OAuth client.

```
python scripts/ga4_auth.py --adc            # prints the gcloud command
python scripts/ga4_auth.py --adc --write    # same, scoped for write APIs
```

Run the printed command, then verify:

```
python scripts/ga4_auth.py --check
python scripts/ga4_auth.py --properties
```

Set a quota project once (any Cloud project you have access to with the GA4
Data and Admin APIs enabled):

```
python scripts/ga4_auth.py --quota-project <project-id>
```

Fallback for environments without gcloud (CI, locked-down workstations):

```
python scripts/ga4_auth.py --oauth --client-secret-file <path>
```

Credentials are resolved in this order: `GOOGLE_APPLICATION_CREDENTIALS`,
gcloud ADC, legacy OAuth file at `~/.claude/ga4-credentials.json`.

## Use it

### Claude Code

After authentication, slash commands work directly:

```
/ga4 audit <property-id>
/ga4 funnel <property-id> --steps view_item,add_to_cart,purchase
/ga4 audiences <property-id>
```

The full list lives in `skills/ga4/SKILL.md`. The runtime auto-loads the
skill and agent definitions.

### Codex

Codex reads `AGENTS.md` at the project root for instructions. The
fastest path is the one-command driver:

```
python scripts/ga4_audit.py --property <id> --output audit.md
```

For finer control:

```
python scripts/ga4_context.py --property <id> --analyze --json
python scripts/ga4_funnel.py --property <id> --days 28 --json
python scripts/ga4_admin.py --property <id> --key-events --json
```

### Gemini CLI

Gemini CLI reads `GEMINI.md`. Same Python CLI, same flags, including the
one-command driver `python scripts/ga4_audit.py --property <id>`.

### Plain Python

Every feature is exposed as a Python CLI under `scripts/`. The runtimes
above are conveniences — anything they can do, you can do manually.

### MCP server

The same toolkit runs as an MCP server over stdio, usable from any MCP
client (Claude Desktop/Code, Cursor, Windsurf, n8n).

```json
{
  "mcpServers": {
    "ga4": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/arcbaslow/google-analytics-agent", "ga4-mcp"]
    }
  }
}
```

The server registers 32 tools. Read and analysis tools cover the full
audit surface — audit, context, funnel, events, check_events, quality,
conversions, attribution, property_config, report, benchmarks — plus
read-only admin reads (property_details, data_streams, custom_defs,
key_events, attribution_settings, list_audiences, list_event_rules) and
saved-definition tools (list_segments, list_saved_reports,
run_saved_report). Write tools follow a dry-run-first contract: tools
like add_key_event, create_audience, add_custom_dimension, and
add_event_edit_rule, when called without `confirm=true`, return the exact
change that would be applied and make no API call; re-invoking the same
call with `confirm=true` executes it.

## Commands

Read:

```
/ga4 audit <property-id>          # full audit, agents in parallel, benchmarked, markdown by default
/ga4 context <property-id>        # profile the live site: vertical, platform, framework, sitemap shape
/ga4 funnel <property-id>         # step-by-step funnel (configurable steps)
/ga4 segments <property-id>       # cohort drop-off breakdowns
/ga4 events <property-id>         # event taxonomy validation
/ga4 conversions <property-id>    # key events configuration
/ga4 attribution <property-id>    # channel attribution at each step
/ga4 quality <property-id>        # data quality and integrity
/ga4 property <property-id>       # property configuration
/ga4 benchmarks [--vertical V]    # inspect bundled industry benchmark bands
```

Write (need `analytics.edit` scope):

```
/ga4 events-edit <property-id>    # EventEditRule / EventCreateRule
/ga4 audiences <property-id>      # create, list, archive audiences
/ga4 custom-defs <property-id>    # custom dimensions and metrics
/ga4 key-events <property-id>     # key events (conversions)
```

Local stored definitions (no API write):

```
/ga4 segment-defs ...             # saved filter expressions
/ga4 report ...                   # saved custom reports → JSON / CSV / HTML / PDF
```

Auth:

```
/ga4 auth
/ga4 properties
```

Outside Claude Code, the same commands run through the Python adapters in
`scripts/` — see `AGENTS.md` for the cross-runtime invocation table.

## How it works

`scripts/ga4_auth.py` resolves credentials. `ga4_data.py` wraps `runReport`
and `runFunnelReport`. `ga4_admin.py` wraps the Admin API for both reads
(property, streams, custom defs, key events, audiences) and writes (event
rules, audiences, custom dimensions, key events). `ga4_context.py` reads
the property's web-stream URL and analyzes the live site to produce the
property profile that grounds every other audit. `ga4_benchmarks.py`
ships a vertical-by-metric benchmark table and a `compare()` helper used
by the reporter to attach calibrated verdicts to findings.
`ga4_definitions.py` stores reusable segment filter expressions and custom
report definitions under `~/.claude/ga4-definitions/`. `ga4_report.py`
renders the audit and single-report markdown, HTML, and PDF (PDF via
WeasyPrint).

Agents under `agents/` are markdown files Claude reads and dispatches as
subagents. Skills under `skills/` provide the `/ga4 ...` routing surface
for Claude Code. Codex and Gemini CLI use the equivalent runtime-specific
instruction files (`AGENTS.md`, `GEMINI.md`) plus the same Python adapters.

## Project structure

```
google-analytics-agent/
  .claude-plugin/        plugin manifest and marketplace config
  agents/                specialist agent definitions
  docs/                  setup guide
  hooks/                 placeholder for pre/post-tool guards
  scripts/               Python adapters and tests (the universal CLI)
  examples/              sample-audit.md showing the audit output shape
  skills/
    ga4/                 top-level router skill + reference docs
    ga4-audit/           parallel audit orchestrator (with benchmarks + markdown)
    ga4-context/         live-site profiler: vertical / platform / framework
    ga4-funnel/          funnel analysis (configurable steps)
    ga4-segments/        cohort drop-off
    ga4-events/          event taxonomy validation
    ga4-conversions/     key events config audit
    ga4-attribution/     channel attribution at each step
    ga4-quality/         data quality audit
    ga4-property/        property configuration audit
    ga4-events-edit/     EventEditRule / EventCreateRule writes
    ga4-audiences/       audience CRUD
    ga4-custom-defs/     custom dimension / metric CRUD
    ga4-key-events/      key event CRUD
    ga4-segment-defs/    local stored segment definitions
    ga4-custom-report/   local stored report definitions
  AGENTS.md              Codex instructions
  GEMINI.md              Gemini CLI instructions
  CLAUDE.md              Claude Code instructions (also points here)
```

## Funnels

The funnel analysis accepts any ordered list of GA4 event names. The
e-commerce purchase funnel is available as a convenience preset:

```
view_item -> add_to_cart -> begin_checkout -> add_payment_info -> purchase
```

For e-commerce flows where a payment provider redirects the user out of
the page and back, the `--check-postpayment` flag runs a heuristic that
detects `add_payment_info` firing after `purchase` and drops the misleading
step from the funnel. The check is opt-in and not relevant outside that
class of flow.

## Date ranges

- Funnel, segments, conversions, attribution, property: 28 days default
- Events (data quality sampling): 7 days default
- Override with `--days N` on any command

## Benchmarks

`scripts/ga4_benchmarks.py` ships a vertical-by-metric band table (p25 /
p50 / p75) for nine verticals — ecommerce, saas, media, lead_gen,
finance, travel, education, nonprofit, other. Numbers are conservative
directional estimates compiled from public industry reports
(Contentsquare digital experience benchmarks, WordStream PPC benchmarks,
Unbounce conversion benchmark reports, Statista) as of late 2025. Any
finding that declares a `metric` / `metric_value` pair is auto-enriched
with the band, interpretation, and a delta-vs-median percent. The
benchmark vertical is read from the property context (`ga4-context`),
overridable per audit via `--vertical`.

## Markdown reports

Audit and custom-report runs default to plain markdown (no emoji) — easy
to commit, review, and diff. The audit markdown includes:

- Header with property ID, confidence label, and benchmark vertical
- Property Context section with homepage status, inferred vertical /
  platform / framework, language, SPA-vs-MPA, sitemap-derived page-type
  inventory
- Executive Summary (one bullet per agent)
- Action Plan grouped by severity, with benchmark band annotations on
  any metric-bearing finding
- Per-Agent Output with collapsed raw JSON appendix per agent

Pass `--format html` or `--format pdf` for the other renderings.

## Confidence labels

The `ga4-quality` agent runs first in every audit and emits a label that
every other finding inherits:

| Label | Meaning |
|-------|---------|
| `high` | <1% sampling, clean data — act on findings |
| `medium` | 1-10% sampling — act but verify with raw event sampling |
| `low` | 10-30% sampling — directional only |
| `very_low` | >30% sampling — fix data quality first, do not act on findings |

## Status

v0.3.0 — context extraction, benchmark engine, and markdown audit
renderer added. Read path is complete and works against live properties.
Write path (event rules, audiences, custom defs, key events) is wired
and unit-tested but not yet covered by integration tests against a live
property. Local segment and custom-report stores are complete.

## License

MIT. See `pyproject.toml`.

## Sample output

See [`examples/sample-audit.md`](examples/sample-audit.md) for a
hand-crafted audit showing the markdown report shape — header, property
context, executive summary, severity-grouped action plan with benchmark
verdicts, and per-agent appendix.

A condensed view is in [`examples/sample-audit-screenshot.md`](examples/sample-audit-screenshot.md).

## Acknowledgements

Built on top of `google-analytics-data` and `google-analytics-admin`.
