"""Fixed aggregate queries over GA4 daily exports. Dry-run unless explicitly executed."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date

from ga4_transport import error_result
from ga4_utils import scrub_pii, scrub_response

TEMPLATES = ("parameters", "consent", "freshness", "funnel")
COLUMNS = {
    "parameters": ("parameter", "events", "present", "usable"),
    "consent": ("analytics_storage", "ads_storage", "uses_transient_token", "events"),
    "freshness": ("latest_event_micros", "latest_event_date", "events", "observed_daily_tables"),
    "funnel": ("step", "event_name", "users"),
}


def _get_client(billing_project, location):
    import google.auth
    from google.cloud import bigquery

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
    return bigquery.Client(project=billing_project, credentials=credentials, location=location)


def _identifier(value, pattern, label):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(f"invalid {label}")
    return value


def _names(values, minimum, maximum, label):
    if not isinstance(values, list) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} needs {minimum}–{maximum} unique names")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} names must be unique")
    for value in values:
        _identifier(value, r"[A-Za-z_][A-Za-z0-9_]{0,39}", label)


def build_query(
    source_project,
    dataset,
    start_date,
    end_date,
    template,
    event_name=None,
    parameters=None,
    steps=None,
    window_seconds=3600,
):
    """Return fixed SELECT SQL and typed values, without resolving credentials."""
    _identifier(source_project, r"[a-z][a-z0-9-]{4,28}[a-z0-9]", "source project")
    _identifier(dataset, r"[A-Za-z_][A-Za-z0-9_]{0,1023}", "dataset")
    for value in (start_date, end_date):
        _identifier(value, r"\d{4}-\d{2}-\d{2}", "date (YYYY-MM-DD)")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if not 0 <= (end - start).days < 31:
        raise ValueError("date range must contain 1–31 days")
    if template not in TEMPLATES:
        raise ValueError("unknown aggregate template")
    values = [
        ("start", "STRING", start.strftime("%Y%m%d")),
        ("end", "STRING", end.strftime("%Y%m%d")),
    ]
    source = f"`{source_project}.{dataset}.events_*`"
    where = "_TABLE_SUFFIX BETWEEN @start AND @end AND REGEXP_CONTAINS(_TABLE_SUFFIX, r'^\\d{8}$')"
    if template == "parameters":
        _identifier(event_name, r"[A-Za-z_][A-Za-z0-9_]{0,39}", "event name")
        _names(parameters, 1, 50, "parameters")
        values += [("event", "STRING", event_name), ("parameters", "ARRAY", parameters)]
        # EXISTS counts each event once even if the export contains duplicate keys.
        sql = f"""WITH events AS (SELECT event_params FROM {source} WHERE {where} AND event_name = @event)
SELECT parameter, COUNT(*) AS events,
COUNTIF(EXISTS(SELECT 1 FROM UNNEST(event_params) p WHERE p.key = parameter)) AS present,
COUNTIF(EXISTS(SELECT 1 FROM UNNEST(event_params) p WHERE p.key = parameter AND
 (NULLIF(p.value.string_value, '') IS NOT NULL OR p.value.int_value IS NOT NULL OR
  p.value.double_value IS NOT NULL OR p.value.float_value IS NOT NULL))) AS usable
FROM events CROSS JOIN UNNEST(@parameters) AS parameter GROUP BY parameter ORDER BY parameter"""
    elif template == "consent":
        sql = f"""SELECT privacy_info.analytics_storage AS analytics_storage,
privacy_info.ads_storage AS ads_storage, privacy_info.uses_transient_token AS uses_transient_token,
COUNT(*) AS events FROM {source} WHERE {where}
GROUP BY analytics_storage, ads_storage, uses_transient_token
ORDER BY analytics_storage, ads_storage, uses_transient_token"""
    elif template == "freshness":
        sql = f"""SELECT MAX(event_timestamp) AS latest_event_micros, MAX(event_date) AS latest_event_date,
