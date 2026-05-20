# GEMINI.md

Instructions for Gemini CLI working with `google-analytics-agent`. Most of
the universal guidance lives in [AGENTS.md](AGENTS.md); this file covers
Gemini-specific notes only.

## Tool-name mapping

Gemini CLI's built-in tool names differ from Claude Code's. When a skill
or instruction mentions a Claude tool, use the Gemini equivalent:

| Claude Code tool | Gemini equivalent |
|------------------|--------------------|
| `Bash` | `run_shell_command` |
| `Read` | `read_file` |
| `Edit` | `replace` |
| `Write` | `write_file` |
| `Grep` | `search_file_content` |
| `Glob` | `glob` |

The Python CLI under `scripts/` is the same on both runtimes.

## Skill activation

Gemini CLI activates skills via the `activate_skill` tool. The
`skills/ga4/SKILL.md` description triggers on GA4-related prompts. Once
activated, follow the routing table in that file.

## How to invoke the toolkit

```
# Ask the user what property to analyze if not given
python scripts/ga4_auth.py --check
python scripts/ga4_auth.py --properties   # if the user is unsure which property to use

# Profile the live site first - feeds vertical + platform to every other agent
python scripts/ga4_context.py --property <id> --analyze --json

# Then call the relevant analysis script
python scripts/ga4_funnel.py --property <id> --steps view_item,add_to_cart,purchase --days 28 --json

# Render the final audit as markdown (no emoji)
python scripts/ga4_report.py --property <id> --inputs a.json,b.json --format md --output audit.md
```

For the full command list, see [AGENTS.md](AGENTS.md).

## Benchmark-aware findings

When emitting an analysis finding that has a comparable numeric, include
both `metric` and `metric_value` keys on the finding object. The
markdown reporter calls `ga4_benchmarks.compare()` against the inferred
vertical and appends a band + interpretation phrase to the finding line.

## Confirmation before writes

Same rule as on every other runtime: for every Admin API write, show the
resolved JSON, ask `y/N`, then execute. Never batch writes without
confirmation.

## Auth

The default auth path is gcloud Application Default Credentials:

```
python scripts/ga4_auth.py --adc            # prints the gcloud command
python scripts/ga4_auth.py --adc --write    # with analytics.edit scope
```

Run the printed command, then `--check` again.
