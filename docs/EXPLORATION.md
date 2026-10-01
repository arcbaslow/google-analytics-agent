# Realtime and same-property comparisons

Both reads are explicit, uncached and scrubbed. They use the existing bounded
read transport and Analytics read credentials; neither changes the property.

```sh
python scripts/ga4_explore.py --property 123 --realtime \
  --metrics eventCount --dimensions eventName \
  --start-minutes-ago 29 --end-minutes-ago 0 --limit 10000
```

Realtime minute bounds are inclusive. The default covers the last 30 minutes;
bounds up to 59 are accepted locally but require a GA360 property at the API.
Realtime supports its own field schema, not every Core report field. The
optional `--filter` takes a JSON dimension filter using the same schema as
Core reports. The API has no offset: one request returns at most `--limit`
rows (maximum 250000). Inspect `complete`; narrow dimensions or raise the
limit when truncated. `fetched_at` is the adapter's UTC observation time,
not proof that every event has finished processing. Quota is Realtime quota.

```sh
python scripts/ga4_explore.py --property 123 --metrics activeUsers \
  --dimensions country \
  --comparisons '[{"name":"mobile","dimension_filter":{"field":"deviceCategory","op":"EXACT","value":"mobile"}},{"name":"desktop","dimension_filter":{"field":"deviceCategory","op":"EXACT","value":"desktop"}}]' \
  --date-ranges '[{"name":"before","start_date":"2026-09-01","end_date":"2026-09-07"},{"name":"after","start_date":"2026-09-08","end_date":"2026-09-14"}]'
```

Comparisons accept 1–4 unique named groups and 1–4 unique named, explicit
date ranges. Each group supplies either `dimension_filter` or a saved
`comparison` resource such as `comparisons/123`, discovered from that property's
metadata. Saved-resource ownership and compatibility are checked by the API.
Official `comparisons/ID` resource names are preserved during scrubbing;
comparison display text still passes through the normal PII filters.
There is one property per request. Arbitrary cross-property joins are not
supported. The API adds comparison/date-range columns to the response; retain
those columns when displaying results. Groups and dates can overlap: never
sum their user counts or infer that the comparison establishes a cause.

Comparison reports use `--limit`, `--page-size` and `--max-pages` with the
Core bounds, and preserve page metadata and completeness. They intentionally
do not use the 15-minute cache so an explicit exploration requests fresh data.
CLI flags from the other mode are rejected when they would be ignored.
MCP tools are `realtime_report` and `comparison_report` with matching arguments.

Sources: [Realtime request, response and minute ranges](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runRealtimeReport),
[comparison definition](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/Comparison),
[Core comparisons and date ranges](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport).
