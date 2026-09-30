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

For the full command list, see [AGENTS.md](AGENTS.md). The full audit runs
context, quality/property, events, funnel/key-events/segments, then conditional
attribution. Use `ga4_audit.py` for the implemented orchestration.

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
