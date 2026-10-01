# Discover report fields

Use the Data API schema before choosing property-specific fields. These are
explicit read operations; running a report does not run either check first.
They use the usual read credentials and scrub all returned strings.

## Metadata

```bash
python scripts/ga4_data.py --property 123 --metadata --json
python scripts/ga4_data.py --property 123 --metadata --no-cache --json
```

MCP: `report_metadata(property_id, use_cache=True)`.

The output contains `dimensions` and `metrics` lists, with the API's available
names, descriptions, types and custom-definition markers in snake_case.
An empty list is returned when the API supplies none. Property `0` requests
standard fields only; a real property ID includes its custom fields.
See [getMetadata](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/getMetadata).

Metadata uses the 15-minute query cache. `--no-cache` (or `use_cache=False`)
bypasses both cache reads and writes. Successful custom-dimension,
custom-metric and key-event creates/archives/deletes invalidate that
property's metadata cache. Key events affect their event-specific rate
metrics as described in the [schema](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema#key_event_rate_metrics_for_each_key_event).
External edits can remain cached until expiry; local invalidation does not
guarantee immediate API propagation. Existing cache concurrency limitations
still apply.

## Compatibility

```bash
python scripts/ga4_data.py --property 123 --check-compatibility --metrics sessions --dimensions date --filter "eventName = purchase" --json
```

MCP: `check_compatibility(property_id, metrics, dimensions,
filter_expr=None, filter_dict=None)`.

This returns `dimension_compatibilities` and `metric_compatibilities` with
the API's candidate fields and compatibility statuses. Incompatible selected
fields can produce an API error. It checks Core reports only; it cannot
validate funnels or realtime reports. See
[checkCompatibility](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/checkCompatibility).

Calls are uncached and do not run a report. Pass the same dimensions, metrics
and dimension filter as the intended report. CLI `--metrics` belongs to this
action; reports still use `--report METRICS`. Omit metrics or dimensions to
leave that selection empty. Add `date` explicitly when checking a daily
report. Dates, quota availability, data presence and permissions at a later
report request are not established by a successful compatibility response.

The MCP/Python `filter_dict` accepts the same shorthand or raw dimension
FilterExpression as `run_report` and takes precedence over `filter_expr`.
Metric filters are not exposed by these adapters. Use the existing report
path after inspecting the result; no field is automatically removed or replaced.

Parameter aggregate metrics return `coverage_pct: null` with `status: not_measurable`; positive revenue is not proof of complete tagging. Segment audits use the API `sessionKeyEventRate` and label findings `session_key_event_rate`.

Reports accept --limit (default 10000, maximum 250000), --page-size and --max-pages (default 10, maximum 100), --start-date/--end-date, --metric-filter JSON and --order-bys JSON. Responses expose complete, pages_fetched and incomplete_reason; do not treat partial results as totals. Partial results are not cached. Saved reports validate their schema, apply these options plus dimension_filter, and honor default_format unless --format overrides it. A saved segment is ANDed with the report filter. See docs/REPORT_FIELDS.md.

Pagination orders dimensions to stabilize offsets; it cannot guarantee a snapshot while source data changes. Every page retains its sampling and quota metadata under metadata.pages. Counts and rates are never summed across pages. Saved reports allow name, description, metrics, dimensions, default_days, default_format, dimension_filter, metric_filter, order_bys, limit, page_size, max_pages, start_date and end_date. Dates are ISO calendar dates and must be provided together. --days on a saved report overrides stored dates. Unknown definition/filter fields fail locally.

Funnel reports accept 2-10 unique steps and retain missing steps by default. --drop-missing explicitly changes the requested funnel. --check-postpayment is advisory and never removes steps. Validation uses the complete requested date window. Numbered API step names are normalized; breakdown rates use the named dimension and RESERVED_TOTAL rows, never summed segment populations. Missing totals or malformed rows produce an error instead of fabricated rates.
