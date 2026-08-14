"""
GA4 event taxonomy validator. Built on ga4_data.run_report.

The REQUIRED_PARAMS table covers Google's recommended e-commerce events as one
example preset. For non-ecomm taxonomies pass `--required-params` JSON on the
CLI or call event_params_coverage() with a custom required-params dict.

CLI:
  python scripts/ga4_events.py --property <id> --list-events --days 7 --json
  python scripts/ga4_events.py --property <id> --check-events sign_up,purchase --json
  python scripts/ga4_events.py --property <id> --event-params purchase --json
  python scripts/ga4_events.py --property <id> --detect-postpayment-api --json
"""

from __future__ import annotations

import argparse
import json
import sys

from ga4_data import run_report

# Preset for Google's recommended e-commerce events. Other taxonomies are
# supported by passing a custom required-params dict to event_params_coverage().
REQUIRED_PARAMS = {
    "view_item": ["currency", "value", "items"],
    "add_to_cart": ["currency", "value", "items"],
    "begin_checkout": ["currency", "value", "items"],
    "add_payment_info": ["currency", "value", "items"],
    "purchase": ["currency", "value", "items", "transaction_id"],
}


def list_events(property_id, days=7):
    """Distinct event names with counts."""
    return run_report(
        property_id=property_id, metrics=["eventCount"], dimensions=["eventName"], days=days
    )


def check_events(property_id, event_names, days=7):
    """Check which listed events fired in the window."""
    in_list = ",".join(event_names)
    report = run_report(
        property_id=property_id,
        metrics=["eventCount"],
        dimensions=["eventName"],
        filter_expr=f"eventName IN ({in_list})",
        days=days,
    )
    fired = {row["eventName"]: int(float(row["eventCount"])) for row in report["rows"]}
    result = {}
    for name in event_names:
        count = fired.get(name, 0)
        result[name] = {"present": count > 0, "event_count": count}
    return {"events": result, "window_days": days}


def event_params_coverage(property_id, event_name, days=7):
    """Per-parameter coverage for a single event."""
    required = REQUIRED_PARAMS.get(event_name, [])
    total_report = run_report(
        property_id=property_id,
        metrics=["eventCount"],
        dimensions=["eventName"],
        filter_expr=f"eventName = '{event_name}'",
        days=days,
    )
    total = sum(int(float(row["eventCount"])) for row in total_report["rows"])
    coverage = {}
    for param in required:
        coverage[param] = _param_coverage(property_id, event_name, param, total, days)
    return {
        "event": event_name,
        "total_count": total,
        "window_days": days,
        "required_params": required,
        "coverage": coverage,
    }


def _param_coverage(property_id, event_name, param, total, days):
    """Approximate coverage of a single param. Exact coverage requires BQ export."""
    dim_map = {
        "currency": "currencyCode",
        "transaction_id": "transactionId",
        "payment_type": "paymentType",
    }
    metric_map = {
        "value": "totalRevenue",
        "items": "itemsPurchased" if event_name == "purchase" else "itemRevenue",
    }

    if param in dim_map:
        report = run_report(
            property_id=property_id,
            metrics=["eventCount"],
            dimensions=[dim_map[param]],
            filter_expr=f"eventName = '{event_name}'",
            days=days,
        )
        with_value = 0
        missing = 0
        for row in report["rows"]:
            val = row.get(dim_map[param], "")
            count = int(float(row.get("eventCount", 0)))
            if val and val != "(not set)":
                with_value += count
            else:
                missing += count
        return {
            "present_count": with_value,
            "missing_count": missing,
            "coverage_pct": round((with_value / total) * 100, 2) if total else 0,
        }
    if param in metric_map:
        report = run_report(
            property_id=property_id,
            metrics=[metric_map[param], "eventCount"],
            dimensions=["eventName"],
            filter_expr=f"eventName = '{event_name}'",
            days=days,
        )
        aggregate = sum(float(row.get(metric_map[param], 0)) for row in report["rows"])
        return {
            "aggregate": aggregate,
            "coverage_pct": 100.0 if aggregate > 0 else 0.0,
            "note": "approximated via aggregate metric > 0; exact per-event coverage requires BQ export",
        }
    return {"coverage_pct": None, "note": f"param {param} not mapped to a Data API field"}


def detect_postpayment_api(property_id, days=7):
    """Post-payment heuristic for the `add_payment_info` event.

    If `add_payment_info` count is within 10% of `purchase` count, the event
    is firing AFTER the payment-gateway redirect-back (a common tagging error
    on flows where the gateway redirects the user out of the page and back).
    This makes funnel step 4 misleading because it only counts users who
    already paid."""
    report = run_report(
        property_id=property_id,
        metrics=["eventCount"],
        dimensions=["eventName"],
        filter_expr="eventName IN (add_payment_info,purchase)",
        days=days,
    )
    counts = {row["eventName"]: int(float(row["eventCount"])) for row in report["rows"]}
    api_count = counts.get("add_payment_info", 0)
    purchase_count = counts.get("purchase", 0)

    if purchase_count == 0:
        return {
            "verdict": "indeterminate",
            "reason": "no purchase events in window",
            "add_payment_info_count": api_count,
            "purchase_count": purchase_count,
        }

    ratio = api_count / purchase_count
    # Tiny epsilon to handle float-precision at the boundary (e.g., 110/100 -> 1.1000000000000001)
    within_10pct = abs(ratio - 1.0) <= 0.10 + 1e-9

    if api_count == 0:
        verdict = "missing"
        explanation = "add_payment_info event not implemented or not firing"
    elif within_10pct:
        verdict = "post_payment"
        explanation = (
            "add_payment_info count is within 10% of purchase count - event fires AFTER "
            "payment (typical when a payment gateway redirects the user out of the page "
            "and back). Recommend dropping from funnel until tagging is fixed."
        )
    elif ratio < 1.0:
        verdict = "ok_below_purchase"
        explanation = (
            "add_payment_info count below purchase count - unusual but tracking may be functional"
        )
    else:
        verdict = "ok"
        explanation = "add_payment_info count exceeds purchase count - normal funnel behavior"

    return {
        "verdict": verdict,
        "explanation": explanation,
        "add_payment_info_count": api_count,
        "purchase_count": purchase_count,
        "ratio": round(ratio, 3),
        "window_days": days,
    }


def main():
    parser = argparse.ArgumentParser(description="GA4 e-commerce event validator")
    parser.add_argument("--property", required=True)
    parser.add_argument("--list-events", action="store_true")
    parser.add_argument("--check-events", help="Comma-separated event names")
    parser.add_argument("--event-params", help="Event name to inspect parameter coverage")
    parser.add_argument("--detect-postpayment-api", action="store_true")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.list_events:
            print(json.dumps(list_events(args.property, args.days), indent=2, default=str))
        elif args.check_events:
            names = [n.strip() for n in args.check_events.split(",") if n.strip()]
            print(json.dumps(check_events(args.property, names, args.days), indent=2, default=str))
        elif args.event_params:
            print(
                json.dumps(
                    event_params_coverage(args.property, args.event_params, args.days),
                    indent=2,
                    default=str,
                )
            )
        elif args.detect_postpayment_api:
            print(
                json.dumps(detect_postpayment_api(args.property, args.days), indent=2, default=str)
            )
        else:
            parser.print_help()
            return 1
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
