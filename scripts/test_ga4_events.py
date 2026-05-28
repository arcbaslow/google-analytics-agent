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
