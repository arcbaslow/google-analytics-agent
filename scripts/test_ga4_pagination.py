"""Mocked pagination contracts using actual supported SDK messages."""

from unittest.mock import Mock

import ga4_data
import ga4_definitions as definitions
import pytest
from google.analytics.data_v1beta.types import RunReportResponse


def page(values, count=3):
    return RunReportResponse(
        dimension_headers=[{"name": "country"}],
        metric_headers=[{"name": "sessions"}],
        row_count=count,
        rows=[
            {"dimension_values": [{"value": v}], "metric_values": [{"value": "1"}]} for v in values
        ],
    )


def test_pages_keep_offsets_order_metadata_and_scrubbing(monkeypatch):
    client = Mock()
    client.run_report.side_effect = [page(["A", "B"]), page(["person@example.com"])]
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    out = ga4_data.run_report("123", ["sessions"], ["country"], page_size=2, include_metadata=True)
    assert out["complete"] and out["rows_returned"] == 3
    assert len(out["metadata"]["pages"]) == 2
    assert "person@example.com" not in str(out)
    requests = [c.args[0] for c in client.run_report.call_args_list]
    assert [r.offset for r in requests] == [0, 2]
    assert requests[0].order_bys[0].dimension.dimension_name == "country"


@pytest.mark.parametrize(
    "pages,options,reason",
    [
        ([page(["A", "B"])], {"limit": 2}, "row_limit"),
        ([page(["A"])], {"max_pages": 1}, "page_limit"),
        ([page([])], {}, "empty_page_before_end"),
        ([page(["A"]), page(["B"], count=4)], {}, "report_changed_between_pages"),
    ],
)
def test_partial_results_are_explicit_and_not_cached(monkeypatch, pages, options, reason):
    client = Mock()
    client.run_report.side_effect = pages
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    write = Mock()
    monkeypatch.setattr(ga4_data, "cache_set", write)
    out = ga4_data.run_report("123", ["sessions"], ["country"], **options)
    assert out["complete"] is False and out["incomplete_reason"] == reason
    write.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"page_size": 250001},
        {"max_pages": True},
        {"start_date": "2026-01-01"},
        {"start_date": "2026-02-01", "end_date": "2026-01-01"},
        {"days": 0},
    ],
)
def test_invalid_options_make_no_request(monkeypatch, options):
    factory = Mock()
    monkeypatch.setattr(ga4_data, "_get_data_client", factory)
    with pytest.raises(ValueError):
        ga4_data.run_report("123", ["sessions"], [], **options)
    factory.assert_not_called()


@pytest.mark.parametrize(
    "definition",
    [
        {"metrics": "sessions"},
        {"metrics": []},
        {"metrics": ["sessions"], "unknown": 1},
        {"metrics": ["sessions"], "limit": -1},
        {"metrics": ["sessions"], "default_format": "xml"},
        {"metrics": ["sessions"], "dimension_filter": {"typo": {}}},
    ],
)
def test_saved_report_rejects_invalid_intent(definition):
    with pytest.raises(ValueError):
        definitions.validate_report_def(definition)


def test_saved_options_default_format_and_combined_segment(monkeypatch):
    monkeypatch.setattr(
        definitions,
        "load_report_def",
        lambda name: {
            "metrics": ["sessions"],
            "default_format": "csv",
            "limit": 3,
            "dimension_filter": {"field": "country", "op": "EXACT", "value": "US"},
            "metric_filter": {
                "filter": {
                    "field_name": "sessions",
                    "numeric_filter": {"operation": "GREATER_THAN", "value": {"int64_value": "1"}},
                }
            },
            "order_bys": [{"metric": {"metric_name": "sessions"}, "desc": True}],
        },
    )
    monkeypatch.setattr(
        definitions,
        "load_segment",
        lambda name: {
            "filter_expression": {"field": "eventName", "op": "EXACT", "value": "purchase"}
        },
    )
    report = Mock(return_value={"rows": [{"sessions": "2"}]})
    monkeypatch.setattr(ga4_data, "run_report", report)
    assert "sessions" in definitions.run_report_def("test", "123", segment="buyers")
    options = report.call_args.kwargs
    assert options["limit"] == 3 and options["metric_filter"]
    assert len(options["filter_dict"]["and_group"]["expressions"]) == 2


def test_custom_dimension_shorthand():
    assert ga4_data.parse_filter("customEvent:plan = paid")["field"] == "customEvent:plan"
