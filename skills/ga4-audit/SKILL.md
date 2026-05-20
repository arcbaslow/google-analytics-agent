---
name: ga4-audit
description: "Full GA4 account audit with parallel agent delegation. Profiles the property's live site for vertical and platform context, runs data-quality and event-taxonomy gates, then fans out funnel, segments, conversions, attribution, and property-configuration agents. Findings are benchmarked against industry bands and rendered to markdown, HTML, or PDF. Use when user says 'audit', 'full analysis', 'analyze my GA4', 'account health check'."
user-invokable: true
argument-hint: "<property-id> [--days N] [--base-currency CODE] [--funnel-steps e1,e2,...] [--vertical V] [--format md|html|pdf] [--output PATH]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.3.0"
  category: ga4
---

# Full GA4 Audit

## Process

1. **Verify auth**: `python scripts/ga4_auth.py --check`
2. **Fetch property summary**: `python scripts/ga4_admin.py --property <id> --details --json`
3. **Spawn `ga4-context` and `ga4-quality` in parallel** — both are gates.
   - `ga4-context` profiles the live site (vertical, platform, framework, sitemap shape) and saves the result under `~/.claude/ga4-context/<id>.json`.
   - `ga4-quality` produces the data-confidence label.
4. **Spawn `ga4-events` as the second gate**, passing the recommended-events table or any taxonomy override.
5. **Fan out the remaining agents in parallel**:
   - `ga4-funnel` (with `--funnel-steps` if supplied, or with steps the events agent confirmed)
   - `ga4-segments`
   - `ga4-conversions`
   - `ga4-property`
6. **Conditionally spawn `ga4-attribution`** if at least one key event is configured.
7. **Collect every agent's JSON output** and write each to a temp file under `/tmp/`.
8. **Render the unified report** via `python scripts/ga4_report.py` with `--format md` by default. The renderer attaches the property context section, the data-confidence label, and benchmark verdicts (from `scripts/ga4_benchmarks.py`) to every finding that declares a `metric` / `metric_value` pair.

## Agent Dispatch

### Parallel gates:
```
1a. Agent: ga4-context — "Profile property <id>"
1b. Agent: ga4-quality — "Audit data quality for property <id>"
```

### Sequential after gates:
```
2.  Agent: ga4-events  — "Validate event taxonomy for property <id>"
```

### Parallel after events:
```
3. Agent: ga4-funnel       — "Analyze the funnel for property <id>"
4. Agent: ga4-segments     — "Break down funnel drop-off by cohort"
5. Agent: ga4-conversions  — "Audit key events configuration"
6. Agent: ga4-property     — "Audit property configuration"
```

### Conditional:
```
7. Agent: ga4-attribution  — "Analyze attribution at each funnel step"
   Spawn only if ga4-conversions reports at least 1 key event configured
```

## Benchmark vertical

The vertical used for benchmark enrichment is, in priority order:

1. The `--vertical` CLI flag if supplied.
2. The inferred vertical from `ga4-context` (read from
   `~/.claude/ga4-context/<id>.json` → `site.inferred.vertical`).
3. `other` (the all-vertical average band).

Available verticals: ecommerce, saas, media, lead_gen, finance, travel,
education, nonprofit, other. See `python scripts/ga4_benchmarks.py
--list-verticals`.

## Default Parameters

- Date range: 28 days (events: 7 days)
- Base currency for cross-property normalization: USD (override with `--base-currency`)
- Output format: markdown (`--format md`) saved to `./ga4-audit-<id>-<YYYYMMDD>.md` unless `--output` is supplied
- Funnel steps: if `--funnel-steps` is not supplied, the funnel agent proposes a funnel based on which events fire (the e-commerce preset is suggested when the recommended ecomm events are present)

## Output: markdown by default

The unified report is rendered by `scripts/ga4_report.py`. The markdown
template has no emoji and includes:

1. **Header** — property ID, generation timestamp, confidence label, benchmark vertical
2. **Property Context** — homepage status, inferred vertical / platform / framework, language, SPA-vs-MPA, sitemap-derived page-type inventory
3. **Executive Summary** — one bullet per agent
4. **Action Plan** — findings grouped by severity (Critical / High / Medium / Low). Each finding shows source agent and benchmark band where applicable, e.g.

   > **Bounce rate above industry p75** _(source: ga4-quality)_ (value 0.74, vertical ecommerce, p25 0.35 / p50 0.45 / p75 0.58, band above_p75, interpretation critical)

5. **Per-Agent Output** — each agent's summary + raw JSON in a collapsed `<details>` block

To export HTML or PDF instead, pass `--format html` or `--format pdf`.

## Confidence Inheritance

Every recommendation inherits the confidence label from ga4-quality:

- Confidence High: findings can be acted on directly
- Confidence Medium: findings should be verified with raw event sampling before action
- Confidence Low: findings are directional only; recommend BigQuery export or fix data quality first

## How agents should emit benchmarkable findings

For any finding the agent wants benchmarked, include a `metric` name and
a `metric_value` (float):

```json
{
  "severity": "High",
  "title": "Bounce rate above industry p75",
  "detail": "...",
  "metric": "bounce_rate",
  "metric_value": 0.74
}
```

The reporter calls `ga4_benchmarks.compare()` and appends the band /
interpretation automatically. Findings without a metric just print
without a benchmark annotation — that's fine for qualitative findings.

## Error Handling

| Scenario | Action |
|----------|--------|
| Auth token expired | Report error, guide user to re-authenticate via gcloud ADC |
| Context fetch fails (homepage 4xx/5xx) | Continue with `vertical = other`, note in the report |
| Quota exceeded (429) | Back off per Data API quota tier, report partial results |
| No funnel events fire | Skip funnel and segments agents, return ga4-property and ga4-quality findings only |
| Post-payment heuristic positive (opt-in) | Degrade funnel by one step, flag in Critical findings |
| Agent timeout | Report findings from completed agents, note incomplete sections |
