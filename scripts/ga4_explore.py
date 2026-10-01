"""Explicit uncached realtime and same-property comparison reads."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

import ga4_data
from ga4_transport import error_result, read_call, read_operation
from ga4_utils import scrub_pii, scrub_response


@scrub_response
@read_operation
def realtime_report(
    property_id,
    metrics,
    dimensions,
    start_minutes_ago=29,
    end_minutes_ago=0,
    filter_dict=None,
    limit=10000,
):
    from google.analytics.data_v1beta.types import RunRealtimeReportRequest
    from google.protobuf.json_format import MessageToDict

    ga4_data.validate_report_options(limit=limit)
    if (
        type(start_minutes_ago) is not int
        or type(end_minutes_ago) is not int
        or not 0 <= end_minutes_ago <= start_minutes_ago <= 59
    ):
        raise ValueError(
            "minute range must satisfy 0 <= end <= start <= 59; over 29 requires GA360"
        )
    kwargs = dict(
        property=f"properties/{property_id}",
        metrics=[{"name": m} for m in metrics],
        dimensions=[{"name": d} for d in dimensions],
        limit=limit,
        minute_ranges=[dict(start_minutes_ago=start_minutes_ago, end_minutes_ago=end_minutes_ago)],
        return_property_quota=True,
    )
    if filter_dict:
        kwargs["dimension_filter"] = ga4_data.build_dimension_filter(filter_dict)
    response = read_call(
        ga4_data._get_data_client().run_realtime_report, RunRealtimeReportRequest(**kwargs)
    )
    out = ga4_data._serialize_run_report(response)
    out.update(
        report_type="realtime",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        complete=out["rows_returned"] == out["row_count"],
        pages_fetched=1,
        minute_range=dict(start_minutes_ago=start_minutes_ago, end_minutes_ago=end_minutes_ago),
        quota=MessageToDict(response.property_quota._pb, preserving_proto_field_name=True),
    )
    if not out["complete"]:
        out["incomplete_reason"] = "realtime_has_no_pagination; narrow_dimensions_or_raise_limit"
    return out


def _named_entries(entries, label):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 4:
        raise ValueError(f"{label} requires 1–4 named objects")
    names = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ValueError(f"{label} requires names")
        name = entry["name"]
        if not name.strip() or len(name) > 100 or name.startswith(("RESERVED_", "date_range_")):
            raise ValueError(f"invalid {label} name")
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError(f"{label} names must be unique")


@scrub_response
@read_operation
def comparison_report(
    property_id,
    metrics,
    dimensions,
    comparisons,
    date_ranges,
    limit=10000,
    page_size=10000,
    max_pages=10,
):
    from google.analytics.data_v1beta.types import Comparison, DateRange, RunReportRequest

    ga4_data.validate_report_options(limit, page_size, max_pages)
    _named_entries(comparisons, "comparisons")
    _named_entries(date_ranges, "date ranges")
    specs = []
    for entry in comparisons:
        if set(entry) - {"name", "dimension_filter", "comparison"}:
            raise ValueError("unknown comparison field")
        if ("dimension_filter" in entry) == ("comparison" in entry):
            raise ValueError(
                "each comparison needs exactly one dimension_filter or saved comparison"
            )
        if "dimension_filter" in entry:
            specs.append(
                Comparison(
                    name=entry["name"],
                    dimension_filter=ga4_data.build_dimension_filter(entry["dimension_filter"]),
                )
            )
        else:
            if not isinstance(entry["comparison"], str) or not re.fullmatch(
                r"comparisons/\d+", entry["comparison"]
            ):
                raise ValueError("saved comparison must be comparisons/ID from property metadata")
            specs.append(Comparison(**entry))
    for entry in date_ranges:
        if (
            set(entry) != {"name", "start_date", "end_date"}
            or not entry["start_date"]
            or not entry["end_date"]
        ):
            raise ValueError("date range requires name, start_date and end_date")
        ga4_data.validate_report_options(start_date=entry["start_date"], end_date=entry["end_date"])
    request = dict(
        property=f"properties/{property_id}",
        metrics=[{"name": m} for m in metrics],
        dimensions=[{"name": d} for d in dimensions],
        comparisons=specs,
        date_ranges=[DateRange(**r) for r in date_ranges],
        return_property_quota=True,
        order_bys=[{"dimension": {"dimension_name": d}} for d in dimensions],
    )
    out = ga4_data._paged_report(
        ga4_data._get_data_client(), RunReportRequest, request, limit, page_size, max_pages
    )
    out.update(
        report_type="same_property_comparisons",
        comparisons=comparisons,
        date_ranges=date_ranges,
        warning="Groups and date ranges may overlap. Do not add their user counts or infer causation.",
    )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--realtime", action="store_true")
    action.add_argument(
        "--comparisons", help="JSON list of named filters or saved comparison resources"
    )
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--dimensions", default="")
    parser.add_argument("--date-ranges", help="JSON list of named explicit date ranges")
    parser.add_argument("--filter", help="JSON dimension filter for realtime")
    parser.add_argument("--start-minutes-ago", type=int, default=29)
    parser.add_argument("--end-minutes-ago", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--page-size", type=int, default=10000)
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()
    try:
        common = (
            args.property,
            args.metrics.split(","),
            args.dimensions.split(",") if args.dimensions else [],
        )
        if args.realtime:
            if args.date_ranges or args.page_size != 10000 or args.max_pages != 10:
                raise ValueError("realtime uses minute ranges and has no pagination")
            out = realtime_report(
                *common,
                args.start_minutes_ago,
                args.end_minutes_ago,
                json.loads(args.filter) if args.filter else None,
                args.limit,
            )
        else:
            if args.filter or args.start_minutes_ago != 29 or args.end_minutes_ago != 0:
                raise ValueError("comparisons use their own filters and explicit date ranges")
            out = comparison_report(
                *common,
                json.loads(args.comparisons),
                json.loads(args.date_ranges or "null"),
                args.limit,
                args.page_size,
                args.max_pages,
            )
    except Exception as exc:
        print(json.dumps(error_result(exc)), file=sys.stderr)
        return 1
    print(json.dumps(scrub_pii(out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
