"""Integration tests for ga4_data.

These replay *recorded* GA4 Data API responses (stored as on-the-wire JSON
under fixtures/data_api/) through the real run_report / run_funnel_report
code paths. The only thing mocked is the gRPC client itself — the request
building, response deserialization, PII scrub, and cache logic all run for
real. This is the "VCR-style" approach adapted to a gRPC API: classic HTTP
cassettes can't intercept gRPC, so we record the response payload and
replay it offline. No live credentials are needed.
"""

from pathlib import Path
from unittest.mock import MagicMock

import ga4_data
import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "data_api"


def _load_report(name):
    from google.analytics.data_v1beta.types import RunReportResponse

    return RunReportResponse.from_json((FIXTURES / name).read_text(encoding="utf-8"))


def _load_funnel(name):
    from google.analytics.data_v1alpha.types import RunFunnelReportResponse

    return RunFunnelReportResponse.from_json((FIXTURES / name).read_text(encoding="utf-8"))


def _fake_client(response):
    client = MagicMock()
    client.run_report.return_value = response
    return client


# ---------- run_report ----------


def test_run_report_deserializes_recorded_source_breakdown(monkeypatch):
    client = _fake_client(_load_report("run_report_sessions_by_source.json"))
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)

    out = ga4_data.run_report(
        property_id="123",
        metrics=["sessions"],
        dimensions=["sessionSource"],
        days=28,
    )

    assert out["dimensions"] == ["sessionSource"]
    assert out["metrics"] == ["sessions"]
    assert out["rows_returned"] == 3
    assert out["rows"][0] == {"sessionSource": "(direct)", "sessions": "4200"}
    assert {r["sessionSource"] for r in out["rows"]} == {"(direct)", "google", "(not set)"}


def test_run_report_surfaces_sampling_metadata(monkeypatch):
    client = _fake_client(_load_report("run_report_sessions_by_date_sampled.json"))
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)

    out = ga4_data.run_report(
        property_id="123",
        metrics=["sessions"],
        dimensions=["date"],
        days=28,
        include_metadata=True,
    )

    meta = out["metadata"]
    # 8.4M of 10M samples read -> 0.84 sample rate -> 16% sampled.
    assert meta["sampling"][0]["sample_rate"] == pytest.approx(0.84)
    assert meta["currency_code"] == "USD"
    assert meta["time_zone"] == "America/Los_Angeles"


def test_run_report_applies_dimension_filter(monkeypatch):
    """A filter_expr exercises parse_filter + _build_filter_expression and is
    passed through to the request without changing the deserialized rows."""
    client = _fake_client(_load_report("run_report_channel_for_purchase.json"))
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)

    out = ga4_data.run_report(
        property_id="123",
        metrics=["eventCount"],
        dimensions=["sessionDefaultChannelGroup"],
        filter_expr="eventName = 'purchase'",
        days=28,
    )

    assert out["rows_returned"] == 3
    # The request the client received carries the dimension_filter we built.
    sent_request = client.run_report.call_args.args[0]
    assert sent_request.dimension_filter is not None


def test_run_report_second_call_is_served_from_cache(monkeypatch):
    client = _fake_client(_load_report("run_report_sessions_by_source.json"))
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)

    first = ga4_data.run_report("123", ["sessions"], ["sessionSource"], days=28)
    second = ga4_data.run_report("123", ["sessions"], ["sessionSource"], days=28)

    assert first == second
    assert client.run_report.call_count == 1


# ---------- run_funnel_report ----------


def test_run_funnel_report_deserializes_recorded_table(monkeypatch):
    client = MagicMock()
    client.run_funnel_report.return_value = _load_funnel("run_funnel_report.json")
    monkeypatch.setattr(ga4_data, "_get_data_alpha_client", lambda: client)

    steps = ["view_item", "add_to_cart", "begin_checkout", "purchase"]
    out = ga4_data.run_funnel_report("123", steps=steps, days=28)

    assert out["steps"] == steps
    assert out["step_count"] == 4
    rows = {r["funnelStepName"]: r["activeUsers"] for r in out["rows"]}
    assert rows == {
        "view_item": "10000",
        "add_to_cart": "3000",
        "begin_checkout": "1500",
        "purchase": "600",
    }


def test_run_funnel_report_feeds_real_rate_computation(monkeypatch):
    """End-to-end: recorded funnel response -> ga4_data -> ga4_funnel rate math."""
    import ga4_funnel

    client = MagicMock()
    client.run_funnel_report.return_value = _load_funnel("run_funnel_report.json")
    monkeypatch.setattr(ga4_data, "_get_data_alpha_client", lambda: client)
    # build_funnel validates steps first; treat all recorded steps as present.
    monkeypatch.setattr(
        ga4_funnel,
        "check_events",
        lambda pid, steps, days: {
            "events": {s: {"present": True, "event_count": 1} for s in steps},
            "window_days": days,
        },
    )

    steps = ["view_item", "add_to_cart", "begin_checkout", "purchase"]
    result = ga4_funnel.build_funnel("123", steps=steps, days=28)
    agg = result["rates"]["aggregate"]
    # 600 / 10000 = 6%.
    assert agg["overall_conversion_pct"] == 6.0
    # Largest absolute drop is view_item -> add_to_cart (7000 users).
    assert agg["leakiest_step"]["from"] == "view_item"
    assert agg["leakiest_step"]["to"] == "add_to_cart"
    assert agg["leakiest_step"]["users_dropped"] == 7000
