"""Tests for ga4_definitions: segment and custom-report local storage."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import ga4_data
import ga4_definitions


@pytest.fixture(autouse=True)
def _redirect_definitions_dir(monkeypatch, tmp_path):
    """Point all definition storage at a temp directory for every test."""
    base = tmp_path / "ga4-definitions"
    monkeypatch.setattr(ga4_definitions, "DEFINITIONS_DIR", base)
    monkeypatch.setattr(ga4_definitions, "SEGMENTS_DIR", base / "segments")
    monkeypatch.setattr(ga4_definitions, "REPORTS_DIR", base / "reports")
    return base


# ---------- segments ----------


def test_save_segment_persists_to_disk(tmp_path):
    path = ga4_definitions.save_segment(
        "branded traffic",
        {"field": "sessionSource", "op": "CONTAINS", "value": "brand"},
        description="branded traffic",
    )
    assert Path(path).exists()
    loaded = ga4_definitions.load_segment("branded traffic")
    assert loaded["name"] == "branded traffic"
    assert loaded["filter_expression"]["op"] == "CONTAINS"


def test_slug_handles_capitals_and_spaces():
    path = ga4_definitions.save_segment(
        "US Only", {"field": "country", "op": "EXACT", "value": "United States"}
    )
    assert path.name == "us-only.json"


def test_list_segments_returns_summaries():
    ga4_definitions.save_segment(
        "a", {"field": "f", "op": "EXACT", "value": "x"}, description="first"
    )
    ga4_definitions.save_segment(
        "b", {"field": "f", "op": "EXACT", "value": "y"}, description="second"
    )
    seg_list = ga4_definitions.list_segments()
    names = sorted(s["name"] for s in seg_list)
    assert names == ["a", "b"]


def test_delete_segment_removes_file():
    ga4_definitions.save_segment("tmp", {"field": "f", "op": "EXACT", "value": "v"})
    ga4_definitions.delete_segment("tmp")
    with pytest.raises(FileNotFoundError):
        ga4_definitions.load_segment("tmp")


def test_load_missing_segment_raises():
    with pytest.raises(FileNotFoundError):
        ga4_definitions.load_segment("never-existed")


# ---------- reports ----------

REPORT_DEF = {
    "description": "weekly channels",
    "metrics": ["activeUsers", "sessions"],
    "dimensions": ["sessionDefaultChannelGroup", "week"],
    "default_days": 28,
    "default_format": "html",
}


def test_save_report_def_roundtrips():
    ga4_definitions.save_report_def("channels", REPORT_DEF)
    loaded = ga4_definitions.load_report_def("channels")
    assert loaded["metrics"] == ["activeUsers", "sessions"]
    assert loaded["dimensions"] == ["sessionDefaultChannelGroup", "week"]


def test_save_report_def_requires_metrics():
    with pytest.raises(ValueError, match="metrics"):
        ga4_definitions.save_report_def("bad", {"dimensions": ["country"]})


def test_list_report_defs_includes_dims_and_metrics():
    ga4_definitions.save_report_def("channels", REPORT_DEF)
    out = ga4_definitions.list_report_defs()
    assert len(out) == 1
    assert out[0]["metrics"] == ["activeUsers", "sessions"]


def test_delete_report_def_removes_file():
    ga4_definitions.save_report_def("channels", REPORT_DEF)
    ga4_definitions.delete_report_def("channels")
    with pytest.raises(FileNotFoundError):
        ga4_definitions.load_report_def("channels")


# ---------- CSV serialization ----------


def test_to_csv_emits_header_and_rows():
    payload = {
        "rows": [
            {"country": "United States", "activeUsers": "100"},
            {"country": "Germany", "activeUsers": "20"},
        ]
    }
    csv_text = ga4_definitions._to_csv(payload)
    assert "country,activeUsers" in csv_text
    assert "United States,100" in csv_text
    assert "Germany,20" in csv_text


def test_to_csv_empty_returns_empty_string():
    assert ga4_definitions._to_csv({"rows": []}) == ""
    assert ga4_definitions._to_csv({}) == ""


# ---------- build_filter_from_definition ----------


def test_build_filter_shorthand_returns_filter_expression():
    from google.analytics.data_v1beta.types import FilterExpression

    fe = ga4_definitions.build_filter_from_definition(
        {"field": "eventName", "op": "EXACT", "value": "purchase"}
    )
    assert isinstance(fe, FilterExpression)
    assert fe.filter.field_name == "eventName"


def test_build_filter_raw_filter_expression_roundtrips():
    """Regression: ParseDict on a proto-plus FilterExpression used to raise
    AttributeError("Unknown field ... DESCRIPTOR")."""
    from google.analytics.data_v1beta.types import FilterExpression

    fe = ga4_definitions.build_filter_from_definition(
        {
            "filter": {
                "field_name": "country",
                "string_filter": {"match_type": "EXACT", "value": "US"},
            }
        }
    )
    assert isinstance(fe, FilterExpression)
    assert fe.filter.field_name == "country"
    assert fe.filter.string_filter.value == "US"


def test_build_filter_raw_and_group_composite():
    fe = ga4_definitions.build_filter_from_definition(
        {
            "and_group": {
                "expressions": [
                    {"filter": {"field_name": "country", "string_filter": {"value": "US"}}}
                ]
            }
        }
    )
    assert len(fe.and_group.expressions) == 1


# ---------- run_report_def format dispatch ----------

REPORT_DEF_RUN = {
    "description": "channels",
    "metrics": ["activeUsers"],
    "dimensions": ["sessionDefaultChannelGroup"],
    "default_days": 28,
}

_ROWS = {
    "rows": [{"sessionDefaultChannelGroup": "Direct", "activeUsers": "5"}],
    "metrics": ["activeUsers"],
}


def test_run_report_def_rejects_unknown_format():
    with pytest.raises(ValueError, match="format must be one of"):
        ga4_definitions.run_report_def("anything", "123", format="xml")


def test_run_report_def_json_wraps_definition_and_result(monkeypatch):
    ga4_definitions.save_report_def("channels", REPORT_DEF_RUN)
    monkeypatch.setattr(ga4_data, "run_report", lambda **kw: _ROWS)
    out = ga4_definitions.run_report_def("channels", "123")
    assert out["definition"]["name"] == "channels"
    assert out["result"]["rows"][0]["sessionDefaultChannelGroup"] == "Direct"


def test_run_report_def_applies_days_override(monkeypatch):
    ga4_definitions.save_report_def("channels", REPORT_DEF_RUN)
    seen = {}
    monkeypatch.setattr(ga4_data, "run_report", lambda **kw: seen.update(kw) or _ROWS)
    ga4_definitions.run_report_def("channels", "123", days_override=7)
    assert seen["days"] == 7


def test_run_report_def_csv_format(monkeypatch):
    ga4_definitions.save_report_def("channels", REPORT_DEF_RUN)
    monkeypatch.setattr(ga4_data, "run_report", lambda **kw: _ROWS)
    out = ga4_definitions.run_report_def("channels", "123", format="csv")
    assert "sessionDefaultChannelGroup,activeUsers" in out
    assert "Direct,5" in out


def test_run_report_def_markdown_format(monkeypatch):
    ga4_definitions.save_report_def("channels", REPORT_DEF_RUN)
    monkeypatch.setattr(ga4_data, "run_report", lambda **kw: _ROWS)
    out = ga4_definitions.run_report_def("channels", "123", format="md")
    assert out.startswith("# channels")


def test_run_report_def_html_format(monkeypatch):
    ga4_definitions.save_report_def("channels", REPORT_DEF_RUN)
    monkeypatch.setattr(ga4_data, "run_report", lambda **kw: _ROWS)
    out = ga4_definitions.run_report_def("channels", "123", format="html")
    assert "<table" in out


def test_run_report_def_with_segment_reruns_through_filter(monkeypatch):
    ga4_definitions.save_report_def("channels", REPORT_DEF_RUN)
    ga4_definitions.save_segment(
        "buyers", {"field": "eventName", "op": "EXACT", "value": "purchase"}
    )
    monkeypatch.setattr(ga4_data, "run_report", lambda **kw: _ROWS)
    captured = {}

    def fake_apply(property_id, defn, days, filter_expression):
        captured["filter"] = filter_expression
        return {"rows": [{"segmented": "yes"}]}

    monkeypatch.setattr(ga4_definitions, "_apply_segment_and_rerun", fake_apply)
    out = ga4_definitions.run_report_def("channels", "123", segment="buyers")

    assert captured["filter"]["value"] == "purchase"
    assert out["result"]["rows"] == [{"segmented": "yes"}]


def test_apply_segment_and_rerun_builds_request_with_dimension_filter(monkeypatch):
    monkeypatch.setattr(ga4_data, "date_range", lambda days: ("2026-01-01", "2026-01-28"))
    client = MagicMock()
    sent = {}
    client.run_report.side_effect = lambda req: sent.setdefault("req", req) or MagicMock()
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    monkeypatch.setattr(
        ga4_data,
        "_serialize_run_report",
        lambda resp, include_metadata=False: {"rows": [{"ok": "1"}]},
    )

    defn = {"metrics": ["activeUsers"], "dimensions": ["country"]}
    out = ga4_definitions._apply_segment_and_rerun(
        "123", defn, 28, {"field": "country", "op": "EXACT", "value": "US"}
    )

    assert out["rows"] == [{"ok": "1"}]
    req = sent["req"]
    assert req.property == "properties/123"
    assert req.dimension_filter is not None
