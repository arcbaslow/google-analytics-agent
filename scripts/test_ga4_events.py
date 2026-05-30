"""Tests for ga4_events: list/check, post-payment detector."""

import ga4_events


def test_check_events_all_present(monkeypatch):
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "view_item", "eventCount": "1000"},
                {"eventName": "add_to_cart", "eventCount": "300"},
                {"eventName": "purchase", "eventCount": "60"},
            ],
        },
    )
    out = ga4_events.check_events("123", ["view_item", "add_to_cart", "purchase"])
    assert out["events"]["view_item"]["present"] is True
    assert out["events"]["view_item"]["event_count"] == 1000
    assert out["events"]["purchase"]["event_count"] == 60


def test_check_events_one_missing(monkeypatch):
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "view_item", "eventCount": "1000"},
            ],
        },
    )
    out = ga4_events.check_events("123", ["view_item", "add_to_cart", "purchase"])
    assert out["events"]["view_item"]["present"] is True
    assert out["events"]["add_to_cart"]["present"] is False
    assert out["events"]["add_to_cart"]["event_count"] == 0


def test_detect_postpayment_api_post_payment(monkeypatch):
    """add_payment_info count ~ purchase count = post-payment firing."""
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "add_payment_info", "eventCount": "105"},
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    out = ga4_events.detect_postpayment_api("123")
    assert out["verdict"] == "post_payment"
    assert out["ratio"] == 1.05


def test_detect_postpayment_api_normal(monkeypatch):
    """add_payment_info count much higher than purchase = normal funnel."""
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "add_payment_info", "eventCount": "300"},
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    out = ga4_events.detect_postpayment_api("123")
    assert out["verdict"] == "ok"
    assert out["ratio"] == 3.0


def test_detect_postpayment_api_below(monkeypatch):
    """add_payment_info below purchase = unusual but functional."""
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "add_payment_info", "eventCount": "50"},
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    out = ga4_events.detect_postpayment_api("123")
    assert out["verdict"] == "ok_below_purchase"


def test_detect_postpayment_api_missing(monkeypatch):
    """No add_payment_info events at all."""
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    out = ga4_events.detect_postpayment_api("123")
    assert out["verdict"] == "missing"


def test_detect_postpayment_api_no_purchases(monkeypatch):
    """No purchases in window = can't determine."""
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "add_payment_info", "eventCount": "10"},
            ],
        },
    )
    out = ga4_events.detect_postpayment_api("123")
    assert out["verdict"] == "indeterminate"


