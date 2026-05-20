"""Tests for ga4_definitions: segment and custom-report local storage."""

from pathlib import Path

import pytest

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
