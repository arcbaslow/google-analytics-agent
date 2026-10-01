"""Tests for ga4_funnel: rate computation, leakiest step, opt-in post-payment check."""

import ga4_funnel
import pytest


def test_step_rates_basic():
    counts = {
        "view_item": 10000,
        "add_to_cart": 3000,
        "begin_checkout": 1500,
        "add_payment_info": 900,
        "purchase": 600,
    }
    steps = list(counts.keys())
    out = ga4_funnel._step_rates_from_counts(counts, steps)
    assert out["overall_conversion_pct"] == 6.0
    assert out["overall_dropoff_pct"] == 94.0
    # First transition: 10000 -> 3000, conv 30%, dropped 7000
    t0 = out["transitions"][0]
    assert t0["from"] == "view_item"
    assert t0["to"] == "add_to_cart"
    assert t0["step_conversion_pct"] == 30.0
    assert t0["step_dropoff_pct"] == 70.0
    assert t0["users_dropped"] == 7000


def test_step_rates_leakiest_is_largest_absolute():
    """Leakiest = largest absolute drop, NOT lowest conversion rate."""
    counts = {
        "view_item": 100000,
        "add_to_cart": 10000,  # 90% drop, 90000 users
        "begin_checkout": 5000,  # 50% drop, 5000 users
        "purchase": 100,  # 98% drop, 4900 users
    }
    steps = list(counts.keys())
    out = ga4_funnel._step_rates_from_counts(counts, steps)
    # view_item -> add_to_cart has lowest conversion AND largest absolute drop
    assert out["leakiest_step"]["from"] == "view_item"
    assert out["leakiest_step"]["to"] == "add_to_cart"
    assert out["leakiest_step"]["users_dropped"] == 90000


def test_step_rates_leakiest_prefers_volume_over_rate():
    """A step with high volume + moderate drop beats a step with low volume + extreme drop."""
    counts = {
        "view_item": 1000000,
        "add_to_cart": 500000,  # 50% drop, 500k users
        "begin_checkout": 5000,  # 99% drop, 495k users
        "purchase": 50,  # 99% drop, 4950 users
    }
    steps = list(counts.keys())
    out = ga4_funnel._step_rates_from_counts(counts, steps)
    # view_item -> add_to_cart drops 500k vs add_to_cart -> begin_checkout drops 495k
    assert out["leakiest_step"]["from"] == "view_item"


def test_step_rates_empty_first_step():
    counts = {"view_item": 0, "purchase": 0}
    out = ga4_funnel._step_rates_from_counts(counts, list(counts.keys()))
    assert "error" in out


def test_step_rates_contribution_to_loss():
    counts = {"a": 1000, "b": 800, "c": 400}
    out = ga4_funnel._step_rates_from_counts(counts, ["a", "b", "c"])
    # Total loss: 600
    # a->b dropped 200, contribution: 200/600 = 33.33%
    # b->c dropped 400, contribution: 400/600 = 66.67%
    assert out["transitions"][0]["contribution_to_total_loss_pct"] == 33.33
    assert out["transitions"][1]["contribution_to_total_loss_pct"] == 66.67


def test_ecomm_funnel_preset_matches_spec():
    assert ga4_funnel.ECOMM_FUNNEL_PRESET == [
        "view_item",
        "add_to_cart",
        "begin_checkout",
        "add_payment_info",
        "purchase",
    ]
    # DEFAULT_FUNNEL_STEPS retained as a back-compat alias.
    assert ga4_funnel.DEFAULT_FUNNEL_STEPS == ga4_funnel.ECOMM_FUNNEL_PRESET


def test_compute_rates_no_breakdown():
    rows = [
        {"funnelStepName": "view_item", "activeUsers": "1000"},
        {"funnelStepName": "add_to_cart", "activeUsers": "300"},
        {"funnelStepName": "purchase", "activeUsers": "60"},
    ]
    out = ga4_funnel._compute_rates(
        rows, ["view_item", "add_to_cart", "purchase"], has_breakdown=False
    )
    assert out["aggregate"]["overall_conversion_pct"] == 6.0


