"""Tests for the ga4_audit orchestrator. Mocks every adapter so the test
runs without an API."""

import pytest

import ga4_audit


# ---------- mechanical agent functions ----------


def test_run_quality_flags_high_direct_share(monkeypatch):
    monkeypatch.setattr(ga4_audit.ga4_data, "run_report", lambda **kw: _quality_report(kw))
    out = ga4_audit.run_quality("123", days=28)
    assert out["agent"] == "ga4-quality"
    titles = [f["title"] for f in out["findings"]]
    assert any("direct" in t.lower() for t in titles)
    # benchmark metric attached
    direct_findings = [f for f in out["findings"] if f.get("metric") == "direct_share"]
    assert direct_findings and direct_findings[0]["metric_value"] > 0.30


def _quality_report(kw):
    """Mock run_report responses for both the metadata call and the source call."""
    dims = tuple(kw.get("dimensions") or ())
    if dims == ("date",):
        return {
            "rows": [],
            "metadata": {
                "sampling": [{"sample_rate": 0.97}],
                "currency_code": "USD",
                "time_zone": "UTC",
            },
        }
    if dims == ("sessionSource",):
        return {
            "rows": [
                {"sessionSource": "(direct)", "sessions": "4200"},
                {"sessionSource": "google", "sessions": "5000"},
                {"sessionSource": "(not set)", "sessions": "800"},
            ],
        }
    return {"rows": []}


