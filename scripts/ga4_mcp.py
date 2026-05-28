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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
