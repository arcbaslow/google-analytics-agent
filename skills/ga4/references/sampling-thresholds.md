# Sampling and confidence

Use each response's metadata rather than inferring sampling from property
size. `ga4_data.py --include-metadata` exposes the retained sample fraction as
`metadata.sampling[].sample_rate`, calculated from `samples_read_count /
sampling_space_size`. `returnPropertyQuota` requests quota status; it is not
what enables sampling metadata.
[Response metadata](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData).

The audit stores the omitted fraction as `sampling_pct` (0–1). Its local
confidence heuristic uses that fraction and the sessionSource not-set share:

| Condition, evaluated in order | Label |
|---|---|
| Sampling >30% or not-set >30% | very_low |
| Sampling >10% or not-set >20% | low |
| Sampling >1% or not-set >10% | medium |
| Otherwise, with completed checks | high |

Failed, empty or incomplete quality checks cap the result at low. This label
describes the sampled checks; it does not validate the property's entire
implementation. The orchestrator passes it in the report; there is no
separate `quality-confidence.json` cache.

Inspect cardinality loss, restrictions, empty reasons and truncation
separately. `subject_to_thresholding` is not proof that rows were removed.
Try narrower windows/queries when appropriate, but do not promise this will
eliminate sampling. BigQuery export is a separate proposed adapter with
different semantics, retention and costs; it is not currently implemented.
