import json
from unittest.mock import Mock

import ga4_data
import ga4_explore as explore
import ga4_mcp
import pytest
from google.analytics.data_v1beta import BetaAnalyticsDataClient, types


@pytest.fixture
def client(monkeypatch):
    client = Mock(spec=BetaAnalyticsDataClient)
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    return client


def test_realtime_is_uncached_scrubbed_and_has_no_offset(client):
    client.run_realtime_report.return_value = types.RunRealtimeReportResponse(
        row_count=2,
        dimension_headers=[{"name": "eventName"}],
        metric_headers=[{"name": "eventCount"}],
        rows=[
            dict(dimension_values=[{"value": "person@example.com"}], metric_values=[{"value": "4"}])
        ],
        property_quota={"tokens_per_hour": {"remaining": 90}},
    )
    for _ in range(2):
        out = ga4_mcp.realtime_report(
            "123",
            ["eventCount"],
            ["eventName"],
            filter_dict={"field": "eventName", "op": "EXACT", "value": "purchase"},
        )
    assert client.run_realtime_report.call_count == 2
    req = client.run_realtime_report.call_args.args[0]
    assert isinstance(req, types.RunRealtimeReportRequest) and "offset" not in type(req).meta.fields
    assert req.minute_ranges[0].start_minutes_ago == 29
    assert req.dimension_filter.filter.string_filter.value == "purchase"
    assert not out["complete"] and "person@example.com" not in str(out)
    assert out["quota"]["tokens_per_hour"]["remaining"] == 90


@pytest.mark.parametrize(
    "start,end,limit", [(60, 0, 10), (1, 2, 10), (True, 0, 10), (1, -1, 10), (29, 0, 0)]
)
def test_invalid_realtime_bounds_never_call_api(client, start, end, limit):
    with pytest.raises(ValueError):
        explore.realtime_report("123", [], [], start, end, limit=limit)
    client.run_realtime_report.assert_not_called()


COMPARISONS = [
    dict(
        name="mobile",
        dimension_filter={"field": "deviceCategory", "op": "EXACT", "value": "mobile"},
    ),
    dict(name="saved", comparison="comparisons/123"),
]
DATES = [
    dict(name="before", start_date="2026-09-01", end_date="2026-09-07"),
    dict(name="after", start_date="2026-09-08", end_date="2026-09-14"),
]


def test_comparisons_preserve_extra_columns_and_request_filters(client):
    client.run_report.return_value = types.RunReportResponse(
        row_count=1,
        dimension_headers=[{"name": "comparison"}, {"name": "dateRange"}],
        metric_headers=[{"name": "activeUsers"}],
        rows=[
            dict(
                dimension_values=[{"value": "mobile"}, {"value": "before"}],
                metric_values=[{"value": "5"}],
            )
        ],
    )
    out = ga4_mcp.comparison_report("123", ["activeUsers"], [], COMPARISONS, DATES)
    req = client.run_report.call_args.args[0]
    assert isinstance(req, types.RunReportRequest)
    assert req.property == "properties/123" and req.comparisons[1].comparison == "comparisons/123"
    assert req.comparisons[0].dimension_filter.filter.field_name == "deviceCategory"
    assert len(req.date_ranges) == 2 and req.date_ranges[1].name == "after"
    assert out["rows"] == [dict(comparison="mobile", dateRange="before", activeUsers="5")]
    assert out["complete"] and "warning" in out


@pytest.mark.parametrize(
    "comparisons,dates",
    [
        ([], DATES),
        (COMPARISONS * 3, DATES),
        ([{"name": "x"}], DATES),
        ([dict(COMPARISONS[0], comparison="comparisons/123")], DATES),
        ([dict(COMPARISONS[1], comparison="properties/999/comparisons/123")], DATES),
        ([dict(COMPARISONS[1], extra=True)], DATES),
        (COMPARISONS, []),
        (COMPARISONS, [dict(DATES[0], start_date=None)]),
        (COMPARISONS, [dict(DATES[0], name="RESERVED_bad")]),
        (COMPARISONS, DATES + DATES),
        ([{"comparison": "comparisons/123"}], DATES),
    ],
)
def test_invalid_comparisons_fail_before_auth(client, comparisons, dates):
    with pytest.raises(ValueError):
        explore.comparison_report("123", [], [], comparisons, dates)
    client.run_report.assert_not_called()


def test_cli_modes_and_rejected_ignored_flags(client, monkeypatch, capsys):
    client.run_realtime_report.return_value = types.RunRealtimeReportResponse()
    monkeypatch.setattr(
        "sys.argv", ["explore", "--property", "123", "--realtime", "--metrics", "eventCount"]
    )
    assert explore.main() == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    monkeypatch.setattr(
        "sys.argv",
        [
            "explore",
            "--property",
            "123",
            "--realtime",
            "--metrics",
            "eventCount",
            "--date-ranges",
            "[]",
        ],
    )
    assert explore.main() == 1
    assert "minute ranges" in capsys.readouterr().err
    client.run_report.return_value = types.RunReportResponse()
    monkeypatch.setattr(
        "sys.argv",
        [
            "explore",
            "--property",
            "123",
            "--comparisons",
            json.dumps(COMPARISONS),
            "--metrics",
            "activeUsers",
            "--date-ranges",
            json.dumps(DATES),
        ],
    )
    assert explore.main() == 0
    assert json.loads(capsys.readouterr().out)["report_type"] == "same_property_comparisons"
