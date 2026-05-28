from unittest import mock

import ga4_mcp


def test_benchmarks_tool_returns_vertical_bands():
    fake = {"vertical": "ecommerce", "bands": {"bounce_rate": {"p50": 0.4}}}
    with mock.patch.object(ga4_mcp.ga4_benchmarks, "benchmarks_for", return_value=fake["bands"]):
        out = ga4_mcp.benchmarks(vertical="ecommerce")
    assert out["vertical"] == "ecommerce"
    assert "bands" in out
