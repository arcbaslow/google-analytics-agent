"""Explicit, uncached alpha advertising conversion reports, separate from key events."""

from __future__ import annotations

import argparse
import json
import re
import sys

import ga4_data
from ga4_transport import error_result, read_call, read_operation
from ga4_utils import scrub_pii, scrub_response


def _supported():
    from google.analytics.data_v1alpha import types

    return hasattr(types, "ConversionSpec")


def _unsupported():
    return {
        "status": "unsupported",
        "reason": "Installed Data client lacks alpha conversion reporting.",
    }


@scrub_response
@read_operation
def conversion_metadata(property_id):
    if not _supported():
        return _unsupported()
    from google.analytics.data_v1alpha.types import GetMetadataRequest

    response = read_call(
        ga4_data._get_data_alpha_client().get_metadata,
        GetMetadataRequest(name=f"properties/{property_id}/metadata"),
    )
    return ga4_data._schema_response(
        response, ("dimensions", "metrics", "comparisons", "conversions")
    )


@scrub_response
@read_operation
def run_conversion_report(
    property_id,
    metrics,
    dimensions,
    start_date,
    end_date,
    conversion_actions=None,
    attribution_model="DATA_DRIVEN",
    limit=10000,
    page_size=10000,
    max_pages=10,
):
    ga4_data.validate_report_options(limit, page_size, max_pages, start_date, end_date)
    if not start_date or not end_date:
        raise ValueError("explicit start_date and end_date are required")
    if attribution_model not in ("DATA_DRIVEN", "LAST_CLICK"):
        raise ValueError("attribution_model must be DATA_DRIVEN or LAST_CLICK")
    actions = conversion_actions or []
    if not isinstance(actions, list) or any(
        not re.fullmatch(r"conversionActions/\d+", a) for a in actions
    ):
        raise ValueError("conversion_actions must contain conversionActions/ID names from metadata")
    if not _supported():
        return _unsupported()
    from google.analytics.data_v1alpha.types import ConversionSpec, RunReportRequest

    request = {
        "property": f"properties/{property_id}",
        "metrics": [{"name": metric} for metric in metrics],
        "dimensions": [{"name": dimension} for dimension in dimensions],
        "date_ranges": [{"start_date": start_date, "end_date": end_date}],
        "conversion_spec": ConversionSpec(
            conversion_actions=actions, attribution_model=attribution_model
        ),
        "order_bys": [{"dimension": {"dimension_name": d}} for d in dimensions],
        "return_property_quota": True,
    }
    result = ga4_data._paged_report(
        ga4_data._get_data_alpha_client(), RunReportRequest, request, limit, page_size, max_pages
    )
    result["report_type"] = "advertising_conversions"
    result["conversion_spec"] = {
        "conversion_actions": actions,
        "attribution_model": attribution_model,
    }
    result["section_verified"] = all(
        page.get("section") == "SECTION_ADVERTISING" for page in result["metadata"]["pages"]
    )
    if not result["section_verified"]:
        result["warning"] = (
            "The API did not confirm the Advertising section; do not interpret this as a verified conversion report."
        )
    return result


def main():
    parser = argparse.ArgumentParser(description="GA4 alpha advertising conversion reports")
    parser.add_argument("--property", required=True)
    parser.add_argument("--metadata", action="store_true")
    parser.add_argument("--metrics", default="allConversionsByConversionDate")
    parser.add_argument("--dimensions", default="defaultChannelGroup")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--conversion-actions", default="")
    parser.add_argument(
        "--attribution-model", choices=("DATA_DRIVEN", "LAST_CLICK"), default="DATA_DRIVEN"
    )
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--page-size", type=int, default=10000)
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()
    try:
        result = (
            conversion_metadata(args.property)
            if args.metadata
            else run_conversion_report(
                args.property,
                args.metrics.split(","),
                args.dimensions.split(",") if args.dimensions else [],
                args.start_date,
                args.end_date,
                args.conversion_actions.split(",") if args.conversion_actions else [],
                args.attribution_model,
                args.limit,
                args.page_size,
                args.max_pages,
            )
        )
    except Exception as exc:
        print(json.dumps(error_result(exc)), file=sys.stderr)
        return 1
    print(json.dumps(scrub_pii(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
