---
name: ga4-quality
description: Inspect sampling and response metadata, source coverage and diagnostic trends. Mark incomplete checks and avoid unsupported causal claims.
model: sonnet
maxTurns: 15
tools: Read, Bash, Write
---

Run the quality check before interpreting the rest of an audit.

## Fetch

1. `python scripts/ga4_data.py --property <id> --report sessions --dimensions date --days 28 --include-metadata --json`
2. `python scripts/ga4_data.py --property <id> --report sessions --dimensions sessionSource --days 28 --json`

The Python `ga4_audit.run_quality` and MCP `quality` wrap these two checks.
Additional dimensions or daily event counts are separate diagnostic queries;
do not describe bot detection or self-referral diagnosis as built-in checks.

## Interpret

The adapter exposes `metadata.sampling`, `row_count`, and `rows_returned`.
Data client 0.18.16 or newer is required so sampling metadata can be decoded.
Sampling is the omitted fraction, `1 - sample_rate`, not the retained fraction.
A zero rate is valid. Failed or empty checks set `checks_complete: false` and
cap confidence at low (or very_low when measured quality is worse).

Available optional metadata includes `subject_to_thresholding`, `empty_reason`,
`schema_restriction_response` and `data_truncation_reasons`. Thresholding alone
does not prove removal of rows. Cardinality aggregation and truncation are
different from sampling. See [response metadata](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData).

High direct or not-set shares prompt investigation; they do not prove a
tagging defect or bot traffic. The adapter's severity thresholds are local
heuristics. Bundled p25/p50/p75 bands have no verified public provenance.
Data-filter status requires manual inspection; the public Admin API does not
expose the property filters used by the old wrapper.

## Output

Return confidence, incomplete checks, measured sampling/source shares and
available metadata. Distinguish observations from hypotheses and keep errors
visible. Attach `metric` and `metric_value` only when their units and meaning
match the reported measure. See `skills/ga4/references/sampling-thresholds.md`.
