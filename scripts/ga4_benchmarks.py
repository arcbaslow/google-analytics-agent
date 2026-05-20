"""
Industry benchmark engine.

Loads a static benchmark table keyed by (vertical, metric) and produces a
verdict for any observed value. Used by the analysis agents and the
markdown reporter so findings can carry a calibrated comparison rather
than free-floating "this looks bad" claims.

The shipped numbers are conservative directional estimates compiled from
public industry reports (Contentsquare digital experience benchmarks,
WordStream PPC benchmarks, Unbounce conversion benchmark reports,
Statista) as of late 2025. Treat them as order-of-magnitude markers; the
underlying methodology differs across sources, and your own analytics
property is the better long-term reference once enough history exists.

CLI:
  python scripts/ga4_benchmarks.py --list-verticals
  python scripts/ga4_benchmarks.py --vertical ecommerce
  python scripts/ga4_benchmarks.py --compare bounce_rate 0.72 --vertical ecommerce
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# direction: how to interpret values
#   "lower_better"  — higher = worse (bounce_rate, direct_share, cart_abandon)
#   "higher_better" — higher = better (engagement_rate, conversion_rate, pages_per_session)
#   "neutral"       — value is contextual (mobile_share, lang_count)
_DIRECTION = {
    "bounce_rate": "lower_better",
    "engagement_rate": "higher_better",
    "pages_per_session": "higher_better",
    "avg_engagement_time_seconds": "higher_better",
    "conversion_rate": "higher_better",
    "cart_abandonment_rate": "lower_better",
    "direct_share": "lower_better",
    "mobile_share": "neutral",
    "sampling_pct": "lower_better",
    "not_set_share": "lower_better",
}

# Values are stored as floats. Rates are 0-1 (not percentages) so callers
# work in consistent units. Time is in seconds. Counts are integers.
_BENCHMARKS: dict[str, dict[str, dict[str, float]]] = {
    "ecommerce": {
        "bounce_rate":               {"p25": 0.35, "p50": 0.45, "p75": 0.58},
        "engagement_rate":           {"p25": 0.42, "p50": 0.55, "p75": 0.65},
        "pages_per_session":         {"p25": 2.6,  "p50": 3.8,  "p75": 5.5},
        "avg_engagement_time_seconds": {"p25": 80, "p50": 130, "p75": 210},
        "conversion_rate":           {"p25": 0.012, "p50": 0.023, "p75": 0.042},
        "cart_abandonment_rate":     {"p25": 0.60,  "p50": 0.70,  "p75": 0.78},
        "direct_share":              {"p25": 0.10,  "p50": 0.20,  "p75": 0.32},
        "mobile_share":              {"p25": 0.55,  "p50": 0.68,  "p75": 0.80},
        "sampling_pct":              {"p25": 0,     "p50": 0.01,  "p75": 0.05},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "saas": {
        "bounce_rate":               {"p25": 0.32, "p50": 0.42, "p75": 0.55},
        "engagement_rate":           {"p25": 0.48, "p50": 0.60, "p75": 0.72},
        "pages_per_session":         {"p25": 2.2,  "p50": 3.3,  "p75": 4.8},
        "avg_engagement_time_seconds": {"p25": 95, "p50": 160, "p75": 250},
        "conversion_rate":           {"p25": 0.008, "p50": 0.018, "p75": 0.035},
        "direct_share":              {"p25": 0.15,  "p50": 0.25,  "p75": 0.38},
        "mobile_share":              {"p25": 0.25,  "p50": 0.40,  "p75": 0.55},
        "sampling_pct":              {"p25": 0,     "p50": 0.01,  "p75": 0.05},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "media": {
        "bounce_rate":               {"p25": 0.45, "p50": 0.58, "p75": 0.72},
        "engagement_rate":           {"p25": 0.30, "p50": 0.42, "p75": 0.55},
        "pages_per_session":         {"p25": 1.6,  "p50": 2.2,  "p75": 3.5},
        "avg_engagement_time_seconds": {"p25": 45, "p50": 80,  "p75": 140},
        "conversion_rate":           {"p25": 0.001, "p50": 0.004, "p75": 0.012},
        "direct_share":              {"p25": 0.08,  "p50": 0.15,  "p75": 0.26},
        "mobile_share":              {"p25": 0.55,  "p50": 0.70,  "p75": 0.82},
        "sampling_pct":              {"p25": 0,     "p50": 0.02,  "p75": 0.10},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "lead_gen": {
        "bounce_rate":               {"p25": 0.40, "p50": 0.52, "p75": 0.65},
        "engagement_rate":           {"p25": 0.35, "p50": 0.48, "p75": 0.62},
        "pages_per_session":         {"p25": 2.0,  "p50": 3.0,  "p75": 4.5},
        "avg_engagement_time_seconds": {"p25": 60, "p50": 110, "p75": 180},
        "conversion_rate":           {"p25": 0.018, "p50": 0.035, "p75": 0.065},
        "direct_share":              {"p25": 0.12,  "p50": 0.22,  "p75": 0.36},
        "mobile_share":              {"p25": 0.40,  "p50": 0.55,  "p75": 0.70},
        "sampling_pct":              {"p25": 0,     "p50": 0.01,  "p75": 0.05},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "finance": {
        "bounce_rate":               {"p25": 0.40, "p50": 0.51, "p75": 0.62},
        "engagement_rate":           {"p25": 0.40, "p50": 0.52, "p75": 0.65},
        "pages_per_session":         {"p25": 2.4,  "p50": 3.5,  "p75": 5.0},
        "avg_engagement_time_seconds": {"p25": 90, "p50": 150, "p75": 230},
        "conversion_rate":           {"p25": 0.015, "p50": 0.030, "p75": 0.055},
        "direct_share":              {"p25": 0.20,  "p50": 0.32,  "p75": 0.48},
        "mobile_share":              {"p25": 0.45,  "p50": 0.60,  "p75": 0.72},
        "sampling_pct":              {"p25": 0,     "p50": 0.01,  "p75": 0.05},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "travel": {
        "bounce_rate":               {"p25": 0.38, "p50": 0.50, "p75": 0.62},
        "engagement_rate":           {"p25": 0.40, "p50": 0.52, "p75": 0.65},
        "pages_per_session":         {"p25": 2.5,  "p50": 4.0,  "p75": 6.0},
        "avg_engagement_time_seconds": {"p25": 100, "p50": 170, "p75": 260},
        "conversion_rate":           {"p25": 0.010, "p50": 0.025, "p75": 0.048},
        "cart_abandonment_rate":     {"p25": 0.72,  "p50": 0.81,  "p75": 0.88},
        "direct_share":              {"p25": 0.15,  "p50": 0.25,  "p75": 0.38},
        "mobile_share":              {"p25": 0.55,  "p50": 0.68,  "p75": 0.80},
        "sampling_pct":              {"p25": 0,     "p50": 0.02,  "p75": 0.08},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "education": {
        "bounce_rate":               {"p25": 0.42, "p50": 0.54, "p75": 0.65},
        "engagement_rate":           {"p25": 0.35, "p50": 0.46, "p75": 0.58},
        "pages_per_session":         {"p25": 2.0,  "p50": 3.0,  "p75": 4.5},
        "avg_engagement_time_seconds": {"p25": 70, "p50": 120, "p75": 200},
        "conversion_rate":           {"p25": 0.010, "p50": 0.025, "p75": 0.050},
        "direct_share":              {"p25": 0.18,  "p50": 0.30,  "p75": 0.42},
        "mobile_share":              {"p25": 0.45,  "p50": 0.60,  "p75": 0.74},
        "sampling_pct":              {"p25": 0,     "p50": 0.02,  "p75": 0.08},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    "nonprofit": {
        "bounce_rate":               {"p25": 0.45, "p50": 0.55, "p75": 0.68},
        "engagement_rate":           {"p25": 0.33, "p50": 0.45, "p75": 0.58},
        "pages_per_session":         {"p25": 1.8,  "p50": 2.6,  "p75": 3.8},
        "avg_engagement_time_seconds": {"p25": 55, "p50": 95,  "p75": 160},
        "conversion_rate":           {"p25": 0.008, "p50": 0.020, "p75": 0.040},
        "direct_share":              {"p25": 0.20,  "p50": 0.32,  "p75": 0.45},
        "mobile_share":              {"p25": 0.55,  "p50": 0.68,  "p75": 0.80},
        "sampling_pct":              {"p25": 0,     "p50": 0.02,  "p75": 0.08},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
    # "other" is a fallback that averages across all verticals
    "other": {
        "bounce_rate":               {"p25": 0.40, "p50": 0.51, "p75": 0.63},
        "engagement_rate":           {"p25": 0.38, "p50": 0.50, "p75": 0.62},
        "pages_per_session":         {"p25": 2.1,  "p50": 3.1,  "p75": 4.6},
        "avg_engagement_time_seconds": {"p25": 70, "p50": 125, "p75": 200},
        "conversion_rate":           {"p25": 0.010, "p50": 0.022, "p75": 0.045},
        "direct_share":              {"p25": 0.14,  "p50": 0.25,  "p75": 0.38},
        "mobile_share":              {"p25": 0.45,  "p50": 0.60,  "p75": 0.75},
        "sampling_pct":              {"p25": 0,     "p50": 0.01,  "p75": 0.06},
        "not_set_share":             {"p25": 0,     "p50": 0.02,  "p75": 0.07},
    },
}


VERTICAL_ALIASES = {
    "e-commerce": "ecommerce",
    "ecom": "ecommerce",
    "shop": "ecommerce",
    "store": "ecommerce",
    "software": "saas",
    "b2b_saas": "saas",
    "content": "media",
    "publisher": "media",
    "news": "media",
    "lead-gen": "lead_gen",
    "leadgen": "lead_gen",
    "lead_generation": "lead_gen",
    "services": "lead_gen",
    "b2b": "lead_gen",
    "fintech": "finance",
    "banking": "finance",
    "insurance": "finance",
    "hospitality": "travel",
    "edu": "education",
    "ngo": "nonprofit",
    "nonprofit_organization": "nonprofit",
}


def list_verticals() -> list[str]:
    return sorted(_BENCHMARKS.keys())


def normalize_vertical(name: str | None) -> str:
    if not name:
        return "other"
    n = name.strip().lower().replace(" ", "_")
    return VERTICAL_ALIASES.get(n, n if n in _BENCHMARKS else "other")


def benchmarks_for(vertical: str) -> dict[str, dict[str, float]]:
    return _BENCHMARKS[normalize_vertical(vertical)]


def compare(metric: str, value: float, vertical: str | None = None) -> dict[str, Any]:
    """Compare a single observed value against the benchmark band for the
    chosen vertical. Returns a structured verdict with band + interpretation.

    Rates are expected as 0-1 fractions (not percentages). For convenience
    you can also pass percentages: any value > 1.5 that's a *rate* metric is
    auto-divided by 100. Time is in seconds.

    Returns {} for unknown metric/vertical pairings."""
    v = normalize_vertical(vertical)
    table = _BENCHMARKS.get(v, {})
    bench = table.get(metric)
    if not bench:
        return {"metric": metric, "value": value, "vertical": v, "error": "no_benchmark"}

    direction = _DIRECTION.get(metric, "neutral")

    normalized = value
    # Auto-detect percentage input on rate-typed metrics: rates live in
    # [0,1] but humans often pass "72" meaning 72%. If the metric ends in
    # _rate or _share and value > 1.5, assume percent and divide.
    if direction != "neutral" and metric.endswith(("_rate", "_share")) and value > 1.5:
        normalized = value / 100.0

    band = _classify_band(normalized, bench, direction)

    return {
        "metric": metric,
        "value": value,
        "value_normalized": normalized,
        "vertical": v,
        "direction": direction,
        "p25": bench["p25"],
        "p50": bench["p50"],
        "p75": bench["p75"],
        "band": band["band"],
        "interpretation": band["interpretation"],
        "delta_vs_median_pct": _delta_pct(normalized, bench["p50"]),
    }


def _classify_band(value: float, bench: dict[str, float], direction: str) -> dict[str, str]:
    """Place a value into one of five bands: below_p25 / p25_p50 / p50_p75 /
    above_p75 / median. Translate band to 'interpretation' according to
    direction."""
    if value < bench["p25"]:
        band = "below_p25"
    elif value < bench["p50"]:
        band = "p25_to_p50"
    elif value <= bench["p75"]:
        band = "p50_to_p75"
    else:
        band = "above_p75"

    if direction == "neutral":
        interpretation = "context_only"
    elif direction == "lower_better":
        interpretation = {
            "below_p25": "good",
            "p25_to_p50": "average",
            "p50_to_p75": "poor",
            "above_p75": "critical",
        }[band]
    else:
        interpretation = {
            "below_p25": "critical",
            "p25_to_p50": "poor",
            "p50_to_p75": "average",
            "above_p75": "good",
        }[band]

    return {"band": band, "interpretation": interpretation}


def _delta_pct(value: float, median: float) -> float | None:
    if median == 0:
        return None
    return round(((value - median) / median) * 100, 1)


def enrich_findings(findings: list[dict[str, Any]], vertical: str | None) -> list[dict[str, Any]]:
    """Walk a list of findings and attach a `benchmark` field where each
    finding declares a `metric` and `value` pair to compare against."""
    v = normalize_vertical(vertical)
    out = []
    for f in findings:
        ff = dict(f)
        metric = ff.get("metric")
        value = ff.get("metric_value")
        if metric and value is not None:
            ff["benchmark"] = compare(metric, value, v)
        out.append(ff)
    return out


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description="GA4 benchmark engine")
    parser.add_argument("--list-verticals", action="store_true")
    parser.add_argument("--vertical", help="Vertical name (e.g. ecommerce, saas, media)")
    parser.add_argument("--compare", nargs=2, metavar=("METRIC", "VALUE"),
                        help="Compare a single value against the benchmark")
    parser.add_argument("--all-metrics", action="store_true",
                        help="With --vertical, print every metric's benchmark band")
    args = parser.parse_args()

    if args.list_verticals:
        print(json.dumps(list_verticals(), indent=2))
        return 0
    if args.compare:
        metric, raw = args.compare
        try:
            value = float(raw)
        except ValueError:
            print(json.dumps({"error": f"value not numeric: {raw!r}"}), file=sys.stderr)
            return 1
        print(json.dumps(compare(metric, value, args.vertical), indent=2, default=str))
        return 0
    if args.vertical and args.all_metrics:
        print(json.dumps(benchmarks_for(args.vertical), indent=2, default=str))
        return 0
    if args.vertical:
        print(json.dumps({"vertical": normalize_vertical(args.vertical),
                          "metrics": list(benchmarks_for(args.vertical).keys())},
                         indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
