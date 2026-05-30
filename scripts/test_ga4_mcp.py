from unittest import mock

import pytest

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


def test_expired_credentials_refresh_error_surfaces_as_auth_required():
    from google.auth.exceptions import RefreshError

    with mock.patch.object(
        ga4_mcp.ga4_audit,
        "orchestrate",
        side_effect=RefreshError("Reauthentication is needed"),
    ):
        out = ga4_mcp.audit(property_id="123")
    assert out["error"] == "auth_required"
    assert "gcloud" in out["hint"]


def test_reauth_api_error_surfaces_as_auth_required():
    from google.api_core.exceptions import ServiceUnavailable

    with mock.patch.object(
        ga4_mcp.ga4_audit,
        "orchestrate",
        side_effect=ServiceUnavailable(
            "Getting metadata from plugin failed with error: Reauthentication is needed."
        ),
    ):
        out = ga4_mcp.audit(property_id="123")
    assert out["error"] == "auth_required"
    assert "gcloud" in out["hint"]


def test_non_auth_error_is_not_swallowed():
    with mock.patch.object(ga4_mcp.ga4_audit, "orchestrate", side_effect=ValueError("boom")):
        with pytest.raises(ValueError):
            ga4_mcp.audit(property_id="123")


def test_server_reports_resolved_package_version():
    assert ga4_mcp.mcp._mcp_server.version == ga4_mcp._resolve_version()
    assert ga4_mcp.mcp._mcp_server.version  # non-empty


# ---------- dry-run / confirm contract across every write tool ----------
#
# The single most safety-critical behaviour of the MCP server: a write tool
# must NEVER touch the Admin API unless confirm=true. Each tool funnels through
# the _preview / _applied helpers, but they are wired by hand per tool, so the
# contract is verified for every one rather than a representative sample.

WRITE_TOOLS = [
    ("add_key_event", {"property_id": "123", "event_name": "purchase"}, "create_key_event"),
    ("delete_key_event", {"name": "properties/123/keyEvents/9"}, "delete_key_event"),
    (
        "create_audience",
        {"property_id": "123", "definition": {"displayName": "Buyers"}},
        "create_audience",
    ),
    ("archive_audience", {"audience_name": "properties/123/audiences/5"}, "archive_audience"),
    (
        "add_custom_dimension",
        {"property_id": "123", "parameter_name": "brand", "display_name": "Brand"},
        "create_custom_dimension",
    ),
    (
        "add_custom_metric",
        {
            "property_id": "123",
            "parameter_name": "score",
            "display_name": "Score",
            "measurement_unit": "STANDARD",
        },
        "create_custom_metric",
    ),
    (
        "archive_custom_dimension",
        {"name": "properties/123/customDimensions/1"},
        "archive_custom_dimension",
    ),
    (
        "archive_custom_metric",
        {"name": "properties/123/customMetrics/1"},
        "archive_custom_metric",
    ),
    (
        "add_event_edit_rule",
        {"property_id": "123", "stream_id": "9", "definition": {"display_name": "Rule"}},
        "create_event_edit_rule",
    ),
    (
        "add_event_create_rule",
        {"property_id": "123", "stream_id": "9", "definition": {"destination_event": "lead"}},
        "create_event_create_rule",
    ),
    (
        "delete_event_edit_rule",
        {"rule_name": "properties/123/dataStreams/9/eventEditRules/5"},
        "delete_event_edit_rule",
    ),
]

_WRITE_IDS = [t[0] for t in WRITE_TOOLS]


@pytest.mark.parametrize("tool_name,kwargs,admin_attr", WRITE_TOOLS, ids=_WRITE_IDS)
def test_write_tool_dry_run_makes_no_api_call(tool_name, kwargs, admin_attr):
    tool = getattr(ga4_mcp, tool_name)
    with mock.patch.object(ga4_mcp.ga4_admin, admin_attr) as adapter:
        out = tool(**kwargs)
    adapter.assert_not_called()
    assert out["preview"] is True
    assert out["applied"] is False
    assert "would_apply" in out


@pytest.mark.parametrize("tool_name,kwargs,admin_attr", WRITE_TOOLS, ids=_WRITE_IDS)
def test_write_tool_confirm_executes(tool_name, kwargs, admin_attr):
    tool = getattr(ga4_mcp, tool_name)
    sentinel = {"name": "applied-resource"}
    with mock.patch.object(ga4_mcp.ga4_admin, admin_attr, return_value=sentinel) as adapter:
        out = tool(confirm=True, **kwargs)
    adapter.assert_called_once()
    assert out["preview"] is False
    assert out["applied"] is True
    assert out["result"] == sentinel