def test_compute_rates_with_breakdown():
    rows = [
        {"funnelStepName": "view_item", "deviceCategory": "mobile", "activeUsers": "800"},
        {"funnelStepName": "view_item", "deviceCategory": "desktop", "activeUsers": "200"},
        {"funnelStepName": "purchase", "deviceCategory": "mobile", "activeUsers": "20"},
        {"funnelStepName": "purchase", "deviceCategory": "desktop", "activeUsers": "40"},
        {"funnelStepName": "view_item", "deviceCategory": "RESERVED_TOTAL", "activeUsers": "1000"},
        {"funnelStepName": "purchase", "deviceCategory": "RESERVED_TOTAL", "activeUsers": "60"},
    ]
    out = ga4_funnel._compute_rates(
        rows, ["view_item", "purchase"], has_breakdown=True, breakdown_dimension="deviceCategory"
    )
    # Aggregate: 1000 -> 60 = 6%
    assert out["aggregate"]["overall_conversion_pct"] == 6.0
    # Mobile: 800 -> 20 = 2.5%
    assert out["by_segment"]["mobile"]["overall_conversion_pct"] == 2.5
    # Desktop: 200 -> 40 = 20%
    assert out["by_segment"]["desktop"]["overall_conversion_pct"] == 20.0


def test_build_funnel_retains_postpayment_step_when_opted_in(monkeypatch):
    """Similar counts cannot establish order or authorize changing a funnel."""
    monkeypatch.setattr(
        ga4_funnel,
        "check_events",
        lambda pid, steps, days: {
            "events": {s: {"present": True, "event_count": 100} for s in steps},
            "window_days": days,
        },
    )
    monkeypatch.setattr(
        ga4_funnel,
        "detect_postpayment_api",
        lambda pid, days: {
            "verdict": "post_payment",
            "explanation": "fires after payment",
            "add_payment_info_count": 105,
            "purchase_count": 100,
            "ratio": 1.05,
        },
    )
    monkeypatch.setattr(
        ga4_funnel,
        "run_funnel_report",
        lambda **kw: {
            "rows": [
                {"funnelStepName": "view_item", "activeUsers": "1000"},
                {"funnelStepName": "add_to_cart", "activeUsers": "300"},
                {"funnelStepName": "begin_checkout", "activeUsers": "150"},
                {"funnelStepName": "purchase", "activeUsers": "60"},
            ],
        },
    )

    out = ga4_funnel.build_funnel("123", days=28, check_postpayment=True)
    assert "add_payment_info" in out["steps"]
    assert any("after payment" in w.lower() for w in out["warnings"])
    assert out["postpayment_check"]["verdict"] == "post_payment"


def test_build_funnel_default_does_not_run_postpayment_check(monkeypatch):
    """Default behaviour: post-payment heuristic does not run, all steps kept."""
    monkeypatch.setattr(
        ga4_funnel,
        "check_events",
        lambda pid, steps, days: {
            "events": {s: {"present": True, "event_count": 100} for s in steps},
            "window_days": days,
        },
    )
    called = {"detect": False}

    def _detect(*_a, **_kw):
        called["detect"] = True
        return {"verdict": "post_payment"}

    monkeypatch.setattr(ga4_funnel, "detect_postpayment_api", _detect)
    monkeypatch.setattr(
        ga4_funnel,
        "run_funnel_report",
        lambda **kw: {
            "rows": [
                {"funnelStepName": s, "activeUsers": "100"}
                for s in [
                    "view_item",
                    "add_to_cart",
                    "begin_checkout",
                    "add_payment_info",
                    "purchase",
                ]
            ],
        },
    )

    out = ga4_funnel.build_funnel("123", days=28)
    assert "add_payment_info" in out["steps"]
    assert called["detect"] is False
    assert out["postpayment_check"] is None


