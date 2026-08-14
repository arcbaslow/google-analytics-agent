"""Tests for ga4_data: filter parsing, date range, report serialization."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import ga4_data
import pytest

# ---------- Filter parser ----------


def test_parse_filter_equality():
    out = ga4_data.parse_filter("eventName = 'purchase'")
    assert out == {"field": "eventName", "op": "EXACT", "value": "purchase"}


def test_parse_filter_inequality():
    out = ga4_data.parse_filter("eventName != 'purchase'")
    assert out == {"field": "eventName", "op": "EXACT", "value": "purchase", "not": True}


def test_parse_filter_in_list_parens():
    out = ga4_data.parse_filter("eventName IN (view_item,add_to_cart,purchase)")
    assert out == {
        "field": "eventName",
        "op": "IN_LIST",
        "values": ["view_item", "add_to_cart", "purchase"],
    }


def test_parse_filter_in_list_no_parens():
    out = ga4_data.parse_filter("eventName IN view_item,purchase")
    assert out["values"] == ["view_item", "purchase"]


def test_parse_filter_contains():
    out = ga4_data.parse_filter("pagePath CONTAINS '/product/'")
    assert out == {"field": "pagePath", "op": "CONTAINS", "value": "/product/"}


def test_parse_filter_begins_with():
    out = ga4_data.parse_filter("sessionSource BEGINS_WITH 'google'")
    assert out == {"field": "sessionSource", "op": "BEGINS_WITH", "value": "google"}


def test_parse_filter_empty():
    assert ga4_data.parse_filter("") is None


def test_parse_filter_invalid_raises():
    with pytest.raises(ValueError):
        ga4_data.parse_filter("not a filter")


def test_parse_filter_case_insensitive_op():
    out = ga4_data.parse_filter("eventName in (a,b)")
    assert out["op"] == "IN_LIST"


# ---------- Date range ----------


def test_date_range_28_days():
    start, end = ga4_data.date_range(28)
    yesterday = date.today() - timedelta(days=1)
    assert end == yesterday.isoformat()
    expected_start = yesterday - timedelta(days=27)
    assert start == expected_start.isoformat()


def test_date_range_1_day():
    start, end = ga4_data.date_range(1)
    assert start == end


# ---------- Report serialization ----------


def _mock_run_report_response():
    response = MagicMock()
    response.row_count = 2
    response.dimension_headers = [MagicMock(name="h", spec=["name"]) for _ in range(1)]
    response.dimension_headers[0].name = "eventName"
    response.metric_headers = [MagicMock(spec=["name"])]
    response.metric_headers[0].name = "eventCount"

    row1 = MagicMock()
    row1.dimension_values = [MagicMock(value="purchase")]
    row1.metric_values = [MagicMock(value="100")]
    row2 = MagicMock()
    row2.dimension_values = [MagicMock(value="view_item")]
    row2.metric_values = [MagicMock(value="5000")]
    response.rows = [row1, row2]
    response.metadata.sampling_metadatas = []
    response.metadata.data_loss_from_other_row = False
    response.metadata.currency_code = "USD"
    response.metadata.time_zone = "America/Los_Angeles"
    response.property_quota = None
    return response


def test_serialize_run_report_basic():
    resp = _mock_run_report_response()
    out = ga4_data._serialize_run_report(resp, include_metadata=False)
    assert out["row_count"] == 2
    assert out["rows_returned"] == 2
    assert out["dimensions"] == ["eventName"]
    assert out["metrics"] == ["eventCount"]
    assert out["rows"][0] == {"eventName": "purchase", "eventCount": "100"}


def test_serialize_run_report_with_metadata():
    resp = _mock_run_report_response()
    sm = MagicMock()
    sm.samples_read_count = 5000000
    sm.sampling_space_size = 10000000
    resp.metadata.sampling_metadatas = [sm]
    out = ga4_data._serialize_run_report(resp, include_metadata=True)
    assert "metadata" in out
    assert out["metadata"]["sampling"][0]["sample_rate"] == 0.5
    assert out["metadata"]["currency_code"] == "USD"


def test_run_report_uses_cache(fake_creds, monkeypatch):
    """Second call with same args should hit cache, not the API."""
    mock_client = MagicMock()
    mock_client.run_report.return_value = _mock_run_report_response()
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: mock_client)

    # Mock the SDK type imports inside run_report
    with patch.dict(
        "sys.modules",
        {
            "google.analytics.data_v1beta": MagicMock(),
            "google.analytics.data_v1beta.types": MagicMock(),
        },
    ):
        out1 = ga4_data.run_report("123", ["eventCount"], ["eventName"], days=7)
        out2 = ga4_data.run_report("123", ["eventCount"], ["eventName"], days=7)

    assert out1 == out2
    # Client should only be called once - second call hits cache
    assert mock_client.run_report.call_count == 1


# ---------- Dimension filter builder ----------


def test_build_dimension_filter_shorthand():
    from google.analytics.data_v1beta.types import FilterExpression

    fe = ga4_data.build_dimension_filter({"field": "eventName", "op": "EXACT", "value": "purchase"})
    assert isinstance(fe, FilterExpression)
    assert fe.filter.field_name == "eventName"
    assert fe.filter.string_filter.value == "purchase"


def test_build_dimension_filter_raw_proto_plus():
    from google.analytics.data_v1beta.types import FilterExpression

    fe = ga4_data.build_dimension_filter(
        {
            "filter": {
                "field_name": "country",
                "string_filter": {"match_type": "EXACT", "value": "US"},
            }
        }
    )
    assert isinstance(fe, FilterExpression)
    assert fe.filter.field_name == "country"


# ---------- run_report filter_dict ----------


def _fake_data_client():
    client = MagicMock()
    resp = MagicMock()
    resp.dimension_headers = []
    resp.metric_headers = []
    resp.rows = []
    resp.row_count = 0
    client.run_report.return_value = resp
    return client


def test_run_report_filter_dict_builds_dimension_filter(monkeypatch):
    client = _fake_data_client()
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)

    ga4_data.run_report(
        "123",
        ["sessions"],
        ["deviceCategory"],
        filter_dict={"field": "eventName", "op": "EXACT", "value": "purchase"},
        days=28,
        use_cache=False,
    )
    sent = client.run_report.call_args.args[0]
    assert sent.dimension_filter is not None


def test_run_report_filter_dict_has_distinct_cache_key(monkeypatch):
    client = _fake_data_client()
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)

    ga4_data.run_report("123", ["sessions"], ["deviceCategory"], days=28)
    ga4_data.run_report(
        "123",
        ["sessions"],
        ["deviceCategory"],
        filter_dict={"field": "eventName", "op": "EXACT", "value": "purchase"},
        days=28,
    )
    assert client.run_report.call_count == 2
