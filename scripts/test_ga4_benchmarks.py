"""Tests for ga4_benchmarks: vertical normalization, compare(), and finding enrichment."""

import pytest

import ga4_benchmarks


# ---------- Vertical normalization ----------


def test_list_verticals_includes_other():
    verticals = ga4_benchmarks.list_verticals()
    assert "other" in verticals
    assert "ecommerce" in verticals
    assert "saas" in verticals


def test_normalize_handles_aliases():
    assert ga4_benchmarks.normalize_vertical("e-commerce") == "ecommerce"
    assert ga4_benchmarks.normalize_vertical("Lead-gen") == "lead_gen"
    assert ga4_benchmarks.normalize_vertical("Software") == "saas"
    assert ga4_benchmarks.normalize_vertical("news") == "media"


def test_normalize_unknown_falls_back_to_other():
    assert ga4_benchmarks.normalize_vertical("crypto") == "other"
    assert ga4_benchmarks.normalize_vertical(None) == "other"


def test_benchmarks_for_returns_table():
    out = ga4_benchmarks.benchmarks_for("ecommerce")
    assert "bounce_rate" in out
    assert "p50" in out["bounce_rate"]


# ---------- compare() — happy paths ----------


def test_compare_bounce_rate_above_p75_is_critical_for_ecomm():
    result = ga4_benchmarks.compare("bounce_rate", 0.80, "ecommerce")
    assert result["band"] == "above_p75"
    assert result["interpretation"] == "critical"
    assert result["direction"] == "lower_better"


def test_compare_bounce_rate_below_p25_is_good_for_ecomm():
    result = ga4_benchmarks.compare("bounce_rate", 0.20, "ecommerce")
    assert result["band"] == "below_p25"
    assert result["interpretation"] == "good"


def test_compare_engagement_rate_higher_better():
    result = ga4_benchmarks.compare("engagement_rate", 0.75, "saas")
    # 0.75 > p75 0.72 → above_p75 → good for higher_better
    assert result["band"] == "above_p75"
    assert result["interpretation"] == "good"


def test_compare_engagement_rate_below_p25_is_critical_for_higher_better():
    result = ga4_benchmarks.compare("engagement_rate", 0.10, "saas")
    assert result["interpretation"] == "critical"


def test_compare_conversion_rate_with_percent_input_normalizes():
    """A user passing 2.3 (meaning 2.3%) should be normalized to 0.023."""
    result = ga4_benchmarks.compare("conversion_rate", 2.3, "ecommerce")
    assert result["value_normalized"] == pytest.approx(0.023, abs=1e-6)


def test_compare_neutral_metric_returns_context_only():
    result = ga4_benchmarks.compare("mobile_share", 0.65, "ecommerce")
    assert result["direction"] == "neutral"
    assert result["interpretation"] == "context_only"


def test_compare_unknown_metric_returns_error_envelope():
    result = ga4_benchmarks.compare("not_a_metric", 0.5, "ecommerce")
    assert result.get("error") == "no_benchmark"


def test_compare_vertical_fallback_to_other():
    result = ga4_benchmarks.compare("bounce_rate", 0.50, "crypto")
    # crypto -> other; "other" has bounce_rate band so a verdict is produced
    assert "band" in result
    assert result["vertical"] == "other"


def test_compare_delta_vs_median_pct():
    result = ga4_benchmarks.compare("bounce_rate", 0.45, "ecommerce")
    # p50 is 0.45 → delta == 0
    assert result["delta_vs_median_pct"] == 0.0


# ---------- enrich_findings ----------


def test_enrich_findings_attaches_benchmark_to_matching_finding():
    findings = [
        {"severity": "High", "title": "Bounce high", "metric": "bounce_rate", "metric_value": 0.78},
        {"severity": "Low", "title": "No metric here"},
    ]
    out = ga4_benchmarks.enrich_findings(findings, "ecommerce")
    assert out[0]["benchmark"]["band"] == "above_p75"
    assert "benchmark" not in out[1]


def test_enrich_findings_preserves_input_objects():
    findings = [
        {"severity": "High", "metric": "bounce_rate", "metric_value": 0.5},
    ]
    out = ga4_benchmarks.enrich_findings(findings, "ecommerce")
    # Original dict not mutated
    assert "benchmark" not in findings[0]
    assert "benchmark" in out[0]
