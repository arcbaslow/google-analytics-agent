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
from ga4_utils import cache_get, cache_set, scrub_pii, scrub_response

_FILTER_RE = re.compile(
    r"^\s*(?P<dim>[\w:]+)\s+(?P<op>=|!=|IN|CONTAINS|BEGINS_WITH)\s+(?P<val>.+?)\s*$",
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
    if type(days) is not int or days < 1:
        raise ValueError("days must be a positive integer")
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
    if not isinstance(filter_dict, dict) or not filter_dict:
        raise ValueError("filter must be a nonempty object")
    if {"field", "op"} <= set(filter_dict.keys()):
        if set(filter_dict) - {"field", "op", "value", "values", "not"}:
            raise ValueError("unsupported shorthand filter fields")
        return _build_filter_expression(filter_dict)
    from google.analytics.data_v1beta.types import FilterExpression
    from google.protobuf.json_format import ParseDict, ParseError

    try:
        pb = ParseDict(filter_dict, FilterExpression.pb(FilterExpression()))
    except ParseError as exc:
        raise ValueError(f"invalid filter: {scrub_pii(str(exc))}") from None
    return FilterExpression.wrap(pb)


def _schema_response(response, list_fields):
    from google.protobuf.json_format import MessageToDict

    out = MessageToDict(response._pb, preserving_proto_field_name=True)
    for field in list_fields:
        out.setdefault(field, [])
    return scrub_pii(out)


@scrub_response
def get_metadata(property_id, use_cache=True):
    """Discover standard and property-specific fields; property 0 is standard-only."""
    from google.analytics.data_v1beta.types import GetMetadataRequest

    cache_args = ("report_metadata", property_id)
    if use_cache:
        cached = cache_get(*cache_args)
        if cached is not None:
            return cached
    response = _get_data_client().get_metadata(
        GetMetadataRequest(name=f"properties/{property_id}/metadata")
    )
    out = _schema_response(response, ("dimensions", "metrics"))
    if use_cache:
        cache_set(out, *cache_args)
    return out


@scrub_response
def check_compatibility(property_id, metrics, dimensions, filter_expr=None, filter_dict=None):
    """Explicit, uncached Core compatibility read; no report or automatic preflight.

    Returns candidate field compatibility from the API. Incompatible selected
    fields may raise an API error. Uses the same dimension-filter precedence
    as run_report; metric filters are not supported by either adapter.
    """
    from google.analytics.data_v1beta.types import CheckCompatibilityRequest, Dimension, Metric

    kwargs = {
        "property": f"properties/{property_id}",
        "metrics": [Metric(name=name) for name in metrics],
        "dimensions": [Dimension(name=name) for name in dimensions],
    }
    if filter_dict:
        kwargs["dimension_filter"] = build_dimension_filter(filter_dict)
    elif filter_expr:
        kwargs["dimension_filter"] = _build_filter_expression(parse_filter(filter_expr))
    response = _get_data_client().check_compatibility(CheckCompatibilityRequest(**kwargs))
    return _schema_response(response, ("dimension_compatibilities", "metric_compatibilities"))


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
    limit=10000,
    page_size=10000,
    max_pages=10,
    start_date=None,
    end_date=None,
    metric_filter=None,
    order_bys=None,
):
    """Run a Data API report. Returns dict with rows + optional metadata.

    When both are supplied, filter_dict (a prebuilt filter dict) wins over
    filter_expr (a 'dim OP value' string)."""
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Metric,
        OrderBy,
        RunReportRequest,
    )

    validate_report_options(limit, page_size, max_pages, start_date, end_date)

    if daily and "date" not in dimensions:
        dimensions = ["date", *dimensions]

    start, end = (start_date, end_date) if start_date else date_range(days)
    cache_args = (
        "run_report",
        property_id,
        tuple(metrics),
        tuple(dimensions),
        filter_expr,
        json.dumps(filter_dict, sort_keys=True) if filter_dict else None,
        start,
        end,
        include_metadata,
        limit,
        page_size,
        max_pages,
        json.dumps(metric_filter, sort_keys=True),
        json.dumps(order_bys, sort_keys=True),
    )
    if use_cache:
        cached = cache_get(*cache_args)
        if cached is not None:
            return cached

    client = _get_data_client()
    req_kwargs = {
        "property": f"properties/{property_id}",
        "metrics": [Metric(name=m) for m in metrics],
        "dimensions": [Dimension(name=d) for d in dimensions],
        "date_ranges": [DateRange(start_date=start, end_date=end)],
        "return_property_quota": include_metadata,
        "order_bys": [OrderBy(**order) for order in (order_bys or [])]
        + [OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name=d)) for d in dimensions],
    }
    if metric_filter:
        req_kwargs["metric_filter"] = build_dimension_filter(metric_filter)
    if filter_dict:
        req_kwargs["dimension_filter"] = build_dimension_filter(filter_dict)
    elif filter_expr:
        parsed = parse_filter(filter_expr)
        if parsed:
            req_kwargs["dimension_filter"] = _build_filter_expression(parsed)

    out = None
    page_metadata = []
    reason = None
    for page_index in range(max_pages):
        offset = len(out["rows"]) if out else 0
        response = client.run_report(
            RunReportRequest(**req_kwargs, offset=offset, limit=min(page_size, limit - offset))
        )
        page = _serialize_run_report(response, include_metadata=include_metadata)
        if out is None:
            out = {**page, "rows": []}
        elif any(page[key] != out[key] for key in ("row_count", "dimensions", "metrics")):
            reason = "report_changed_between_pages"
            break
        if include_metadata:
            page_metadata.append(dict(page["metadata"]))
        out["rows"].extend(page["rows"][: limit - offset])
        if len(out["rows"]) >= out["row_count"]:
            break
        if not page["rows"]:
            reason = "empty_page_before_end"
            break
        if len(out["rows"]) >= limit:
            reason = "row_limit"
            break
    assert out is not None
    out["rows_returned"] = len(out["rows"])
    out["pages_fetched"] = page_index + 1
    out["complete"] = reason is None and out["rows_returned"] == out["row_count"]
    if not out["complete"]:
        out["incomplete_reason"] = reason or "page_limit"
    if include_metadata:
        out["metadata"]["pages"] = page_metadata
    out = scrub_pii(out)
    if use_cache and out["complete"]:
        cache_set(out, *cache_args)
    return out


