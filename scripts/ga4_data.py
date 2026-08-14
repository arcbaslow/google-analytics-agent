"""
GA4 Data API wrapper.

runReport and runFunnelReport (v1alpha) with filter parsing, sampling metadata,
local caching, PII scrubbing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta

from ga4_auth import get_credentials
from ga4_utils import cache_get, cache_set, scrub_pii

_FILTER_RE = re.compile(
    r"^\s*(?P<dim>\w+)\s+(?P<op>=|!=|IN|CONTAINS|BEGINS_WITH)\s+(?P<val>.+?)\s*$",
    re.IGNORECASE,
)


def parse_filter(expr):
    """Parse 'dimension OP value' into a dict the API client builders can consume."""
    if not expr:
        return None
    m = _FILTER_RE.match(expr)
    if not m:
        raise ValueError(f"Unparseable filter: {expr!r}")
    dim = m.group("dim")
    op = m.group("op").upper()
    val = m.group("val").strip()

    if op == "IN":
        val = val.strip("()")
        values = [v.strip().strip("'\"") for v in val.split(",") if v.strip()]
        return {"field": dim, "op": "IN_LIST", "values": values}

    val = val.strip("'\"")
    if op == "=":
        return {"field": dim, "op": "EXACT", "value": val}
    if op == "!=":
        return {"field": dim, "op": "EXACT", "value": val, "not": True}
    if op == "CONTAINS":
        return {"field": dim, "op": "CONTAINS", "value": val}
    if op == "BEGINS_WITH":
        return {"field": dim, "op": "BEGINS_WITH", "value": val}
    raise ValueError(f"Unsupported operator: {op}")


def date_range(days):
    """Return (start_date, end_date) as YYYY-MM-DD, end = yesterday."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _get_data_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    return BetaAnalyticsDataClient(credentials=get_credentials())


def _get_data_alpha_client():
    from google.analytics.data_v1alpha import AlphaAnalyticsDataClient

    return AlphaAnalyticsDataClient(credentials=get_credentials())


def _build_filter_expression(parsed):
    from google.analytics.data_v1beta.types import Filter, FilterExpression

    op = parsed["op"]
    field = parsed["field"]
    if op == "IN_LIST":
        f = Filter(field_name=field, in_list_filter=Filter.InListFilter(values=parsed["values"]))
    elif op == "EXACT":
        f = Filter(
            field_name=field,
            string_filter=Filter.StringFilter(
                value=parsed["value"], match_type=Filter.StringFilter.MatchType.EXACT
            ),
        )
    elif op == "CONTAINS":
        f = Filter(
            field_name=field,
            string_filter=Filter.StringFilter(
                value=parsed["value"], match_type=Filter.StringFilter.MatchType.CONTAINS
            ),
        )
    elif op == "BEGINS_WITH":
        f = Filter(
            field_name=field,
            string_filter=Filter.StringFilter(
                value=parsed["value"], match_type=Filter.StringFilter.MatchType.BEGINS_WITH
            ),
        )
    else:
        raise ValueError(f"Unsupported filter op: {op}")
    expr = FilterExpression(filter=f)
    if parsed.get("not"):
        expr = FilterExpression(not_expression=expr)
    return expr


def build_dimension_filter(filter_dict):
    """Build a Data API FilterExpression from a stored filter dict.

    Accepts the shorthand shape used for stored segments
    ({"field","op","value"|"values", optional "not"} — the same dict
    parse_filter() produces) and the raw FilterExpression schema
    (and_group / or_group / not_expression / filter).
    FilterExpression is a proto-plus wrapper, so the raw path parses into the
    underlying protobuf via .pb() and wraps the result (ParseDict cannot target
    a proto-plus message directly)."""
    if {"field", "op"} <= set(filter_dict.keys()):
        return _build_filter_expression(filter_dict)
    from google.analytics.data_v1beta.types import FilterExpression
    from google.protobuf.json_format import ParseDict

    pb = ParseDict(filter_dict, FilterExpression.pb(FilterExpression()), ignore_unknown_fields=True)
    return FilterExpression.wrap(pb)


def run_report(
    property_id,
    metrics,
    dimensions,
    filter_expr=None,
    filter_dict=None,
    days=28,
    daily=False,
    include_metadata=False,
    use_cache=True,
):
    """Run a Data API report. Returns dict with rows + optional metadata.

    When both are supplied, filter_dict (a prebuilt filter dict) wins over
    filter_expr (a 'dim OP value' string)."""
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    if daily and "date" not in dimensions:
        dimensions = ["date", *dimensions]

    start, end = date_range(days)
    cache_args = (
        "run_report",
        property_id,
        tuple(sorted(metrics)),
        tuple(sorted(dimensions)),
        filter_expr,
        json.dumps(filter_dict, sort_keys=True) if filter_dict else None,
        start,
        end,
        include_metadata,
    )
    if use_cache:
        cached = cache_get(*cache_args)
        if cached:
            return cached

    client = _get_data_client()
    req_kwargs = {
        "property": f"properties/{property_id}",
        "metrics": [Metric(name=m) for m in metrics],
        "dimensions": [Dimension(name=d) for d in dimensions],
        "date_ranges": [DateRange(start_date=start, end_date=end)],
        "return_property_quota": include_metadata,
    }
    if filter_dict:
        req_kwargs["dimension_filter"] = build_dimension_filter(filter_dict)
    elif filter_expr:
        parsed = parse_filter(filter_expr)
        if parsed:
            req_kwargs["dimension_filter"] = _build_filter_expression(parsed)

    response = client.run_report(RunReportRequest(**req_kwargs))
    out = _serialize_run_report(response, include_metadata=include_metadata)
    out = scrub_pii(out)
    if use_cache:
        cache_set(out, *cache_args)
    return out


