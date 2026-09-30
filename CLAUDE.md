# CLAUDE.md

Instructions for Claude Code working with `google-analytics-agent`. Most
of the universal guidance lives in [AGENTS.md](AGENTS.md); this file
covers Claude Code-specific notes only.

## Skills and subagents

Claude Code loads `skills/ga4/SKILL.md` as the top-level router. It
exposes `/ga4 <command>` and routes to:

- `conversions`, `attribution`, `quality`, `property` are router-hosted commands with no skill directory of their own (the router verifies auth and spawns the matching agent directly).

The `ga4-audit` orchestrator spawns `ga4-context` and `ga4-quality` in
parallel as gates before the rest of the audit runs. Every other audit
command can call `ga4-context` first when it needs the inferred vertical
for benchmark enrichment.

Each skill either calls a Python script directly or spawns a subagent
defined under `agents/`. The audit orchestrator (`ga4-audit`) runs the
quality and events agents sequentially as gates, then fans out the rest
in parallel.

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

Audit output defaults to markdown (no emoji) via
`scripts/ga4_report.py --format md`. The report attaches the property
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
