"""GA4 MCP server. Exposes the ga4_* CLI surface as MCP tools over stdio.

Reads/analysis return structured JSON unchanged from the underlying modules
(PII scrubbing and caching are inherited). Admin writes use a dry-run-first
confirmation contract: confirm=false (default) returns the resolved change
and makes no API call; confirm=true executes.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar, cast

import ga4_admin
import ga4_audit
import ga4_auth
import ga4_benchmarks
import ga4_context
import ga4_data
import ga4_definitions
import ga4_events
import ga4_funnel
from mcp.server.fastmcp import FastMCP


def _resolve_version() -> str:
    """Resolve the installed package version for the server handshake. Falls back
    to a source marker when the package isn't installed (e.g. running from a raw
    checkout without `pip install`)."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("google-analytics-agent")
        except PackageNotFoundError:
            return "0.0.0+source"
    except Exception:
        return "0.0.0+source"


mcp = FastMCP("google-analytics-agent")
# FastMCP has no `version` constructor argument; the underlying low-level server
# otherwise reports the `mcp` library's own version on initialize. Set our real
# package version so MCP clients see the toolkit version, not the SDK's.
mcp._mcp_server.version = _resolve_version()

F = TypeVar("F", bound=Callable[..., Any])


def _is_reauth_error(exc: BaseException) -> bool:
    """True for credential errors that a client fixes by re-authenticating:
    google-auth refresh failures (expired/revoked ADC) and API call errors that
    are 401s or carry a 'Reauthentication is needed' message."""
    try:
        from google.auth.exceptions import RefreshError

        if isinstance(exc, RefreshError):
            return True
    except ImportError:
        pass
    try:
        from google.api_core.exceptions import Unauthenticated

        if isinstance(exc, Unauthenticated):
            return True
    except ImportError:
        pass
    return "reauthentication is needed" in str(exc).lower()


def _auth_guarded(fn: F) -> F:
    """Wrap a tool so a credentials problem becomes a structured result instead of
    a stack trace over the wire. Covers both unresolved credentials
    (AuthRequiredError) and expired/revoked credentials surfaced at call time."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ga4_auth.AuthRequiredError as e:
            return {"error": "auth_required", "hint": e.hint}
        except Exception as e:
            if _is_reauth_error(e):
                return {
                    "error": "auth_required",
                    "hint": "Credentials are expired or require reauthentication. Run:\n  "
                    + ga4_auth.adc_command(write=False),
                }
            raise

    return cast(F, wrapper)


@mcp.tool()
def benchmarks(vertical: str = "other") -> dict[str, Any]:
    """Return the benchmark band table for a vertical."""
    v = ga4_benchmarks.normalize_vertical(vertical)
    return {"vertical": v, "bands": ga4_benchmarks.benchmarks_for(v)}


@mcp.tool()
@_auth_guarded
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
@_auth_guarded
def context(property_id: str, refresh: bool = False) -> dict[str, Any]:
    """Profile the property's live site: vertical, platform, framework, sitemap."""
    return ga4_context.build_property_context(property_id, force=refresh)


@mcp.tool()
@_auth_guarded
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
@_auth_guarded
def events(property_id: str, days: int = 7) -> dict[str, Any]:
    """List distinct events seen on the property."""
    return ga4_events.list_events(property_id, days=days)


@mcp.tool()
@_auth_guarded
def check_events(property_id: str, event_names: list[str], days: int = 7) -> dict[str, Any]:
    """Check presence of specific events."""
    return ga4_events.check_events(property_id, event_names, days=days)


@mcp.tool()
@_auth_guarded
def quality(property_id: str, days: int = 28) -> dict[str, Any]:
    """Run the data-quality audit (sampling, direct share, not-set share)."""
    return ga4_audit.run_quality(property_id, days=days)


@mcp.tool()
@_auth_guarded
def conversions(property_id: str) -> dict[str, Any]:
    """Audit key-events (conversions) configuration."""
    return ga4_audit.run_conversions(property_id)


@mcp.tool()
@_auth_guarded
def attribution(
    property_id: str, days: int = 28, primary_event: str = "purchase"
) -> dict[str, Any]:
    """Channel attribution analysis."""
    return ga4_audit.run_attribution(property_id, days=days, primary_event=primary_event)


@mcp.tool()
@_auth_guarded
def property_config(property_id: str) -> dict[str, Any]:
    """Property configuration audit."""
    return ga4_audit.run_property(property_id)


@mcp.tool()
@_auth_guarded
def report(
    property_id: str, metrics: list[str], dimensions: list[str], days: int = 28
) -> dict[str, Any]:
    """Generic GA4 runReport."""
    return ga4_data.run_report(property_id, metrics=metrics, dimensions=dimensions, days=days)


def _preview(would_apply: Any) -> dict[str, Any]:
    return {
        "preview": True,
        "applied": False,
        "would_apply": would_apply,
        "note": "Dry run. No API call made. Re-invoke with confirm=true to apply.",
    }


def _applied(result: Any) -> dict[str, Any]:
    return {"preview": False, "applied": True, "result": result}


@mcp.tool()
@_auth_guarded
def add_key_event(
    property_id: str,
    event_name: str,
    counting_method: str = "ONCE_PER_EVENT",
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a key event (conversion). Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"event_name": event_name, "counting_method": counting_method})
    return _applied(
        ga4_admin.create_key_event(property_id, event_name, counting_method=counting_method)
    )


