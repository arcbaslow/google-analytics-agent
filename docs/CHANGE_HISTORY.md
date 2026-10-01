# Annotations and configuration history

```sh
python scripts/ga4_admin.py --property 123 --annotations \
  --start-date 2026-09-01 --end-date 2026-09-30 --json
python scripts/ga4_admin.py --property 123 --account 456 --change-history \
  --start-date 2026-09-01 --end-date 2026-09-30 --json
```

Both reads require explicit inclusive dates, at most 366 days, and are
uncached. They share the bounded read budget and use pages of 200. A failed
page or exhausted budget returns an error rather than a complete partial
list. `complete: true` means every API page was consumed, not that the API
records every possible change. Both response paths are scrubbed.

Annotations use the alpha `listReportingDataAnnotations` method and its
`is_annotation_in_range` filter. Older clients return `status: unsupported`.
The dates refer to the annotation's calendar dates. Annotation text may
explain an operator's intent; it is not proof of a change's effect.

History uses beta `searchChangeHistoryEvents`, filtered to the supplied
account and property. Date boundaries are UTC, through the last nanosecond
of the end date. This read requires **analytics.edit**, as specified by the
API, and uses credentials already granted that scope. It performs no write
and does not prompt for write approval. Missing scope or property access is
an error; the adapter does not initiate authorization automatically.

History returns event identifiers, times, actor types, filtering indicators
and each change's resource/action. Actor email addresses and before/after
resource snapshots are omitted. The public API covers only a subset of UI
history. An empty result cannot establish that no changes occurred. Use the
timeline as context for investigating an anomaly, never as a causal test.
MCP exposes `reporting_annotations` and `change_history` with matching inputs.

Sources: [annotation list and filter](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1alpha/properties.reportingDataAnnotations/list),
[history scope, timestamps and coverage](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1beta/accounts/searchChangeHistoryEvents).
