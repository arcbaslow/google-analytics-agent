# BigQuery aggregate evidence

Install the optional free client with `pip install -e ".[bigquery]"`. This
adapter uses existing BigQuery ADC with the `bigquery` OAuth scope, separate
from the Analytics scope. The billing project needs `bigquery.jobs.create`;
the principal also needs read access to the source export. It does not start
login, create credentials, create datasets, or configure GA4 exports.

```sh
python scripts/ga4_bigquery.py --billing-project billing-project \
  --source-project source-project --dataset analytics_123 --location US \
  --start-date 2026-09-01 --end-date 2026-09-02 \
  --template parameters --event-name purchase --parameters value,currency \
  --max-bytes 1073741824
```

The default makes a dry-run estimate and returns the SQL and bound values.
Dates are inclusive and limited to 31 days. Review that output before adding
`--execute`, which can incur BigQuery query charges. Every execution repeats
the estimate and refuses a missing, negative or over-budget estimate. The
same byte cap is enforced on the real job (default 1 GiB, maximum 100 GiB).
This is a scan limit, not a currency estimate or reservation-cost guarantee.
The MCP `bigquery_dry_run` tool has no execution argument. Agents must get
explicit user authorization before running a billable CLI query.

Only four fixed SELECT templates are available:

- `parameters`: `--event-name` and 1–50 comma-separated `--parameters`.
  Counts exported events, events with the key, and events with a nonempty
  string or non-null numeric value. Zero is a usable numeric value. Duplicate
  keys do not multiply events. This covers top-level `event_params`, not item
  fields; empty results have no measurable denominator.
- `consent`: counts combinations of the three `privacy_info` fields. These
  are exported observations, not a legal-compliance finding or tag audit.
- `freshness`: latest observed event timestamp in microseconds, event date,
  event count and number of observed daily tables. This does not establish
  export-job health or that every day's export is complete.
- `funnel`: 2–7 unique comma-separated `--steps`, with `--window-seconds`
  (default 3600, maximum 2678400). Each user's first occurrence of step one
  in the selected dates anchors a strict, increasing-timestamp sequence.
  Later steps must fit that first-entry window. Null pseudo IDs and tied
  timestamps cannot establish a sequence. This is not GA4's modeled funnel
  or a search for any later qualifying entry. Only per-step counts leave
  BigQuery; no user identifiers or individual rows are returned.

Queries read daily `events_YYYYMMDD` tables only. Intraday tables are excluded
to prevent overlap. Missing days and late export updates affect the evidence;
no result is cached. Fixed identifiers are validated and values are query
parameters. There is no arbitrary SQL, DML, destination table or member export.

Submission and job retries are disabled. The client waits up to 60 seconds,
and requests a 180-second server timeout (best effort). A failed or timed-out
execution returns its preassigned job ID and an unknown outcome: inspect that
job in the stated billing project/location before submitting another query.
Do not assume the job was canceled. Results are capped at 1000 aggregate rows
and identify incompleteness. All responses and errors pass through scrubbing.

Tests mock all client calls and execute generated SQL, translated to DuckDB,
against synthetic in-memory export rows. That checks denominator and sequence
semantics; it does not verify live BigQuery SQL acceptance, IAM or billing.

Sources: [GA4 export schema](https://support.google.com/analytics/answer/7029846?hl=en),
[job scopes and permissions](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/jobs/insert),
[cost controls](https://docs.cloud.google.com/bigquery/docs/best-practices-costs),
[Python client](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client).