def test_postpayment_boundary_exactly_10pct(monkeypatch):
    """Exactly 10% difference should still flag as post_payment."""
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {
            "rows": [
                {"eventName": "add_payment_info", "eventCount": "110"},
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    out = ga4_events.detect_postpayment_api("123")
    assert out["verdict"] == "post_payment"


def test_required_params_match_spec():
    """Make sure REQUIRED_PARAMS has the right shape for each funnel event."""
    assert "transaction_id" in ga4_events.REQUIRED_PARAMS["purchase"]
    assert "items" in ga4_events.REQUIRED_PARAMS["view_item"]
    assert "currency" in ga4_events.REQUIRED_PARAMS["add_to_cart"]


# ---------- list_events ----------


def test_list_events_requests_event_name_dimension(monkeypatch):
    seen = {}
    monkeypatch.setattr(ga4_events, "run_report", lambda **kw: seen.update(kw) or {"rows": []})
    ga4_events.list_events("123", days=30)
    assert seen["dimensions"] == ["eventName"]
    assert seen["metrics"] == ["eventCount"]
    assert seen["days"] == 30


# ---------- event_params_coverage / _param_coverage ----------


def _purchase_coverage_dispatch(**kw):
    """Stand in for run_report across the several queries event_params_coverage
    issues for a single event. Routes on the requested dimension/metric."""
    dims = kw.get("dimensions") or []
    metrics = kw.get("metrics") or []
    d0 = dims[0] if dims else ""
    m0 = metrics[0] if metrics else ""
    if d0 == "currencyCode":
        return {
            "rows": [
                {"currencyCode": "USD", "eventCount": "950"},
                {"currencyCode": "(not set)", "eventCount": "50"},
            ]
        }
    if d0 == "transactionId":
        return {"rows": [{"transactionId": "t-1", "eventCount": "1000"}]}
    if m0 == "totalRevenue":
        return {
            "rows": [{"eventName": "purchase", "totalRevenue": "54321.0", "eventCount": "1000"}]
        }
    if m0 == "itemsPurchased":
        return {"rows": [{"eventName": "purchase", "itemsPurchased": "0", "eventCount": "1000"}]}
    # default: the total-count report (eventName / eventCount)
    return {"rows": [{"eventName": "purchase", "eventCount": "1000"}]}


def test_event_params_coverage_purchase_mixes_dim_and_metric_params(monkeypatch):
    monkeypatch.setattr(ga4_events, "run_report", _purchase_coverage_dispatch)

    out = ga4_events.event_params_coverage("123", "purchase", days=7)

    assert out["total_count"] == 1000
    assert out["required_params"] == ["currency", "value", "items", "transaction_id"]
    cov = out["coverage"]

    # dimension-backed param: 950 of 1000 carry a currency -> 95%
    assert cov["currency"]["present_count"] == 950
    assert cov["currency"]["missing_count"] == 50
    assert cov["currency"]["coverage_pct"] == 95.0
    assert cov["transaction_id"]["coverage_pct"] == 100.0

    # metric-backed param: aggregate > 0 reads as full coverage; 0 reads as none
    assert cov["value"]["coverage_pct"] == 100.0
    assert cov["value"]["aggregate"] == 54321.0
    assert cov["items"]["coverage_pct"] == 0.0


def test_event_params_coverage_non_purchase_uses_item_revenue_metric(monkeypatch):
    calls = []

    def dispatch(**kw):
        calls.append(kw.get("metrics") or [])
        metrics = kw.get("metrics") or []
        dims = kw.get("dimensions") or []
        if (dims[0] if dims else "") == "currencyCode":
            return {"rows": [{"currencyCode": "USD", "eventCount": "300"}]}
        if metrics and metrics[0] == "itemRevenue":
            return {
                "rows": [{"eventName": "add_to_cart", "itemRevenue": "120.0", "eventCount": "300"}]
            }
        if metrics and metrics[0] == "totalRevenue":
            return {
                "rows": [{"eventName": "add_to_cart", "totalRevenue": "0", "eventCount": "300"}]
            }
        return {"rows": [{"eventName": "add_to_cart", "eventCount": "300"}]}

    monkeypatch.setattr(ga4_events, "run_report", dispatch)

    out = ga4_events.event_params_coverage("123", "add_to_cart", days=7)

    # non-purchase events map "items" to the itemRevenue metric, not itemsPurchased
    assert any(m and m[0] == "itemRevenue" for m in calls)
    assert out["coverage"]["items"]["coverage_pct"] == 100.0
    # totalRevenue aggregated to 0 -> "value" reads as no coverage
    assert out["coverage"]["value"]["coverage_pct"] == 0.0


def test_param_coverage_dimension_with_zero_total_is_zero(monkeypatch):
    monkeypatch.setattr(
        ga4_events,
        "run_report",
        lambda **kw: {"rows": [{"currencyCode": "USD", "eventCount": "0"}]},
    )
    out = ga4_events._param_coverage("123", "purchase", "currency", total=0, days=7)
    assert out["coverage_pct"] == 0


def test_param_coverage_unmapped_param_returns_none():
    out = ga4_events._param_coverage("123", "purchase", "coupon_code", total=100, days=7)
    assert out["coverage_pct"] is None
    assert "not mapped" in out["note"]
