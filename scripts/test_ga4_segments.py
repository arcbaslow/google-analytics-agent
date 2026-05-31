"""Unit tests for the deterministic segments agent (ga4_audit.run_segments)."""

import ga4_audit
import ga4_data
import ga4_definitions


def _wire(monkeypatch, by_dim):
    """Mock run_report (dispatched by dimensions[0]) and an empty segment store.

    Saved-segment tests below set up their own run_report / list_segments mocks."""

    def fake_run_report(*args, **kwargs):
        dims = kwargs.get("dimensions") or []
        return by_dim[dims[0]]

    monkeypatch.setattr(ga4_data, "run_report", fake_run_report)
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [])


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


def _eng(dim, rows):
    return {"dimensions": [dim], "metrics": ["sessions", "engagementRate"], "rows": rows}


def test_engagement_fallback_when_no_key_events(monkeypatch):
    # probe returns keyEvents total 0 -> engagement mode; cohorts then carry engagementRate
    probe_zero = {
        "dimensions": ["deviceCategory"],
        "metrics": ["sessions", "keyEvents"],
        "rows": [{"deviceCategory": "mobile", "sessions": "5000", "keyEvents": "0"}],
    }
    eng_by_dim = {
        "deviceCategory": _eng(
            "deviceCategory",
            [
                {"deviceCategory": "mobile", "sessions": "6000", "engagementRate": "0.20"},
                {"deviceCategory": "desktop", "sessions": "4000", "engagementRate": "0.70"},
            ],
        ),
        "newVsReturning": _eng(
            "newVsReturning",
            [
                {"newVsReturning": "new", "sessions": "10000", "engagementRate": "0.55"},
            ],
        ),
        "sessionDefaultChannelGroup": _eng(
            "sessionDefaultChannelGroup",
            [
                {
                    "sessionDefaultChannelGroup": "Organic",
                    "sessions": "10000",
                    "engagementRate": "0.55",
                },
            ],
        ),
    }

    def fake_run_report(*args, **kwargs):
        dims = kwargs.get("dimensions") or []
        metrics = kwargs.get("metrics") or []
        if metrics[:2] == ["sessions", "keyEvents"]:
            return probe_zero  # the probe
        return eng_by_dim[dims[0]]

    monkeypatch.setattr(ga4_data, "run_report", fake_run_report)
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [])

    out = ga4_audit.run_segments("123", days=28)
    assert out["data"]["mode"] == "engagement"
    mobile = next(f for f in out["findings"] if "mobile" in f["title"])
    assert mobile["metric"] == "engagement_rate"


def test_saved_segment_underperformance_flagged(monkeypatch):
    by_dim = {
        "deviceCategory": _conv(
            "deviceCategory",
            [
                {"deviceCategory": "desktop", "sessions": "10000", "keyEvents": "200"},
            ],
        ),
        "newVsReturning": _conv(
            "newVsReturning",
            [
                {"newVsReturning": "new", "sessions": "10000", "keyEvents": "200"},
            ],
        ),
        "sessionDefaultChannelGroup": _conv(
            "sessionDefaultChannelGroup",
            [
                {"sessionDefaultChannelGroup": "Organic", "sessions": "10000", "keyEvents": "200"},
            ],
        ),
    }
    # site baseline = 200/10000 = 2%. Segment converts at 0.5% -> well under 0.5x.
    seg_report = {
        "dimensions": [],
        "metrics": ["sessions", "keyEvents"],
        "rows": [{"sessions": "2000", "keyEvents": "10"}],
    }
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [{"name": "paid social"}])
    monkeypatch.setattr(
        ga4_definitions,
        "load_segment",
        lambda name: {
            "name": name,
            "filter_expression": {"field": "x", "op": "EXACT", "value": name},
        },
    )

    def fake(*args, **kwargs):
        if kwargs.get("filter_dict") is not None:
            return seg_report
        return by_dim[kwargs["dimensions"][0]]

    monkeypatch.setattr(ga4_data, "run_report", fake)

    out = ga4_audit.run_segments("123", days=28)
    assert out["data"]["saved_segments"][0]["name"] == "paid social"
    assert any("saved segment: paid social" in f["title"] for f in out["findings"])
    seg_finding = next(f for f in out["findings"] if "saved segment: paid social" in f["title"])
    assert "of sessions on this breakdown" not in seg_finding["detail"]


def test_saved_segment_run_error_is_captured(monkeypatch):
    by_dim = {
        "deviceCategory": _conv(
            "deviceCategory",
            [
                {"deviceCategory": "desktop", "sessions": "10000", "keyEvents": "200"},
            ],
        ),
        "newVsReturning": _conv(
            "newVsReturning",
            [
                {"newVsReturning": "new", "sessions": "10000", "keyEvents": "200"},
            ],
        ),
        "sessionDefaultChannelGroup": _conv(
            "sessionDefaultChannelGroup",
            [
                {"sessionDefaultChannelGroup": "Organic", "sessions": "10000", "keyEvents": "200"},
            ],
        ),
    }

    def fake(*args, **kwargs):
        if kwargs.get("filter_dict") is not None:
            raise RuntimeError("bad filter")
        return by_dim[kwargs["dimensions"][0]]

    monkeypatch.setattr(ga4_data, "run_report", fake)
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [{"name": "broken"}])
    monkeypatch.setattr(
        ga4_definitions,
        "load_segment",
        lambda name: {
            "name": name,
            "filter_expression": {"field": "x", "op": "EXACT", "value": "y"},
        },
    )

    out = ga4_audit.run_segments("123", days=28)
    entry = out["data"]["saved_segments"][0]
    assert entry["name"] == "broken"
    assert "error" in entry


def test_run_segments_never_raises_on_total_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("data api down")

    monkeypatch.setattr(ga4_data, "run_report", boom)
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [])

    out = ga4_audit.run_segments("123", days=28)
    assert out["agent"] == "ga4-segments"
    assert any(f["severity"] == "Medium" for f in out["findings"])
