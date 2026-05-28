# CLAUDE.md

Instructions for Claude Code working with `google-analytics-agent`. Most
of the universal guidance lives in [AGENTS.md](AGENTS.md); this file
covers Claude Code-specific notes only.

## Skills and subagents

Claude Code loads `skills/ga4/SKILL.md` as the top-level router. It
exposes `/ga4 <command>` and routes to:

- read skills: `ga4-audit`, `ga4-context`, `ga4-funnel`, `ga4-segments`,
  `ga4-events`
- router-hosted read commands (no separate skill; the router verifies auth
  and spawns the matching agent directly): `conversions`, `attribution`,
  `quality`, `property`
- write skills: `ga4-events-edit`, `ga4-audiences`, `ga4-custom-defs`,
  `ga4-key-events`
- local-definition skills: `ga4-segment-defs`, `ga4-custom-report`

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