def _serialize_run_report(response, include_metadata=False):
    rows = []
    dim_headers = [h.name for h in response.dimension_headers]
    metric_headers = [h.name for h in response.metric_headers]
    for r in response.rows:
        row = {}
        for i, dv in enumerate(r.dimension_values):
            row[dim_headers[i]] = dv.value
        for i, mv in enumerate(r.metric_values):
            row[metric_headers[i]] = mv.value
        rows.append(row)
    out = {
        "row_count": response.row_count,
        "rows_returned": len(rows),
        "dimensions": dim_headers,
        "metrics": metric_headers,
        "rows": rows,
    }
    if include_metadata:
        sampling = []
        for sm in response.metadata.sampling_metadatas or []:
            sampling.append(
                {
                    "samples_read_count": sm.samples_read_count,
                    "sampling_space_size": sm.sampling_space_size,
                    "sample_rate": (
                        sm.samples_read_count / sm.sampling_space_size
                        if sm.sampling_space_size
                        else 1.0
                    ),
                }
            )
        out["metadata"] = {
            "sampling": sampling,
            "data_loss_from_other_row": response.metadata.data_loss_from_other_row,
            "currency_code": response.metadata.currency_code,
            "time_zone": response.metadata.time_zone,
        }
        if response.property_quota:
            pq = response.property_quota
            out["metadata"]["quota"] = {
                "tokens_per_day_remaining": pq.tokens_per_day.remaining,
                "tokens_per_hour_remaining": pq.tokens_per_hour.remaining,
                "concurrent_requests_remaining": pq.concurrent_requests.remaining,
            }
    return out


def run_funnel_report(property_id, steps, days=28, breakdown_dimension=None, use_cache=True):
    """Run a v1alpha funnel report keyed on eventName per step."""
    from google.analytics.data_v1alpha.types import (
        DateRange,
        Dimension,
        Funnel,
        FunnelBreakdown,
        FunnelEventFilter,
        FunnelFilterExpression,
        FunnelStep,
        RunFunnelReportRequest,
    )

    start, end = date_range(days)
    cache_args = ("run_funnel_report", property_id, tuple(steps), breakdown_dimension, start, end)
    if use_cache:
        cached = cache_get(*cache_args)
        if cached:
            return cached

    funnel_steps = []
    for event_name in steps:
        step_filter = FunnelFilterExpression(
            funnel_event_filter=FunnelEventFilter(event_name=event_name)
        )
        funnel_steps.append(FunnelStep(name=event_name, filter_expression=step_filter))

    funnel = Funnel(steps=funnel_steps)
    req_kwargs = {
        "property": f"properties/{property_id}",
        "funnel": funnel,
        "date_ranges": [DateRange(start_date=start, end_date=end)],
    }
    if breakdown_dimension:
        req_kwargs["funnel_breakdown"] = FunnelBreakdown(
            breakdown_dimension=Dimension(name=breakdown_dimension)
        )

    client = _get_data_alpha_client()
    response = client.run_funnel_report(RunFunnelReportRequest(**req_kwargs))
    out = _serialize_funnel_report(response, steps=steps)
    out = scrub_pii(out)
    if use_cache:
        cache_set(out, *cache_args)
    return out


def _serialize_funnel_report(response, steps):
    steps_out = []
    table = response.funnel_table
    if table:
        dim_headers = [h.name for h in table.dimension_headers]
        metric_headers = [h.name for h in table.metric_headers]
        for r in table.rows:
            row = {}
            for i, dv in enumerate(r.dimension_values):
                row[dim_headers[i]] = dv.value
            for i, mv in enumerate(r.metric_values):
                row[metric_headers[i]] = mv.value
            steps_out.append(row)
    return {"steps": steps, "step_count": len(steps), "rows": steps_out}


def main():
    parser = argparse.ArgumentParser(description="GA4 Data API wrapper")
    parser.add_argument("--property", required=True)
    parser.add_argument("--report", help="Comma-separated metric names")
    parser.add_argument("--funnel-report", action="store_true")
    parser.add_argument("--steps", help="Comma-separated event names for funnel")
    parser.add_argument("--breakdown", help="Optional funnel breakdown dimension")
    parser.add_argument("--dimensions", help="Comma-separated dimension names")
    parser.add_argument("--filter", help="Filter: 'dim OP value'")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--include-metadata", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    use_cache = not args.no_cache
    try:
        if args.funnel_report:
            if not args.steps:
                print("ERROR: --steps required with --funnel-report", file=sys.stderr)
                return 1
            steps = [s.strip() for s in args.steps.split(",") if s.strip()]
            result = run_funnel_report(
                args.property,
                steps,
                days=args.days,
                breakdown_dimension=args.breakdown,
                use_cache=use_cache,
            )
        else:
            if not args.report:
                print("ERROR: --report required (or use --funnel-report)", file=sys.stderr)
                return 1
            metrics = [m.strip() for m in args.report.split(",") if m.strip()]
            dimensions = [d.strip() for d in (args.dimensions or "").split(",") if d.strip()]
            result = run_report(
                args.property,
                metrics,
                dimensions,
                filter_expr=args.filter,
                days=args.days,
                daily=args.daily,
                include_metadata=args.include_metadata,
                use_cache=use_cache,
            )
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