def validate_report_options(
    limit=10000, page_size=10000, max_pages=10, start_date=None, end_date=None
):
    """Bound total work locally before constructing a client."""
    for name, value, maximum in (
        ("limit", limit, 250000),
        ("page_size", page_size, 250000),
        ("max_pages", max_pages, 100),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    if bool(start_date) != bool(end_date):
        raise ValueError("start_date and end_date must be supplied together")
    if start_date:
        if date.fromisoformat(start_date) > date.fromisoformat(end_date):
            raise ValueError("start_date must not follow end_date")


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
        for sm in getattr(response.metadata, "sampling_metadatas", []) or []:
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
        # Serialize optional fields only when this SDK knows them. September
        # 2026 truncation fields are absent from older supported clients.
        from google.protobuf.json_format import MessageToDict
        from google.protobuf.message import Message

        metadata_pb = getattr(response.metadata, "_pb", None)
        if isinstance(metadata_pb, Message):
            raw_meta = MessageToDict(metadata_pb, preserving_proto_field_name=True)
            for field in (
                "subject_to_thresholding",
                "empty_reason",
                "schema_restriction_response",
                "data_truncation_reasons",
            ):
                if field in raw_meta:
                    out["metadata"][field] = raw_meta[field]
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
    if not 2 <= len(steps) <= 10 or len(set(steps)) != len(steps):
        raise ValueError("funnel needs 2 to 10 unique steps")
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
        if cached is not None:
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
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--report", help="Comma-separated metric names")
    actions.add_argument("--funnel-report", action="store_true")
    actions.add_argument("--metadata", action="store_true", help="Discover available report fields")
    actions.add_argument(
        "--check-compatibility", action="store_true", help="Check Core report fields"
    )
    parser.add_argument("--metrics", help="Comma-separated metrics for --check-compatibility")
    parser.add_argument("--steps", help="Comma-separated event names for funnel")
    parser.add_argument("--breakdown", help="Optional funnel breakdown dimension")
    parser.add_argument("--dimensions", help="Comma-separated dimension names")
    parser.add_argument("--filter", help="Filter: 'dim OP value'")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--include-metadata", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--page-size", type=int, default=10000)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--metric-filter", help="FilterExpression JSON")
    parser.add_argument("--order-bys", help="JSON list of OrderBy objects")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.metrics is not None and not args.check_compatibility:
        parser.error("--metrics requires --check-compatibility; use --report METRICS for a report")

    use_cache = not args.no_cache
    try:
        if args.metadata:
            result = get_metadata(args.property, use_cache=use_cache)
        elif args.check_compatibility:
            result = check_compatibility(
                args.property,
                metrics=[m.strip() for m in (args.metrics or "").split(",") if m.strip()],
                dimensions=[d.strip() for d in (args.dimensions or "").split(",") if d.strip()],
                filter_expr=args.filter,
            )
        elif args.funnel_report:
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
                print(
                    "ERROR: select --report, --funnel-report, --metadata or --check-compatibility",
                    file=sys.stderr,
                )
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
                limit=args.limit,
                page_size=args.page_size,
                max_pages=args.max_pages,
                start_date=args.start_date,
                end_date=args.end_date,
                metric_filter=json.loads(args.metric_filter) if args.metric_filter else None,
                order_bys=json.loads(args.order_bys) if args.order_bys else None,
            )
    except Exception as e:
        print(json.dumps({"error": scrub_pii(str(e)), "type": type(e).__name__}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
