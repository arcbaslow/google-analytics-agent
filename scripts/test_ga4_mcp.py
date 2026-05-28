from unittest import mock

import ga4_auth
import ga4_mcp


def test_benchmarks_tool_returns_vertical_bands():
    fake = {"vertical": "ecommerce", "bands": {"bounce_rate": {"p50": 0.4}}}
    with mock.patch.object(ga4_mcp.ga4_benchmarks, "benchmarks_for", return_value=fake["bands"]):
        out = ga4_mcp.benchmarks(vertical="ecommerce")
    assert out["vertical"] == "ecommerce"
    assert "bands" in out


def test_audit_tool_wraps_orchestrate():
    agents = [{"agent": "ga4-quality", "summary": "ok", "findings": [], "data": {}}]
    with mock.patch.object(
        ga4_mcp.ga4_audit,
        "orchestrate",
        return_value=(agents, {"site": {}}, "ecommerce", "high"),
    ):
        out = ga4_mcp.audit(property_id="123", days=28)
    assert out["vertical"] == "ecommerce"
    assert out["confidence"] == "high"
    assert out["agents"] == agents


def test_funnel_tool_wraps_build_funnel():
    with mock.patch.object(ga4_mcp.ga4_funnel, "build_funnel", return_value={"steps": []}) as bf:
        out = ga4_mcp.funnel(property_id="123", steps=["view_item", "purchase"], days=14)
    bf.assert_called_once()
    assert out == {"steps": []}


def test_list_events_tool():
    with mock.patch.object(ga4_mcp.ga4_events, "list_events", return_value={"events": ["x"]}):
        out = ga4_mcp.events(property_id="123", days=7)
    assert out == {"events": ["x"]}


def test_create_key_event_preview_makes_no_api_call():
    with mock.patch.object(ga4_mcp.ga4_admin, "create_key_event") as create:
        out = ga4_mcp.add_key_event(property_id="123", event_name="purchase")
    create.assert_not_called()
    assert out["preview"] is True
    assert out["would_apply"]["event_name"] == "purchase"


def test_create_key_event_confirm_executes():
    with mock.patch.object(
        ga4_mcp.ga4_admin,
        "create_key_event",
        return_value={"name": "properties/123/keyEvents/9"},
    ) as create:
        out = ga4_mcp.add_key_event(property_id="123", event_name="purchase", confirm=True)
    create.assert_called_once_with("123", "purchase", counting_method="ONCE_PER_EVENT")
    assert out["applied"] is True
    assert out["result"]["name"].endswith("/9")


def test_create_audience_preview_then_apply():
    definition = {"displayName": "Buyers", "filterClauses": []}
    with mock.patch.object(ga4_mcp.ga4_admin, "create_audience") as create:
        preview = ga4_mcp.create_audience(property_id="123", definition=definition)
    create.assert_not_called()
    assert preview["preview"] is True
    assert preview["would_apply"] == definition

    with mock.patch.object(
        ga4_mcp.ga4_admin,
        "create_audience",
        return_value={"name": "properties/123/audiences/5"},
    ) as create:
        applied = ga4_mcp.create_audience(property_id="123", definition=definition, confirm=True)
    create.assert_called_once_with("123", definition)
    assert applied["applied"] is True


def test_list_audiences_tool():
    with mock.patch.object(ga4_mcp.ga4_admin, "list_audiences", return_value=[{"name": "a"}]):
        out = ga4_mcp.list_audiences(property_id="123")
    assert out == [{"name": "a"}]


def test_list_segments_tool():
    with mock.patch.object(ga4_mcp.ga4_definitions, "list_segments", return_value=[{"name": "s"}]):
        out = ga4_mcp.list_segments()
    assert out == [{"name": "s"}]


def test_run_saved_report_tool():
    with mock.patch.object(
        ga4_mcp.ga4_definitions, "run_report_def", return_value={"rows": []}
    ) as rr:
        out = ga4_mcp.run_saved_report(name="weekly", property_id="123")
    rr.assert_called_once()
    assert out == {"rows": []}


def test_audit_surfaces_auth_error_as_structured_result():
    with mock.patch.object(
        ga4_mcp.ga4_audit,
        "orchestrate",
        side_effect=ga4_auth.AuthRequiredError("run gcloud ..."),
    ):
        out = ga4_mcp.audit(property_id="123")
    assert out["error"] == "auth_required"
    assert "gcloud" in out["hint"]