COUNT(*) AS events, COUNT(DISTINCT _TABLE_SUFFIX) AS observed_daily_tables FROM {source} WHERE {where}"""
    else:
        _names(steps, 2, 7, "steps")
        if type(window_seconds) is not int or not 1 <= window_seconds <= 31 * 86400:
            raise ValueError("window_seconds must be between 1 and 2678400")
        values += [("window_micros", "INT64", window_seconds * 1000000)]
        values += [(f"step{i}", "STRING", name) for i, name in enumerate(steps)]
        ctes = [
            f"events AS (SELECT user_pseudo_id, event_name, event_timestamp FROM {source} WHERE {where} AND user_pseudo_id IS NOT NULL)",
            "s0 AS (SELECT user_pseudo_id, MIN(event_timestamp) AS first_time, MIN(event_timestamp) AS step_time FROM events WHERE event_name = @step0 GROUP BY user_pseudo_id)",
        ]
        for i in range(1, len(steps)):
            ctes.append(f"""s{i} AS (SELECT p.user_pseudo_id, p.first_time, MIN(e.event_timestamp) AS step_time
FROM s{i - 1} p JOIN events e ON e.user_pseudo_id = p.user_pseudo_id
AND e.event_name = @step{i} AND e.event_timestamp > p.step_time
AND e.event_timestamp <= p.first_time + @window_micros GROUP BY p.user_pseudo_id, p.first_time)""")
        rows = [
            f"SELECT {i + 1} AS step, @step{i} AS event_name, COUNT(*) AS users FROM s{i}"
            for i in range(len(steps))
        ]
        sql = "WITH " + ",\n".join(ctes) + "\n" + "\nUNION ALL\n".join(rows) + "\nORDER BY step"
    return sql, values


@scrub_response
def aggregate_evidence(
    billing_project,
    source_project,
    dataset,
    location,
    start_date,
    end_date,
    template,
    event_name=None,
    parameters=None,
    steps=None,
    window_seconds=3600,
    max_bytes=1073741824,
    execute=False,
):
    _identifier(billing_project, r"[a-z][a-z0-9-]{4,28}[a-z0-9]", "billing project")
    _identifier(location, r"[A-Za-z][A-Za-z0-9-]{0,39}", "location")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 100 * 1024**3:
        raise ValueError("max_bytes must be between 1 byte and 100 GiB")
    if type(execute) is not bool:
        raise ValueError("execute must be a boolean")
    sql, values = build_query(
        source_project,
        dataset,
        start_date,
        end_date,
        template,
        event_name,
        parameters,
        steps,
        window_seconds,
    )
    try:
        from google.cloud import bigquery
    except ImportError:
        return {"status": "unsupported", "reason": "Install google-analytics-agent[bigquery]."}
    params = [
        bigquery.ArrayQueryParameter(n, "STRING", v)
        if t == "ARRAY"
        else bigquery.ScalarQueryParameter(n, t, v)
        for n, t, v in values
    ]
    client = _get_client(billing_project, location)
    config = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
        use_legacy_sql=False,
        maximum_bytes_billed=max_bytes,
        query_parameters=params,
    )
    estimate = client.query(
        sql, job_config=config, location=location, retry=None, job_retry=None, timeout=30
    ).total_bytes_processed
    result = {
        "status": "dry_run",
        "template": template,
        "estimated_bytes": estimate,
        "maximum_bytes_billed": max_bytes,
        "sql": sql,
        "parameters": {n: v for n, _, v in values},
        "billing_project": billing_project,
        "source": f"{source_project}.{dataset}.events_*",
        "location": location,
        "scope": "daily export only; no intraday tables or modeled GA4 data",
    }
    if not execute:
        return result
    if type(estimate) is not int or estimate < 0 or estimate > max_bytes:
        return {
            **result,
            "status": "execution_refused",
            "reason": "Missing or over-budget estimate.",
        }
    # No submit or job retries: a lost response must not silently submit a second billable job.
    config = bigquery.QueryJobConfig.from_api_repr(config.to_api_repr())
    config.dry_run = False
    config.job_timeout_ms = 180000
    job_id = "ga4_" + uuid.uuid4().hex.translate(
        str.maketrans("0123456789abcdef", "abcdefghijklmnop")
    )
    result["job_id"] = job_id
    try:
        job = client.query(
            sql,
            job_config=config,
            location=location,
            job_id=job_id,
            retry=None,
            job_retry=None,
            timeout=30,
        )
        rows = job.result(timeout=60, retry=None, job_retry=None, max_results=1000)
        result["rows"] = [{column: row[column] for column in COLUMNS[template]} for row in rows]
        result["complete"] = rows.total_rows == len(result["rows"])
        result["status"] = "complete" if result["complete"] else "incomplete"
        result["bytes_processed"] = job.total_bytes_processed
        result["bytes_billed"] = job.total_bytes_billed
    except Exception as exc:
        result.update(error_result(exc))
        result.update(
            status="outcome_unknown",
            complete=False,
            warning="The job may still be running. Inspect its ID before submitting again.",
            retryable=False,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "billing-project",
        "source-project",
        "dataset",
        "location",
        "start-date",
        "end-date",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--template", choices=TEMPLATES, required=True)
    parser.add_argument("--event-name")
    parser.add_argument("--parameters")
    parser.add_argument("--steps")
    parser.add_argument("--window-seconds", type=int, default=3600)
    parser.add_argument("--max-bytes", type=int, default=1073741824)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the billable aggregate query after its dry-run check",
    )
    args = vars(parser.parse_args())
    for field in ("parameters", "steps"):
        if args[field]:
            args[field] = args[field].split(",")
    try:
        result = aggregate_evidence(**args)
    except Exception as exc:
        print(json.dumps(error_result(exc)), file=sys.stderr)
        return 1
    print(json.dumps(scrub_pii(result), indent=2))
    return 0 if result["status"] in ("dry_run", "complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