def test_build_funnel_keeps_postpayment_api_when_check_ok(monkeypatch):
    """With check_postpayment=True and an OK verdict, the step is kept."""
    monkeypatch.setattr(
        ga4_funnel,
        "check_events",
        lambda pid, steps, days: {
            "events": {s: {"present": True, "event_count": 100} for s in steps},
            "window_days": days,
        },
    )
    monkeypatch.setattr(
        ga4_funnel,
        "detect_postpayment_api",
        lambda pid, days: {
            "verdict": "ok",
            "add_payment_info_count": 200,
            "purchase_count": 100,
            "ratio": 2.0,
        },
    )
    monkeypatch.setattr(
        ga4_funnel,
        "run_funnel_report",
        lambda **kw: {
            "rows": [
                {"funnelStepName": s, "activeUsers": "100"}
                for s in [
                    "view_item",
                    "add_to_cart",
                    "begin_checkout",
                    "add_payment_info",
                    "purchase",
                ]
            ],
        },
    )

    out = ga4_funnel.build_funnel("123", days=28, check_postpayment=True)
    assert "add_payment_info" in out["steps"]


def test_numbered_proto_steps_and_reserved_totals():
    from ga4_data import _serialize_funnel_report
    from google.analytics.data_v1alpha.types import RunFunnelReportResponse

    response = RunFunnelReportResponse(
        funnel_table={
            "dimension_headers": [{"name": "funnelStepName"}, {"name": "deviceCategory"}],
            "metric_headers": [{"name": "activeUsers"}, {"name": "funnelStepCompletionRate"}],
            "rows": [
                {
                    "dimension_values": [{"value": step}, {"value": segment}],
                    "metric_values": [{"value": count}, {"value": "0.2"}],
                }
                for step, segment, count in [
                    ("1. start", "RESERVED_TOTAL", "100"),
                    ("2. finish", "RESERVED_TOTAL", "20"),
                    ("1. start", "mobile", "80"),
                    ("2. finish", "mobile", "10"),
                ]
            ],
        }
    )
    rows = _serialize_funnel_report(response, ["start", "finish"])["rows"]
    out = ga4_funnel._compute_rates(rows, ["start", "finish"], True, "deviceCategory")
    assert out["aggregate"]["overall_conversion_pct"] == 20
    assert out["by_segment"]["mobile"]["overall_conversion_pct"] == 12.5
    assert "RESERVED_TOTAL" not in out["by_segment"]


@pytest.mark.parametrize(
    "rows,breakdown",
    [
        ([{"funnelStepName": "wrong", "activeUsers": "1"}], None),
        ([{"funnelStepName": "a", "activeUsers": "1"}] * 2, None),
        (
            [{"funnelStepName": "a", "deviceCategory": "mobile", "activeUsers": "1"}],
            "deviceCategory",
        ),
        ([{"funnelStepName": "a", "activeUsers": "1"}], "deviceCategory"),
    ],
)
def test_unrecognized_or_incomplete_contract_does_not_invent_rates(rows, breakdown):
    out = ga4_funnel._compute_rates(rows, ["a", "b"], bool(breakdown), breakdown)
    assert "error" in out["aggregate"]


def test_missing_steps_are_retained_until_explicitly_removed(monkeypatch):
    seen = []

    def check(pid, steps, days):
        seen.append(days)
        return {"events": {"a": {"present": True}, "b": {"present": False}}}

    monkeypatch.setattr(ga4_funnel, "check_events", check)
    assert ga4_funnel.validate_steps("123", ["a", "b"], 90)["validated_steps"] == ["a", "b"]
    assert ga4_funnel.validate_steps("123", ["a", "b"], 90, True)["dropped_steps"] == ["b"]
    assert seen == [90, 90]


def test_invalid_closed_funnel_counts():
    assert "error" in ga4_funnel._step_rates_from_counts({"a": 1, "b": 2}, ["a", "b"])


def test_duplicate_steps_fail_before_reads():
    with pytest.raises(ValueError, match="unique"):
        ga4_funnel.build_funnel("123", ["a", "a"])