@mcp.tool()
@_auth_guarded
def delete_key_event(name: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a key event by full resource name. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"name": name})
    return _applied(ga4_admin.delete_key_event(name))


@mcp.tool()
@_auth_guarded
def create_audience(
    property_id: str, definition: dict[str, Any], confirm: bool = False
) -> dict[str, Any]:
    """Create an audience from a definition dict. Dry-run unless confirm=true."""
    if not confirm:
        return _preview(definition)
    return _applied(ga4_admin.create_audience(property_id, definition))


@mcp.tool()
@_auth_guarded
def archive_audience(audience_name: str, confirm: bool = False) -> dict[str, Any]:
    """Archive an audience by full resource name. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"audience_name": audience_name})
    return _applied(ga4_admin.archive_audience(audience_name))


@mcp.tool()
@_auth_guarded
def add_custom_dimension(
    property_id: str,
    parameter_name: str,
    display_name: str,
    scope: str = "EVENT",
    description: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a custom dimension. Dry-run unless confirm=true."""
    if not confirm:
        return _preview(
            {
                "parameter_name": parameter_name,
                "display_name": display_name,
                "scope": scope,
                "description": description,
            }
        )
    return _applied(
        ga4_admin.create_custom_dimension(
            property_id, parameter_name, display_name, scope, description
        )
    )


@mcp.tool()
@_auth_guarded
def add_custom_metric(
    property_id: str,
    parameter_name: str,
    display_name: str,
    measurement_unit: str,
    scope: str = "EVENT",
    description: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a custom metric. Dry-run unless confirm=true."""
    if not confirm:
        return _preview(
            {
                "parameter_name": parameter_name,
                "display_name": display_name,
                "measurement_unit": measurement_unit,
                "scope": scope,
                "description": description,
            }
        )
    return _applied(
        ga4_admin.create_custom_metric(
            property_id, parameter_name, display_name, measurement_unit, scope, description
        )
    )


@mcp.tool()
@_auth_guarded
def archive_custom_dimension(name: str, confirm: bool = False) -> dict[str, Any]:
    """Archive a custom dimension by full resource name. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"name": name})
    return _applied(ga4_admin.archive_custom_dimension(name))


@mcp.tool()
@_auth_guarded
def archive_custom_metric(name: str, confirm: bool = False) -> dict[str, Any]:
    """Archive a custom metric by full resource name. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"name": name})
    return _applied(ga4_admin.archive_custom_metric(name))


@mcp.tool()
@_auth_guarded
def add_event_edit_rule(
    property_id: str, stream_id: str, definition: dict[str, Any], confirm: bool = False
) -> dict[str, Any]:
    """Create an event edit rule on a data stream. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"stream_id": stream_id, "definition": definition})
    return _applied(ga4_admin.create_event_edit_rule(property_id, stream_id, definition))


@mcp.tool()
@_auth_guarded
def add_event_create_rule(
    property_id: str, stream_id: str, definition: dict[str, Any], confirm: bool = False
) -> dict[str, Any]:
    """Create an event create rule on a data stream. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"stream_id": stream_id, "definition": definition})
    return _applied(ga4_admin.create_event_create_rule(property_id, stream_id, definition))


@mcp.tool()
@_auth_guarded
def delete_event_edit_rule(rule_name: str, confirm: bool = False) -> dict[str, Any]:
    """Delete an event edit rule by full resource name. Dry-run unless confirm=true."""
    if not confirm:
        return _preview({"rule_name": rule_name})
    return _applied(ga4_admin.delete_event_edit_rule(rule_name))


@mcp.tool()
@_auth_guarded
def property_details(property_id: str) -> dict[str, Any]:
    """Fetch the property summary from the Admin API."""
    return ga4_admin.get_property_details(property_id)


@mcp.tool()
@_auth_guarded
def data_streams(property_id: str) -> list[dict[str, Any]]:
    """List the data streams configured on the property."""
    return ga4_admin.list_data_streams(property_id)


@mcp.tool()
@_auth_guarded
def custom_defs(property_id: str) -> dict[str, Any]:
    """List custom dimensions and metrics on the property."""
    return ga4_admin.list_custom_defs(property_id)


@mcp.tool()
@_auth_guarded
def key_events(property_id: str) -> list[dict[str, Any]]:
    """List the key events (conversions) on the property."""
    return ga4_admin.list_key_events(property_id)


@mcp.tool()
@_auth_guarded
def attribution_settings(property_id: str) -> dict[str, Any]:
    """Read the property's attribution settings."""
    return ga4_admin.get_attribution_settings(property_id)


@mcp.tool()
@_auth_guarded
def list_audiences(property_id: str) -> list[dict[str, Any]]:
    """List the audiences on the property."""
    return ga4_admin.list_audiences(property_id)


@mcp.tool()
@_auth_guarded
def list_event_rules(property_id: str, stream_id: str) -> dict[str, Any]:
    """List event edit and create rules for a data stream."""
    return ga4_admin.list_event_rules(property_id, stream_id)


@mcp.tool()
def list_segments() -> list[dict[str, Any]]:
    """List locally stored segment definitions."""
    return ga4_definitions.list_segments()


@mcp.tool()
def list_saved_reports() -> list[dict[str, Any]]:
    """List locally stored custom report definitions."""
    return ga4_definitions.list_report_defs()


@mcp.tool()
@_auth_guarded
def run_saved_report(name: str, property_id: str, days: int | None = None) -> Any:
    """Run a saved custom report definition against a property."""
    return ga4_definitions.run_report_def(name, property_id, days_override=days)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
