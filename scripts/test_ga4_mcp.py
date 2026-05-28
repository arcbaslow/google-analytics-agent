from unittest import mock

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
    with mock.patch.object(
        ga4_mcp.ga4_funnel, "build_funnel", return_value={"steps": []}
    ) as bf:
        out = ga4_mcp.funnel(property_id="123", steps=["view_item", "purchase"], days=14)
    bf.assert_called_once()
    assert out == {"steps": []}


def test_list_events_tool():
    with mock.patch.object(ga4_mcp.ga4_events, "list_events", return_value={"events": ["x"]}):
        out = ga4_mcp.events(property_id="123", days=7)
    assert out == {"events": ["x"]}
