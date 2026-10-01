"""GA4 Admin API wrapper. Each CLI flag maps to one Admin API call.

Read surfaces (v1beta + v1alpha):
  property details, data streams, enhanced measurement, data filters,
  custom dimensions/metrics, key events, attribution settings, platform links,
  event create/edit rules, audiences.

Write surfaces (require analytics.edit scope):
  event create/edit rules, audiences, custom dimensions/metrics, key events.
"""

from __future__ import annotations

import argparse
import copy
import functools
import inspect
import json
import re
import sys
from pathlib import Path

from ga4_auth import get_credentials
from ga4_transport import error_result, read_call, read_list, read_operation
from ga4_utils import (
    cache_get,
    cache_invalidate,
    cache_namespace,
    cache_set,
    scrub_pii,
    scrub_response,
)

_PARAM_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_PROPERTY_IN_NAME_RE = re.compile(r"^properties/([^/]+)/")

PARAMETER_NAME_LIMITS = {"EVENT": 40, "USER": 24, "ITEM": 40}
AUDIENCE_DURATION_MAX_DAYS = 540
KEY_EVENT_LIMIT = 30


class ConfirmationRequiredError(RuntimeError):
    """No interactive approval was supplied for this one proposed write."""


def _confirmed_write(fn):
    """Gate direct imports as well as the CLI. Never consume MCP's stdin pipe."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        bound = inspect.signature(fn).bind(*args, **kwargs)
        bound.apply_defaults()
        bound.arguments = copy.deepcopy(bound.arguments)
        proposal = {"operation": fn.__name__, "arguments": bound.arguments}
        print(json.dumps(scrub_pii(proposal), indent=2, default=str), file=sys.stderr)
        print("Apply this change? [y/N]", file=sys.stderr, flush=True)
        if not sys.stdin.isatty():
            raise ConfirmationRequiredError(
                "Use an interactive terminal to review and approve this write."
            )
        try:
            approved = input().strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            approved = False
        if not approved:
            raise ConfirmationRequiredError("Write cancelled; no API call made.")
        return fn(*bound.args, **bound.kwargs)

    return wrapper


def _get_admin_client(write: bool = False):
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient

    return AnalyticsAdminServiceClient(credentials=get_credentials(write=write))


def _get_admin_alpha_client(write: bool = False):
    from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient as AlphaClient

    return AlphaClient(credentials=get_credentials(write=write))


def _admin_type(name: str):
    """Use the explicit beta surface for both the client and its message types.

    Alpha and beta messages with identical field names are distinct classes;
    mixing them fails when GAPIC builds the request.
    """
    from google.analytics import admin_v1beta

    return getattr(admin_v1beta.types, name)


def _proto_to_dict(msg):
    from google.protobuf.json_format import MessageToDict

    return scrub_pii(
        MessageToDict(msg._pb if hasattr(msg, "_pb") else msg, preserving_proto_field_name=True)
    )


def _dict_to_proto(d, proto_cls):
    """Reverse of _proto_to_dict. Used to load JSON definitions from disk.

    The Admin API types are proto-plus wrappers. json_format.ParseDict cannot
    populate a proto-plus message directly — it probes for a DESCRIPTOR
    attribute the wrapper does not expose and raises
    "Unknown field ... DESCRIPTOR". Parse into the underlying protobuf message
    obtained via proto_cls.pb(...) and wrap the result back into the proto-plus
    type. Accepts both camelCase and snake_case keys and ignores unknown
    fields, matching the previous call's semantics."""
    from google.protobuf.json_format import ParseDict

    pb = ParseDict(d, proto_cls.pb(proto_cls()), ignore_unknown_fields=True)
    return proto_cls.wrap(pb)


