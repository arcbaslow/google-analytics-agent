"""GA4 MCP server. Exposes the ga4_* CLI surface as MCP tools over stdio.

Reads/analysis return structured JSON unchanged from the underlying modules
(PII scrubbing and caching are inherited). Admin writes use a dry-run-first
confirmation contract: confirm=false (default) returns the resolved change
and makes no API call; confirm=true executes.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

import ga4_admin
import ga4_audit
import ga4_benchmarks
import ga4_context
import ga4_data
import ga4_definitions
import ga4_events
import ga4_funnel

mcp = FastMCP("google-analytics-agent")


@mcp.tool()
def benchmarks(vertical: str = "other") -> dict[str, Any]:
    """Return the benchmark band table for a vertical."""
    v = ga4_benchmarks.normalize_vertical(vertical)
    return {"vertical": v, "bands": ga4_benchmarks.benchmarks_for(v)}


@mcp.tool()
def audit(property_id: str, days: int = 28, vertical: str | None = None) -> dict[str, Any]:
    """Run the full GA4 audit. Returns agent outputs, context, vertical, confidence."""
    agents, ctx, resolved_vertical, confidence = ga4_audit.orchestrate(
        property_id, days=days, vertical_override=vertical
    )
    return {
        "agents": agents,
        "context": ctx,
        "vertical": resolved_vertical,
        "confidence": confidence,
    }


@mcp.tool()
def context(property_id: str, refresh: bool = False) -> dict[str, Any]:
    """Profile the property's live site: vertical, platform, framework, sitemap."""
    return ga4_context.build_property_context(property_id, force=refresh)


@mcp.tool()
def funnel(
    property_id: str,
    steps: list[str],
    days: int = 28,
    check_postpayment: bool = False,
) -> dict[str, Any]:
    """Build a funnel from an ordered list of event names."""
    return ga4_funnel.build_funnel(
        property_id, steps=steps, days=days, check_postpayment=check_postpayment
    )


@mcp.tool()
def events(property_id: str, days: int = 7) -> dict[str, Any]:
    """List distinct events seen on the property."""
    return ga4_events.list_events(property_id, days=days)


@mcp.tool()
def check_events(property_id: str, event_names: list[str], days: int = 7) -> dict[str, Any]:
    """Check presence of specific events."""
    return ga4_events.check_events(property_id, event_names, days=days)


@mcp.tool()
def quality(property_id: str, days: int = 28) -> dict[str, Any]:
    """Run the data-quality audit (sampling, direct share, not-set share)."""
    return ga4_audit.run_quality(property_id, days=days)


@mcp.tool()
def conversions(property_id: str) -> dict[str, Any]:
    """Audit key-events (conversions) configuration."""
    return ga4_audit.run_conversions(property_id)


@mcp.tool()
def attribution(
    property_id: str, days: int = 28, primary_event: str = "purchase"
) -> dict[str, Any]:
    """Channel attribution analysis."""
    return ga4_audit.run_attribution(property_id, days=days, primary_event=primary_event)


@mcp.tool()
def property_config(property_id: str) -> dict[str, Any]:
    """Property configuration audit."""
    return ga4_audit.run_property(property_id)


@mcp.tool()
def report(
    property_id: str, metrics: list[str], dimensions: list[str], days: int = 28
) -> dict[str, Any]:
    """Generic GA4 runReport."""
    return ga4_data.run_report(property_id, metrics=metrics, dimensions=dimensions, days=days)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