def test_run_events_full_ecomm_taxonomy_no_findings_when_coverage_ok(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_events,
        "list_events",
        lambda pid, days: {
            "rows": [
                {"eventName": "view_item", "eventCount": "1000"},
                {"eventName": "add_to_cart", "eventCount": "500"},
                {"eventName": "begin_checkout", "eventCount": "300"},
                {"eventName": "add_payment_info", "eventCount": "200"},
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    monkeypatch.setattr(
        ga4_audit.ga4_events,
        "event_params_coverage",
        lambda pid, ev, days: {
            "event": ev,
            "coverage": {"currency": {"coverage_pct": 99}, "value": {"coverage_pct": 100}},
        },
    )
    out = ga4_audit.run_events("123", days=7)
    assert out["data"]["distinct_event_count"] == 5
    assert out["data"]["ecomm_events_present"] == [
        "view_item",
        "add_to_cart",
        "begin_checkout",
        "add_payment_info",
        "purchase",
    ]
    assert all(f.get("severity") not in {"Critical", "High"} for f in out["findings"])


def test_run_events_partial_ecomm_raises_high_finding(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_events,
        "list_events",
        lambda pid, days: {
            "rows": [
                {"eventName": "view_item", "eventCount": "1000"},
                {"eventName": "purchase", "eventCount": "100"},
            ],
        },
    )
    out = ga4_audit.run_events("123")
    titles = [f["title"] for f in out["findings"]]
    assert any("Partial" in t for t in titles)


def test_run_conversions_flags_zero_key_events(monkeypatch):
    monkeypatch.setattr(ga4_audit.ga4_admin, "list_key_events", lambda pid: [])
    out = ga4_audit.run_conversions("123")
    assert out["data"]["key_event_count"] == 0
    assert any(f["severity"] == "Critical" for f in out["findings"])


def test_run_conversions_ok_when_two_key_events(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_admin,
        "list_key_events",
        lambda pid: [
            {"eventName": "purchase"},
            {"eventName": "generate_lead"},
        ],
    )
    out = ga4_audit.run_conversions("123")
    assert out["data"]["key_event_count"] == 2
    assert all(f["severity"] != "Critical" for f in out["findings"])


def test_run_property_flags_short_retention(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_admin,
        "get_property_details",
        lambda pid: {
            "displayName": "Acme",
            "dataRetentionSettings": {"eventDataRetention": "TWO_MONTHS"},
        },
    )
    monkeypatch.setattr(
        ga4_audit.ga4_admin,
        "list_data_streams",
        lambda pid: [
            {"displayName": "Web", "webStreamData": {"defaultUri": "https://example.com"}},
        ],
    )
    monkeypatch.setattr(ga4_audit.ga4_admin, "list_data_filters", lambda pid: [])
    monkeypatch.setattr(
        ga4_audit.ga4_admin,
        "list_custom_defs",
        lambda pid: {
            "custom_dimensions": [],
            "custom_metrics": [],
        },
    )
    out = ga4_audit.run_property("123")
    titles = [f["title"] for f in out["findings"]]
    assert any("retention shorter" in t.lower() for t in titles)


def test_run_funnel_skipped_when_no_steps():
    out = ga4_audit.run_funnel("123", steps=[], days=28)
    assert "skipped" in out["summary"]
    assert out["findings"] == []


def test_run_funnel_surfaces_leakiest_step(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_funnel,
        "build_funnel",
        lambda **kw: {
            "property_id": kw["property_id"],
            "window_days": kw["days"],
            "steps": kw["steps"],
            "rates": {
                "aggregate": {
                    "overall_conversion_pct": 2.1,
                    "leakiest_step": {
                        "from": "view_item",
                        "to": "add_to_cart",
                        "users_dropped": 142580,
                        "share_of_total_loss_pct": 64,
                    },
                }
            },
            "warnings": [],
        },
    )
    out = ga4_audit.run_funnel("123", steps=["view_item", "add_to_cart", "purchase"], days=28)
    cr_findings = [f for f in out["findings"] if f.get("metric") == "conversion_rate"]
    assert cr_findings and cr_findings[0]["metric_value"] == pytest.approx(0.021)
    titles = [f["title"] for f in out["findings"]]
    assert any("Leakiest step" in t for t in titles)


def test_run_attribution_flags_high_direct(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_admin,
        "get_attribution_settings",
        lambda pid: {
            "reporting_attribution_model": "DATA_DRIVEN",
        },
    )
    monkeypatch.setattr(
        ga4_audit.ga4_data,
        "run_report",
        lambda **kw: {
            "rows": [
                {"sessionDefaultChannelGroup": "Direct", "eventCount": "342"},
                {"sessionDefaultChannelGroup": "Organic Search", "eventCount": "400"},
                {"sessionDefaultChannelGroup": "Paid Search", "eventCount": "258"},
            ],
        },
    )
    out = ga4_audit.run_attribution("123")
    findings = [f for f in out["findings"] if f.get("metric") == "direct_share"]
    assert findings and findings[0]["metric_value"] == pytest.approx(0.342, abs=1e-3)


# ---------- orchestrator end-to-end ----------


def test_orchestrate_end_to_end(monkeypatch):
    """Smoke-test that orchestrate() wires the pieces together and returns the
    right shape."""
    monkeypatch.setattr(
        ga4_audit.ga4_context,
        "build_property_context",
        lambda pid, force=False: {
            "status": "ok",
            "context": {
                "property_id": pid,
                "site": {"inferred": {"vertical": "ecommerce"}, "summary": "Acme | ecomm"},
            },
        },
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_quality",
        lambda pid, days: ga4_audit._ok("ga4-quality", "ok", [], {"confidence_label": "high"}),
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_events",
        lambda pid, days: ga4_audit._ok(
            "ga4-events",
            "ok",
            [],
            {"ecomm_events_present": ["view_item", "add_to_cart", "purchase"]},
        ),
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_funnel",
        lambda pid, steps, days, check_postpayment: ga4_audit._ok(
            "ga4-funnel", "ok", [], {"steps": steps}
        ),
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_conversions",
        lambda pid: ga4_audit._ok("ga4-conversions", "ok", [], {"key_event_count": 2}),
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_attribution",
        lambda pid, days, primary_event: ga4_audit._ok(
            "ga4-attribution", "ok", [], {"called_with": primary_event}
        ),
    )
    monkeypatch.setattr(
        ga4_audit, "run_property", lambda pid: ga4_audit._ok("ga4-property", "ok", [], {})
    )

    agents_out, context, vertical, confidence = ga4_audit.orchestrate(
        property_id="999",
        days=14,
        funnel_steps_arg=None,
        vertical_override=None,
        check_postpayment=False,
        refresh_context=False,
    )

    agent_names = [a["agent"] for a in agents_out]
    assert agent_names == [
        "ga4-context",
        "ga4-quality",
        "ga4-events",
        "ga4-funnel",
        "ga4-segments",
        "ga4-conversions",
        "ga4-attribution",
        "ga4-property",
    ]
    assert vertical == "ecommerce"
    assert confidence == "high"
    assert context["site"]["inferred"]["vertical"] == "ecommerce"


def test_orchestrate_skips_attribution_without_key_events(monkeypatch):
    monkeypatch.setattr(
        ga4_audit.ga4_context,
        "build_property_context",
        lambda pid, force=False: {
            "status": "ok",
            "context": {"site": {"inferred": {"vertical": "other"}, "summary": "x"}},
        },
    )
    monkeypatch.setattr(
        ga4_audit, "run_quality", lambda pid, days: ga4_audit._ok("ga4-quality", "ok")
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_events",
        lambda pid, days: ga4_audit._ok("ga4-events", "ok", [], {"ecomm_events_present": []}),
    )
    monkeypatch.setattr(
        ga4_audit,
        "run_conversions",
        lambda pid: ga4_audit._ok("ga4-conversions", "no key events", [], {"key_event_count": 0}),
    )
    monkeypatch.setattr(ga4_audit, "run_property", lambda pid: ga4_audit._ok("ga4-property", "ok"))
    called = {"attribution": False}

    def _attr(*a, **kw):
        called["attribution"] = True
        return ga4_audit._ok("ga4-attribution", "ran")

    monkeypatch.setattr(ga4_audit, "run_attribution", _attr)

    agents_out, _ctx, vertical, _conf = ga4_audit.orchestrate(
        property_id="111",
        days=28,
        funnel_steps_arg=None,
        vertical_override=None,
        check_postpayment=False,
        refresh_context=False,
    )
    assert called["attribution"] is False
    attribution = next(a for a in agents_out if a["agent"] == "ga4-attribution")
    assert "skipped" in attribution["summary"]
    assert vertical == "other"


def test_resolve_funnel_steps_explicit_overrides_auto():
    args = ga4_audit._Namespace(funnel_steps="a,b,c")
    out = ga4_audit._resolve_funnel_steps(args, {})
    assert out == ["a", "b", "c"]


def test_resolve_funnel_steps_uses_present_ecomm_subset():
    args = ga4_audit._Namespace(funnel_steps=None)
    events_out = {
        "data": {"ecomm_events_present": ["view_item", "add_to_cart", "begin_checkout", "purchase"]}
    }
    out = ga4_audit._resolve_funnel_steps(args, events_out)
    assert out == ["view_item", "add_to_cart", "begin_checkout", "purchase"]


def test_resolve_funnel_steps_returns_empty_when_no_ecomm_overlap():
    args = ga4_audit._Namespace(funnel_steps=None)
    events_out = {"data": {"ecomm_events_present": ["purchase"]}}  # only 1 → below threshold
    out = ga4_audit._resolve_funnel_steps(args, events_out)
    assert out == []
