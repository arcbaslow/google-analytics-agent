# GA4 Sampling Thresholds and Mitigation

## When GA4 samples

**Standard properties**: queries that span more than ~10 million events in the date range trigger sampling. The threshold is not published exactly and varies by query complexity.

**360 properties**: threshold is ~1 billion events.

Sampling affects:
- Custom reports in Explorations (sampling rate visible in UI)
- Data API queries when event count exceeds threshold
- Reports with custom dimensions/metrics not in pre-aggregated tables

Sampling does NOT affect:
- Standard reports in the GA4 UI for simple metrics (sessions, users by default channel)
- Realtime reports
- Reports based on pre-aggregated tables

## How to detect sampling

Data API responses include `samplingMetadatas` field. Always request with `returnPropertyQuota: true` to see remaining quota AND sampling status.

Sample rate is computed as: `sampleCount / samplingSpaceSize`

- 100% (rate = 1.0): no sampling
- 50% (rate = 0.5): half the data was used to extrapolate
- 10% (rate = 0.1): severe sampling, results are estimates only

## Confidence labels

`ga4_utils.format_confidence` maps sampling % to a label that propagates through the audit:

| Sampling rate | Confidence label | What it means |
|---------------|------------------|---------------|
| 100% (no sampling) | high | Trust the numbers |
| 99-90% | medium | Trust the numbers, expect minor variance |
| 89-70% | low | Directional only; don't act on small differences |
| <70% | very_low | Recommend BQ export before making decisions |

## Mitigation

In order of effectiveness:

1. **Shorten date range**: 7 days instead of 28 cuts event volume by 4x
2. **Narrow filters**: filter to single channel/device upfront instead of pulling all and slicing
3. **Use pre-aggregated dimensions**: `sessionDefaultChannelGroup` is pre-aggregated, raw `sessionSource`/`sessionMedium` is not
4. **Enable BigQuery export**: the only way to fully eliminate sampling on standard properties

## What the audit does about sampling

- `ga4-quality` agent runs first, measures sampling on a baseline 28-day query
- Confidence label is cached at `.ga4-cache/<property-id>/quality-confidence.json`
- Other agents read this cache and stamp their findings with the confidence level
- The unified audit output includes the confidence label in the executive summary