def _read_json_file(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _invalidate_for_name(read, name):
    """Delete/archive writes only get a resource name such as
    `properties/123/keyEvents/456`; drop the cached `read` for its property."""
    match = _PROPERTY_IN_NAME_RE.match(name)
    if match:
        cache_invalidate(read, match.group(1))


# ---------- reads ----------


@scrub_response
@read_operation
def get_property_details(property_id):
    client = _get_admin_client()
    namespace = cache_namespace(client)
    cached = cache_get("property_details", property_id, namespace=namespace)
    if cached is not None:
        return cached
    prop = read_call(client.get_property, name=f"properties/{property_id}")
    out = _proto_to_dict(prop)
    cache_set(out, "property_details", property_id, namespace=namespace)
    return out


@scrub_response
@read_operation
def list_data_streams(property_id):
    client = _get_admin_client()
    namespace = cache_namespace(client)
    cached = cache_get("data_streams", property_id, namespace=namespace)
    if cached is not None:
        return cached
    streams = [
        _proto_to_dict(s)
        for s in read_list(client.list_data_streams, parent=f"properties/{property_id}")
    ]
    cache_set(streams, "data_streams", property_id, namespace=namespace)
    return streams


@scrub_response
@read_operation
def get_enhanced_measurement(property_id):
    client = _get_admin_alpha_client()
    namespace = cache_namespace(client)
    cached = cache_get("enhanced_measurement", property_id, namespace=namespace)
    if cached is not None:
        return cached
    results = []
    for s in read_list(client.list_data_streams, parent=f"properties/{property_id}"):
        stream_d = _proto_to_dict(s)
        if (
            "web_stream_data" in stream_d
            or "webStreamData" in stream_d
            or stream_d.get("type", stream_d.get("type_")) == "WEB_DATA_STREAM"
        ):
            try:
                em = read_call(
                    client.get_enhanced_measurement_settings,
                    name=f"{s.name}/enhancedMeasurementSettings",
                )
                stream_d["enhanced_measurement"] = _proto_to_dict(em)
            except Exception as e:
                stream_d["enhanced_measurement_error"] = error_result(e)
        results.append(stream_d)
    cache_set(results, "enhanced_measurement", property_id, namespace=namespace)
    return results


@scrub_response
@read_operation
def list_data_filters(property_id):
    """No public Admin API method exists for property data filters."""
    return [
        {
            "status": "unsupported",
            "property_id": property_id,
            "reason": "Data filters are not exposed by the public Admin API; inspect them in GA4 Admin.",
        }
    ]


@scrub_response
@read_operation
def list_custom_defs(property_id):
    client = _get_admin_client()
    namespace = cache_namespace(client)
    cached = cache_get("custom_defs", property_id, namespace=namespace)
    if cached is not None:
        return cached
    dims = [
        _proto_to_dict(d)
        for d in read_list(client.list_custom_dimensions, parent=f"properties/{property_id}")
    ]
    mets = [
        _proto_to_dict(m)
        for m in read_list(client.list_custom_metrics, parent=f"properties/{property_id}")
    ]
    out = {"custom_dimensions": dims, "custom_metrics": mets}
    cache_set(out, "custom_defs", property_id, namespace=namespace)
    return out


@scrub_response
@read_operation
def list_key_events(property_id, use_cache=True):
    client = _get_admin_client()
    namespace = cache_namespace(client)
    cached = cache_get("key_events", property_id, namespace=namespace) if use_cache else None
    if cached is not None:
        return cached
    events = []
    if hasattr(client, "list_key_events"):
        for e in read_list(client.list_key_events, parent=f"properties/{property_id}"):
            events.append(_proto_to_dict(e))
    else:
        for e in read_list(client.list_conversion_events, parent=f"properties/{property_id}"):
            events.append(_proto_to_dict(e))
    if use_cache:
        cache_set(events, "key_events", property_id, namespace=namespace)
    return events


@scrub_response
@read_operation
def get_attribution_settings(property_id):
    client = _get_admin_alpha_client()
    namespace = cache_namespace(client)
    cached = cache_get("attribution_settings", property_id, namespace=namespace)
    if cached is not None:
        return cached
    try:
        att = read_call(
            client.get_attribution_settings, name=f"properties/{property_id}/attributionSettings"
        )
        out = _proto_to_dict(att)
    except Exception as e:
        out = error_result(e)
    cache_set(out, "attribution_settings", property_id, namespace=namespace)
    return out


@scrub_response
@read_operation
def list_platform_links(property_id):
    client = _get_admin_client()
    namespace = cache_namespace(client)
    cached = cache_get("platform_links", property_id, namespace=namespace)
    if cached is not None:
        return cached
    alpha = _get_admin_alpha_client()
    out = {}

    def _try(name, fn):
        try:
            out[name] = [_proto_to_dict(x) for x in fn()]
        except Exception as e:
            out[name] = [error_result(e)]

    _try(
        "google_ads_links",
        lambda: read_list(client.list_google_ads_links, parent=f"properties/{property_id}"),
    )
    _try(
        "search_ads_360_links",
        lambda: read_list(alpha.list_search_ads360_links, parent=f"properties/{property_id}"),
    )
    _try(
        "display_video_360_advertiser_links",
        lambda: read_list(
            alpha.list_display_video360_advertiser_links, parent=f"properties/{property_id}"
        ),
    )
    _try(
        "bigquery_links",
        lambda: read_list(alpha.list_big_query_links, parent=f"properties/{property_id}"),
    )
    out["search_console_links"] = [
        {
            "status": "unsupported",
            "reason": "Search Console links are not exposed by the public Admin API; inspect them in GA4 Admin.",
        }
    ]

    cache_set(out, "platform_links", property_id, namespace=namespace)
    return out


@scrub_response
@read_operation
def get_data_retention_settings(property_id):
    """Retention is a separate resource, not a field on Property."""
    client = _get_admin_client()
    namespace = cache_namespace(client)
    cached = cache_get("data_retention_settings", property_id, namespace=namespace)
    if cached is not None:
        return cached
    out = _proto_to_dict(
        read_call(
            client.get_data_retention_settings,
            name=f"properties/{property_id}/dataRetentionSettings",
        )
    )
    cache_set(out, "data_retention_settings", property_id, namespace=namespace)
    return out


@scrub_response
@read_operation
def get_reporting_identity_settings(property_id):
    """Read the selected identity. Older SDKs may not expose this alpha method."""
    client = _get_admin_alpha_client()
    namespace = cache_namespace(client)
    cached = cache_get("reporting_identity_settings", property_id, namespace=namespace)
    if cached is not None:
        return cached
    if not hasattr(client, "get_reporting_identity_settings"):
        return {
            "status": "unsupported",
            "reason": "Installed Admin client does not expose getReportingIdentitySettings.",
        }
    out = _proto_to_dict(
        read_call(
            client.get_reporting_identity_settings,
            name=f"properties/{property_id}/reportingIdentitySettings",
        )
    )
    cache_set(out, "reporting_identity_settings", property_id, namespace=namespace)
    return out


# ---------- event create / edit rules (v1alpha, per data stream) ----------


@scrub_response
@read_operation
def get_user_provided_data_settings(property_id):
    """Property configuration only; this does not observe event-level consent."""
    client = _get_admin_alpha_client()
    if not hasattr(client, "get_user_provided_data_settings"):
        return {
            "status": "unsupported",
            "reason": "Installed Admin client lacks user-provided-data settings.",
        }
    namespace = cache_namespace(client)
    cached = cache_get("user_provided_data_settings", property_id, namespace=namespace)
    if cached is not None:
        return cached
    response = read_call(
        client.get_user_provided_data_settings,
        name=f"properties/{property_id}/userProvidedDataSettings",
    )
    out = _proto_to_dict(response)
    for field in (
        "user_provided_data_collection_enabled",
        "automatically_detected_data_collection_enabled",
    ):
        out[field] = bool(getattr(response, field))
    cache_set(out, "user_provided_data_settings", property_id, namespace=namespace)
    return out


@scrub_response
@read_operation
def get_consent_diagnostics(property_id):
    """Separate API-observable settings from evidence requiring tag/export review."""
    settings = {}
    for name, reader in (
        ("user_provided_data", get_user_provided_data_settings),
        ("reporting_identity", get_reporting_identity_settings),
    ):
        try:
            settings[name] = reader(property_id)
        except Exception as exc:
            settings[name] = error_result(exc)
    return {
        "property_id": property_id,
        "settings": settings,
        "event_consent_status": "not_observed",
        "manual_evidence_required": [
            "Inspect consent defaults and updates for analytics_storage, ad_storage, ad_user_data and ad_personalization in the tag/CMP configuration.",
            "Compare granted, denied and unset privacy_info aggregates in BigQuery where an export is available.",
            "Review user-provided-data collection configuration separately; an enabled property setting does not prove event consent or legal compliance.",
            "Reporting identity selects how users are counted; it is not evidence of consent or complete modeling.",
        ],
    }


@scrub_response
@read_operation
def list_event_rules(property_id, stream_id):
    """List both edit rules and create rules for one data stream. Not cached;
    caching it would require the rule writes below to invalidate it."""
    client = _get_admin_alpha_client()
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    edits = [_proto_to_dict(r) for r in read_list(client.list_event_edit_rules, parent=parent)]
    creates = [_proto_to_dict(r) for r in read_list(client.list_event_create_rules, parent=parent)]
    return {"edit_rules": edits, "create_rules": creates}


@_confirmed_write
@scrub_response
@read_operation
def create_event_edit_rule(property_id, stream_id, definition):
    from google.analytics.admin_v1alpha.types import EventEditRule

    client = _get_admin_alpha_client(write=True)
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    rule = _dict_to_proto(definition, EventEditRule)
    created = client.create_event_edit_rule(parent=parent, event_edit_rule=rule)
    cache_invalidate("property", property_id)
    return _proto_to_dict(created)


@_confirmed_write
@scrub_response
@read_operation
def update_event_edit_rule(rule_name, definition):
    from google.analytics.admin_v1alpha.types import EventEditRule
    from google.protobuf.field_mask_pb2 import FieldMask

    client = _get_admin_alpha_client(write=True)
    rule = _dict_to_proto({**definition, "name": rule_name}, EventEditRule)
    mask = FieldMask(paths=list(definition.keys()))
    updated = client.update_event_edit_rule(event_edit_rule=rule, update_mask=mask)
    _invalidate_for_name("property", rule_name)
    return _proto_to_dict(updated)


@_confirmed_write
@scrub_response
@read_operation
def delete_event_edit_rule(rule_name):
    client = _get_admin_alpha_client(write=True)
    client.delete_event_edit_rule(name=rule_name)
    _invalidate_for_name("property", rule_name)
    return {"status": "deleted", "name": rule_name}


@_confirmed_write
@scrub_response
@read_operation
def reorder_event_edit_rules(property_id, stream_id, ordered_names):
    client = _get_admin_alpha_client(write=True)
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    client.reorder_event_edit_rules(parent=parent, event_edit_rules=list(ordered_names))
    cache_invalidate("property", property_id)
    return {"status": "reordered", "count": len(ordered_names)}


@_confirmed_write
@scrub_response
@read_operation
def create_event_create_rule(property_id, stream_id, definition):
    from google.analytics.admin_v1alpha.types import EventCreateRule

    client = _get_admin_alpha_client(write=True)
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    rule = _dict_to_proto(definition, EventCreateRule)
    created = client.create_event_create_rule(parent=parent, event_create_rule=rule)
    cache_invalidate("property", property_id)
    return _proto_to_dict(created)


@_confirmed_write
@scrub_response
@read_operation
def delete_event_create_rule(rule_name):
    client = _get_admin_alpha_client(write=True)
    client.delete_event_create_rule(name=rule_name)
    _invalidate_for_name("property", rule_name)
    return {"status": "deleted", "name": rule_name}


# ---------- audiences (v1alpha) ----------


@scrub_response
@read_operation
def list_audiences(property_id):
    """Not cached; caching it would require the audience writes below to
    invalidate it."""
    client = _get_admin_alpha_client()
    return [
        _proto_to_dict(a)
        for a in read_list(client.list_audiences, parent=f"properties/{property_id}")
    ]


@scrub_response
@read_operation
def get_audience(audience_name):
    client = _get_admin_alpha_client()
    return _proto_to_dict(read_call(client.get_audience, name=audience_name))


@_confirmed_write
@scrub_response
@read_operation
def create_audience(property_id, definition):
    from google.analytics.admin_v1alpha.types import Audience

    if definition.get("membership_duration_days", 0) > AUDIENCE_DURATION_MAX_DAYS:
        raise ValueError(f"membership_duration_days must be <= {AUDIENCE_DURATION_MAX_DAYS}")
    client = _get_admin_alpha_client(write=True)
    audience = _dict_to_proto(definition, Audience)
    created = client.create_audience(parent=f"properties/{property_id}", audience=audience)
    cache_invalidate("property", property_id)
    return _proto_to_dict(created)


@_confirmed_write
@scrub_response
@read_operation
def update_audience_metadata(audience_name, display_name=None, description=None):
    """Only display_name and description are mutable post-create. Filter clauses
    cannot be edited — archive and recreate to change them."""
    from google.analytics.admin_v1alpha.types import Audience
    from google.protobuf.field_mask_pb2 import FieldMask

    fields = {}
    if display_name is not None:
        fields["display_name"] = display_name
    if description is not None:
        fields["description"] = description
    if not fields:
        raise ValueError("at least one of display_name/description must be set")
    client = _get_admin_alpha_client(write=True)
    audience = _dict_to_proto({**fields, "name": audience_name}, Audience)
    mask = FieldMask(paths=list(fields.keys()))
    updated = client.update_audience(audience=audience, update_mask=mask)
    _invalidate_for_name("property", audience_name)
    return _proto_to_dict(updated)


@_confirmed_write
@scrub_response
@read_operation
def archive_audience(audience_name):
    client = _get_admin_alpha_client(write=True)
    # archive_audience is not a flattened method; it takes a request object.
    client.archive_audience(request={"name": audience_name})
    _invalidate_for_name("property", audience_name)
    return {"status": "archived", "name": audience_name}


# ---------- custom dimensions / metrics (v1beta) ----------


def _validate_parameter_name(parameter_name, scope):
    if not _PARAM_NAME_RE.match(parameter_name):
        raise ValueError(
            f"parameter_name {parameter_name!r} must start with a letter and "
            "contain only letters, digits, underscores"
        )
    limit = PARAMETER_NAME_LIMITS.get(scope.upper())
    if not limit:
        raise ValueError(f"unknown scope {scope!r}; expected EVENT, USER, or ITEM")
    if len(parameter_name) > limit:
        raise ValueError(
            f"parameter_name length {len(parameter_name)} exceeds {limit} for scope {scope}"
        )


@_confirmed_write
@scrub_response
@read_operation
def create_custom_dimension(property_id, parameter_name, display_name, scope, description=""):
    CustomDimension = _admin_type("CustomDimension")

    _validate_parameter_name(parameter_name, scope)
    client = _get_admin_client(write=True)
    dim = CustomDimension(
        parameter_name=parameter_name,
        display_name=display_name,
        description=description,
        scope=CustomDimension.DimensionScope[scope.upper()],
    )
    created = client.create_custom_dimension(
        parent=f"properties/{property_id}", custom_dimension=dim
    )
    cache_invalidate("custom_defs", property_id)
    cache_invalidate("report_metadata", property_id)
    return _proto_to_dict(created)


@_confirmed_write
@scrub_response
@read_operation
def archive_custom_dimension(name):
    client = _get_admin_client(write=True)
    client.archive_custom_dimension(name=name)
    _invalidate_for_name("custom_defs", name)
    _invalidate_for_name("report_metadata", name)
    return {"status": "archived", "name": name}


@_confirmed_write
@scrub_response
@read_operation
def create_custom_metric(
    property_id, parameter_name, display_name, measurement_unit, scope="EVENT", description=""
):
    CustomMetric = _admin_type("CustomMetric")

    _validate_parameter_name(parameter_name, scope)
    client = _get_admin_client(write=True)
    metric = CustomMetric(
        parameter_name=parameter_name,
        display_name=display_name,
        description=description,
        measurement_unit=CustomMetric.MeasurementUnit[measurement_unit.upper()],
        scope=CustomMetric.MetricScope[scope.upper()],
    )
    created = client.create_custom_metric(parent=f"properties/{property_id}", custom_metric=metric)
    cache_invalidate("custom_defs", property_id)
    cache_invalidate("report_metadata", property_id)
    return _proto_to_dict(created)


@_confirmed_write
@scrub_response
@read_operation
def archive_custom_metric(name):
    client = _get_admin_client(write=True)
    client.archive_custom_metric(name=name)
    _invalidate_for_name("custom_defs", name)
    _invalidate_for_name("report_metadata", name)
    return {"status": "archived", "name": name}


# ---------- key events (v1beta) ----------


@_confirmed_write
@scrub_response
@read_operation
def create_key_event(property_id, event_name, counting_method="ONCE_PER_EVENT"):
    KeyEvent = _admin_type("KeyEvent")

    # Count against the live list. A cached one can predate a delete made
    # elsewhere (GA4 UI, another host) and block a create that fits the limit.
    existing = list_key_events(property_id, use_cache=False)
    if len(existing) >= KEY_EVENT_LIMIT:
        raise ValueError(
            f"property already has {len(existing)} key events (limit {KEY_EVENT_LIMIT}); "
            "delete one before creating another"
        )
    client = _get_admin_client(write=True)
    ke = KeyEvent(
        event_name=event_name,
        counting_method=KeyEvent.CountingMethod[counting_method.upper()],
    )
    created = client.create_key_event(parent=f"properties/{property_id}", key_event=ke)
    cache_invalidate("key_events", property_id)
    cache_invalidate("report_metadata", property_id)
    return _proto_to_dict(created)


@_confirmed_write
@scrub_response
@read_operation
def delete_key_event(name):
    client = _get_admin_client(write=True)
    client.delete_key_event(name=name)
    _invalidate_for_name("key_events", name)
    _invalidate_for_name("report_metadata", name)
    return {"status": "deleted", "name": name}


# ---------- CLI ----------


def main():
    parser = argparse.ArgumentParser(description="GA4 Admin API wrapper")
    parser.add_argument("--property")
    parser.add_argument("--stream", help="Data stream ID (for event rule commands)")

    actions = parser.add_mutually_exclusive_group()

    # reads
    actions.add_argument("--details", action="store_true")
    actions.add_argument("--streams", action="store_true")
    actions.add_argument("--enhanced-measurement", action="store_true")
    actions.add_argument("--data-filters", action="store_true")
    actions.add_argument("--custom-defs", action="store_true")
    actions.add_argument("--key-events", action="store_true")
    actions.add_argument("--attribution-settings", action="store_true")
    actions.add_argument("--reporting-identity", action="store_true")
    actions.add_argument("--user-provided-data", action="store_true")
    actions.add_argument("--consent-diagnostics", action="store_true")
    actions.add_argument("--links", action="store_true")
    actions.add_argument("--list-event-rules", action="store_true")
    actions.add_argument("--list-audiences", action="store_true")

    # writes
    actions.add_argument("--add-edit-rule", metavar="JSON_PATH")
    actions.add_argument("--add-create-rule", metavar="JSON_PATH")
    parser.add_argument("--rule-name", help="Full resource name for --delete-rule")
    actions.add_argument("--delete-edit-rule", action="store_true")
    actions.add_argument("--delete-create-rule", action="store_true")
    actions.add_argument("--create-audience", metavar="JSON_PATH")
    parser.add_argument("--audience-name", help="Full resource name for audience ops")
    actions.add_argument("--archive-audience", action="store_true")
    parser.add_argument(
        "--add-custom-dim",
        action="store_true",
        help="needs --parameter-name --display-name --scope",
    )
    parser.add_argument(
        "--add-custom-metric",
        action="store_true",
        help="needs --parameter-name --display-name --measurement-unit",
    )
    parser.add_argument("--parameter-name")
    parser.add_argument("--display-name")
    parser.add_argument("--scope", default="EVENT")
    parser.add_argument("--measurement-unit")
    parser.add_argument("--description", default="")
    actions.add_argument("--archive-custom-dim", metavar="NAME")
    actions.add_argument("--archive-custom-metric", metavar="NAME")
    actions.add_argument("--add-key-event", metavar="EVENT_NAME")
    parser.add_argument("--counting-method", default="ONCE_PER_EVENT")
    actions.add_argument("--delete-key-event", metavar="NAME")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        out = _dispatch(args)
    except Exception as e:
        print(json.dumps(error_result(e)), file=sys.stderr)
        return 1

    if out is None:
        parser.print_help()
        return 1
    print(json.dumps(scrub_pii(out), indent=2, default=str))
    return 0


def _dispatch(args):
    if args.details:
        return get_property_details(args.property)
    if args.streams:
        return list_data_streams(args.property)
    if args.enhanced_measurement:
        return get_enhanced_measurement(args.property)
    if args.data_filters:
        return list_data_filters(args.property)
    if args.custom_defs:
        return list_custom_defs(args.property)
    if args.key_events:
        return list_key_events(args.property)
    if args.attribution_settings:
        return get_attribution_settings(args.property)
    if args.reporting_identity:
        return get_reporting_identity_settings(args.property)
    if args.user_provided_data:
        return get_user_provided_data_settings(args.property)
    if args.consent_diagnostics:
        return get_consent_diagnostics(args.property)
    if args.links:
        return list_platform_links(args.property)
    if args.list_event_rules:
        return list_event_rules(args.property, args.stream)
    if args.list_audiences:
        return list_audiences(args.property)
    if args.add_edit_rule:
        return create_event_edit_rule(
            args.property, args.stream, _read_json_file(args.add_edit_rule)
        )
    if args.add_create_rule:
        return create_event_create_rule(
            args.property, args.stream, _read_json_file(args.add_create_rule)
        )
    if args.delete_edit_rule:
        return delete_event_edit_rule(args.rule_name)
    if args.delete_create_rule:
        return delete_event_create_rule(args.rule_name)
    if args.create_audience:
        return create_audience(args.property, _read_json_file(args.create_audience))
    if args.archive_audience:
        return archive_audience(args.audience_name)
    if args.add_custom_dim:
        return create_custom_dimension(
            args.property, args.parameter_name, args.display_name, args.scope, args.description
        )
    if args.archive_custom_dim:
        return archive_custom_dimension(args.archive_custom_dim)
    if args.add_custom_metric:
        return create_custom_metric(
            args.property,
            args.parameter_name,
            args.display_name,
            args.measurement_unit,
            args.scope,
            args.description,
        )
    if args.archive_custom_metric:
        return archive_custom_metric(args.archive_custom_metric)
    if args.add_key_event:
        return create_key_event(args.property, args.add_key_event, args.counting_method)
    if args.delete_key_event:
        return delete_key_event(args.delete_key_event)
    return None


if __name__ == "__main__":
    sys.exit(main())
