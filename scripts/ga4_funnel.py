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
from ga4_transport import read_operation
from ga4_utils import scrub_pii, scrub_response

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


@read_operation
def validate_steps(property_id, steps, days=7, drop_missing=False):
    """Keep missing steps unless explicitly asked to change the funnel."""
    check = check_events(property_id, steps, days=days)
    validated = []
    dropped = []
    warnings = []
    for step in steps:
        info = check["events"].get(step, {})
        if info.get("present"):
            validated.append(step)
        else:
            if drop_missing:
                dropped.append(step)
            else:
                validated.append(step)
            action = "dropped" if drop_missing else "retained"
            warnings.append(f"step '{step}' has no events in last {days} days - {action}")
    return {"validated_steps": validated, "dropped_steps": dropped, "warnings": warnings}


@scrub_response
@read_operation
def build_funnel(
    property_id, steps=None, days=28, breakdown=None, check_postpayment=False, drop_missing=False
):
    """Build the requested closed funnel; diagnostics never infer event ordering."""
    if steps is None:
        steps = list(ECOMM_FUNNEL_PRESET)

    if not 2 <= len(steps) <= 10 or len(set(steps)) != len(steps):
        raise ValueError("funnel needs 2 to 10 unique steps")
    warnings = []

    validation = validate_steps(property_id, steps, days=days, drop_missing=drop_missing)
    steps = validation["validated_steps"]
    warnings.extend(validation["warnings"])

    if len(steps) < 2:
        return {
            "error": "fewer than 2 funnel steps with data - cannot build funnel",
            "validation": validation,
        }

    postpayment_verdict = None
    if check_postpayment and "add_payment_info" in steps:
        verdict = detect_postpayment_api(property_id, days=7)
        postpayment_verdict = verdict
        if verdict.get("verdict") == "post_payment":
            warnings.append(
                "Similar event counts do not establish ordering after payment; "
                "inspect tagging or sequential export evidence. Steps are unchanged."
            )

    raw = run_funnel_report(
        property_id=property_id, steps=steps, days=days, breakdown_dimension=breakdown
    )
    rates = _compute_rates(
        raw["rows"], steps, has_breakdown=breakdown is not None, breakdown_dimension=breakdown
    )

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


def _compute_rates(rows, steps, has_breakdown, breakdown_dimension=None):
    """Use API totals, never sum overlapping breakdown populations."""
    names = {s: s for s in steps}
    names.update({f"{i}. {s}": s for i, s in enumerate(steps, 1)})
    counts = {s: 0 for s in steps}
    by_segment = {}
    seen = set()
    totals_seen = set()
    for row in rows:
        step = names.get(row.get("funnelStepName") or row.get("stepName"))
        if step is None:
            return {"aggregate": {"error": "unrecognized funnel step label"}}
        if has_breakdown:
            if not breakdown_dimension or breakdown_dimension not in row:
                return {"aggregate": {"error": "missing explicit breakdown dimension"}}
            segment = str(row[breakdown_dimension])
        else:
            segment = "RESERVED_TOTAL"
        key = (step, segment)
        if key in seen:
            return {"aggregate": {"error": "duplicate funnel row"}}
        seen.add(key)
        users = int(float(row.get("activeUsers", 0) or 0))
        if segment == "RESERVED_TOTAL":
            counts[step] = users
            totals_seen.add(step)
        else:
            by_segment.setdefault(segment, {s: 0 for s in steps})[step] = users
    aggregate = _step_rates_from_counts(counts, steps)
    if has_breakdown and totals_seen != set(steps):
        aggregate = {"error": "missing API total rows; breakdown users cannot be summed"}
    out = {"aggregate": aggregate}
    if has_breakdown:
        out["by_segment"] = {
            seg: _step_rates_from_counts(values, steps) for seg, values in by_segment.items()
        }
    return out


def _step_rates_from_counts(counts, steps):
    """Per-step conversion + drop-off + leakiest step identification."""
    if not steps or counts.get(steps[0], 0) == 0:
        return {"error": "no users at step 1, cannot compute rates", "counts": counts}

    if any(counts[s] < 0 for s in steps) or any(
        counts[b] > counts[a] for a, b in zip(steps, steps[1:])
    ):
        return {"error": "inconsistent closed-funnel counts", "counts": counts}
    top = counts[steps[0]]
    bottom = counts[steps[-1]]
    overall_conv = (bottom / top) if top else 0

    transitions = []
    for prev, curr in zip(steps, steps[1:]):
        prev_users = counts.get(prev, 0)
        curr_users = counts.get(curr, 0)
        dropped = max(prev_users - curr_users, 0)
        conv = (curr_users / prev_users) if prev_users else 0
        transitions.append(
            {
                "from": prev,
                "to": curr,
                "from_users": prev_users,
                "to_users": curr_users,
                "users_dropped": dropped,
                "step_conversion_pct": round(conv * 100, 2),
                "step_dropoff_pct": round((1 - conv) * 100, 2),
            }
        )

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


@read_operation
def main():
    parser = argparse.ArgumentParser(description="GA4 funnel constructor")
    parser.add_argument("--property", required=True)
    parser.add_argument(
        "--steps", help="Comma-separated event names; defaults to the e-commerce preset"
    )
    parser.add_argument("--preset", choices=["ecomm"], help="Built-in funnel preset")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--breakdown", help="Optional breakdown dimension")
    parser.add_argument(
        "--check-postpayment",
        action="store_true",
        help="Inspect similar event counts; does not establish order or remove a step",
    )
    parser.add_argument(
        "--drop-missing",
        action="store_true",
        help="Explicitly remove steps with no observed events",
    )
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
            drop_missing=args.drop_missing,
        )
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": scrub_pii(str(e)), "type": type(e).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
