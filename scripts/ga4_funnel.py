"""
GA4 funnel constructor.

Built on ga4_data.run_funnel_report. Handles step validation, rate computation,
and leakiest-step identification. A post-payment check for events that fire
after a payment-gateway redirect-back is available as an opt-in via the
--check-postpayment flag (off by default).
"""

from __future__ import annotations

import argparse
import json
import sys

from ga4_data import run_funnel_report
from ga4_events import check_events, detect_postpayment_api

# E-commerce purchase funnel preset. Users running non-ecomm funnels pass
# their own --steps list and ignore this constant.
ECOMM_FUNNEL_PRESET = [
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "add_payment_info",
    "purchase",
]

# Retained for backward compatibility with imports / tests.
DEFAULT_FUNNEL_STEPS = ECOMM_FUNNEL_PRESET


def validate_steps(property_id, steps, days=7):
    """Drop steps with no data in the window. Return validated list + warnings."""
    check = check_events(property_id, steps, days=days)
    validated = []
    dropped = []
    warnings = []
    for step in steps:
        info = check["events"].get(step, {})
        if info.get("present"):
            validated.append(step)
        else:
            dropped.append(step)
            warnings.append(f"step '{step}' has no events in last {days} days - dropped from funnel")
    return {"validated_steps": validated, "dropped_steps": dropped, "warnings": warnings}


def build_funnel(property_id, steps=None, days=28, breakdown=None, check_postpayment=False):
    """Build a funnel and compute rates.

    `check_postpayment` (opt-in) runs the post-payment heuristic against the
    `add_payment_info` step and drops it from the funnel if it appears to fire
    after the payment-gateway redirect-back. Useful for e-commerce flows where
    a payment provider strips the user out of the page and back, but not
    relevant to other funnel types — hence it is off by default."""
    if steps is None:
        steps = list(ECOMM_FUNNEL_PRESET)

    warnings = []

    validation = validate_steps(property_id, steps, days=min(days, 28))
    steps = validation["validated_steps"]
    warnings.extend(validation["warnings"])

    if len(steps) < 2:
        return {"error": "fewer than 2 funnel steps with data - cannot build funnel", "validation": validation}

    postpayment_verdict = None
    if check_postpayment and "add_payment_info" in steps:
        verdict = detect_postpayment_api(property_id, days=7)
        postpayment_verdict = verdict
        if verdict.get("verdict") == "post_payment":
            steps = [s for s in steps if s != "add_payment_info"]
            warnings.append(
                "add_payment_info dropped from funnel - count is within 10% of purchase "
                "count, indicating the event fires AFTER payment (typical of payment "
                "gateways that redirect back into the page). Fix tagging order before "
                "reintroducing the step."
            )

    raw = run_funnel_report(property_id=property_id, steps=steps, days=days, breakdown_dimension=breakdown)
    rates = _compute_rates(raw["rows"], steps, has_breakdown=breakdown is not None)

    return {
        "property_id": property_id,
        "window_days": days,
        "steps": steps,
        "step_count": len(steps),
        "breakdown": breakdown,
        "raw_rows": raw["rows"],
        "rates": rates,
        "warnings": warnings,
        "postpayment_check": postpayment_verdict,
    }


def _compute_rates(rows, steps, has_breakdown):
    """Compute step-to-step rates. With breakdown, return aggregate + per-segment."""
    if has_breakdown:
        by_segment = {}
        aggregate = {s: 0 for s in steps}
        for row in rows:
            step = row.get("funnelStepName") or row.get("stepName") or ""
            seg = _get_breakdown_value(row)
            users = int(float(row.get("activeUsers", 0) or 0))
            if step not in aggregate:
                continue
            aggregate[step] += users
            by_segment.setdefault(seg, {s: 0 for s in steps})
            by_segment[seg][step] += users
        return {
            "aggregate": _step_rates_from_counts(aggregate, steps),
            "by_segment": {seg: _step_rates_from_counts(counts, steps) for seg, counts in by_segment.items()},
        }
    else:
        counts = {s: 0 for s in steps}
        for row in rows:
            step = row.get("funnelStepName") or row.get("stepName") or ""
            users = int(float(row.get("activeUsers", 0) or 0))
            if step in counts:
                counts[step] += users
        return {"aggregate": _step_rates_from_counts(counts, steps)}


def _step_rates_from_counts(counts, steps):
    """Per-step conversion + drop-off + leakiest step identification."""
    if not steps or counts.get(steps[0], 0) == 0:
        return {"error": "no users at step 1, cannot compute rates", "counts": counts}

    top = counts[steps[0]]
    bottom = counts[steps[-1]]
    overall_conv = (bottom / top) if top else 0

    transitions = []
    for prev, curr in zip(steps, steps[1:]):
        prev_users = counts.get(prev, 0)
        curr_users = counts.get(curr, 0)
        dropped = max(prev_users - curr_users, 0)
        conv = (curr_users / prev_users) if prev_users else 0
        transitions.append({
            "from": prev,
            "to": curr,
            "from_users": prev_users,
            "to_users": curr_users,
            "users_dropped": dropped,
            "step_conversion_pct": round(conv * 100, 2),
            "step_dropoff_pct": round((1 - conv) * 100, 2),
        })

    total_loss = top - bottom
    for t in transitions:
        t["contribution_to_total_loss_pct"] = (
            round((t["users_dropped"] / total_loss) * 100, 2) if total_loss else 0
        )

    leakiest = max(transitions, key=lambda x: x["users_dropped"]) if transitions else None

    return {
        "step_counts": counts,
        "overall_conversion_pct": round(overall_conv * 100, 2),
        "overall_dropoff_pct": round((1 - overall_conv) * 100, 2),
        "transitions": transitions,
        "leakiest_step": (
            {
                "from": leakiest["from"],
                "to": leakiest["to"],
                "users_dropped": leakiest["users_dropped"],
                "share_of_total_loss_pct": leakiest["contribution_to_total_loss_pct"],
            }
            if leakiest
            else None
        ),
    }


def _get_breakdown_value(row):
    """Extract the breakdown dimension value from a funnel row."""
    for k, v in row.items():
        if k not in ("funnelStepName", "stepName", "activeUsers"):
            return str(v)
    return "(unknown)"


def main():
    parser = argparse.ArgumentParser(description="GA4 funnel constructor")
    parser.add_argument("--property", required=True)
    parser.add_argument("--steps", help="Comma-separated event names; defaults to the e-commerce preset")
    parser.add_argument("--preset", choices=["ecomm"], help="Built-in funnel preset")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--breakdown", help="Optional breakdown dimension")
    parser.add_argument("--check-postpayment", action="store_true",
                        help="Run the post-payment heuristic and drop add_payment_info if it fires after purchase")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.steps:
        steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    elif args.preset == "ecomm":
        steps = list(ECOMM_FUNNEL_PRESET)
    else:
        steps = list(ECOMM_FUNNEL_PRESET)
    try:
        result = build_funnel(
            property_id=args.property,
            steps=steps,
            days=args.days,
            breakdown=args.breakdown,
            check_postpayment=args.check_postpayment,
        )
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
