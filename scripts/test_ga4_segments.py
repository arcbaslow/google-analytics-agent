"""Unit tests for the deterministic segments agent (ga4_audit.run_segments)."""

import ga4_audit
import ga4_data
import ga4_definitions


def _wire(monkeypatch, by_dim, segments=None, seg_reports=None):
    """Mock run_report (dispatched by dimensions[0], or by filter_dict for
    saved segments) and the segment store."""

    def fake_run_report(*args, **kwargs):
        if kwargs.get("filter_dict") is not None:
            name = kwargs.get("_seg_name")
            return (seg_reports or {})[name]
        dims = kwargs.get("dimensions") or []
        return by_dim[dims[0]]

    monkeypatch.setattr(ga4_data, "run_report", fake_run_report)
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: segments or [])
    monkeypatch.setattr(
        ga4_definitions,
        "load_segment",
        lambda name: {
            "name": name,
            "filter_expression": {"field": "x", "op": "EXACT", "value": name},
        },
    )


def _conv(dim, rows):
    return {"dimensions": [dim], "metrics": ["sessions", "keyEvents"], "rows": rows}


def test_conversion_mode_flags_high_for_dominant_low_cohort(monkeypatch):
    by_dim = {
        "deviceCategory": _conv(
            "deviceCategory",
            [
                {"deviceCategory": "mobile", "sessions": "6000", "keyEvents": "24"},
                {"deviceCategory": "desktop", "sessions": "4000", "keyEvents": "76"},
            ],
        ),
        "newVsReturning": _conv(
            "newVsReturning",
            [
                {"newVsReturning": "new", "sessions": "5000", "keyEvents": "50"},
                {"newVsReturning": "returning", "sessions": "5000", "keyEvents": "50"},
            ],
        ),
        "sessionDefaultChannelGroup": _conv(
            "sessionDefaultChannelGroup",
            [
                {"sessionDefaultChannelGroup": "Organic", "sessions": "10000", "keyEvents": "100"},
            ],
        ),
    }
    _wire(monkeypatch, by_dim)
    out = ga4_audit.run_segments("123", days=28)

    assert out["agent"] == "ga4-segments"
    assert out["data"]["mode"] == "conversion"
    titles = [f["title"] for f in out["findings"]]
    assert any("deviceCategory = mobile" in t for t in titles)
    dev = next(f for f in out["findings"] if "deviceCategory = mobile" in f["title"])
    assert dev["severity"] == "High"
    assert dev["metric"] == "conversion_rate"
    assert dev["metric_value"] < 0.01


def test_conversion_mode_medium_for_small_share_cohort(monkeypatch):
    by_dim = {
        "deviceCategory": _conv(
            "deviceCategory",
            [
                {"deviceCategory": "desktop", "sessions": "8500", "keyEvents": "170"},
                {"deviceCategory": "tablet", "sessions": "1500", "keyEvents": "3"},
            ],
        ),
        "newVsReturning": _conv(
            "newVsReturning",
            [
                {"newVsReturning": "new", "sessions": "10000", "keyEvents": "150"},
            ],
        ),
        "sessionDefaultChannelGroup": _conv(
            "sessionDefaultChannelGroup",
            [
                {"sessionDefaultChannelGroup": "Organic", "sessions": "10000", "keyEvents": "150"},
            ],
        ),
    }
    _wire(monkeypatch, by_dim)
    out = ga4_audit.run_segments("123", days=28)
    tablet = next(f for f in out["findings"] if "tablet" in f["title"])
    assert tablet["severity"] == "Medium"


def test_cohorts_below_min_share_are_ignored(monkeypatch):
    by_dim = {
        "deviceCategory": _conv(
            "deviceCategory",
            [
                {"deviceCategory": "desktop", "sessions": "9500", "keyEvents": "190"},
                {"deviceCategory": "smarttv", "sessions": "500", "keyEvents": "0"},
            ],
        ),
        "newVsReturning": _conv(
            "newVsReturning",
            [
                {"newVsReturning": "new", "sessions": "10000", "keyEvents": "190"},
            ],
        ),
        "sessionDefaultChannelGroup": _conv(
            "sessionDefaultChannelGroup",
            [
                {"sessionDefaultChannelGroup": "Organic", "sessions": "10000", "keyEvents": "190"},
            ],
        ),
    }
    _wire(monkeypatch, by_dim)
    out = ga4_audit.run_segments("123", days=28)
    assert not any("smarttv" in f["title"] for f in out["findings"])
