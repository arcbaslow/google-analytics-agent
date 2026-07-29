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
import json
import re
import sys
from pathlib import Path

from ga4_auth import get_credentials
from ga4_utils import cache_get, cache_set

_PARAM_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

PARAMETER_NAME_LIMITS = {"EVENT": 40, "USER": 24, "ITEM": 40}
AUDIENCE_DURATION_MAX_DAYS = 540
KEY_EVENT_LIMIT = 30


def _get_admin_client(write: bool = False):
    from google.analytics.admin import AnalyticsAdminServiceClient

    return AnalyticsAdminServiceClient(credentials=get_credentials(write=write))


def _get_admin_alpha_client(write: bool = False):
    from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient as AlphaClient

    return AlphaClient(credentials=get_credentials(write=write))


def _proto_to_dict(msg):
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(msg._pb if hasattr(msg, "_pb") else msg, preserving_proto_field_name=True)


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


# ---------- reads ----------


def get_property_details(property_id):
    cached = cache_get("property_details", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    prop = client.get_property(name=f"properties/{property_id}")
    out = _proto_to_dict(prop)
    cache_set(out, "property_details", property_id)
    return out


def list_data_streams(property_id):
    cached = cache_get("data_streams", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    streams = [
        _proto_to_dict(s) for s in client.list_data_streams(parent=f"properties/{property_id}")
    ]
    cache_set(streams, "data_streams", property_id)
    return streams


def get_enhanced_measurement(property_id):
    cached = cache_get("enhanced_measurement", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    results = []
    for s in client.list_data_streams(parent=f"properties/{property_id}"):
        stream_d = _proto_to_dict(s)
        if "webStreamData" in stream_d or stream_d.get("type_") == "WEB_DATA_STREAM":
            try:
                em = client.get_enhanced_measurement_settings(
                    name=f"{s.name}/enhancedMeasurementSettings"
                )
                stream_d["enhanced_measurement"] = _proto_to_dict(em)
            except Exception as e:
                stream_d["enhanced_measurement_error"] = str(e)
        results.append(stream_d)
    cache_set(results, "enhanced_measurement", property_id)
    return results


def list_data_filters(property_id):
    cached = cache_get("data_filters", property_id)
    if cached:
        return cached
    client = _get_admin_alpha_client()
    try:
        filters = [
            _proto_to_dict(f) for f in client.list_data_filters(parent=f"properties/{property_id}")
        ]
    except Exception as e:
        filters = [{"error": str(e)}]
    cache_set(filters, "data_filters", property_id)
    return filters


def list_custom_defs(property_id):
    cached = cache_get("custom_defs", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    dims = [
        _proto_to_dict(d) for d in client.list_custom_dimensions(parent=f"properties/{property_id}")
    ]
    mets = [
        _proto_to_dict(m) for m in client.list_custom_metrics(parent=f"properties/{property_id}")
    ]
    out = {"custom_dimensions": dims, "custom_metrics": mets}
    cache_set(out, "custom_defs", property_id)
    return out


def list_key_events(property_id):
    cached = cache_get("key_events", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    events = []
    if hasattr(client, "list_key_events"):
        for e in client.list_key_events(parent=f"properties/{property_id}"):
            events.append(_proto_to_dict(e))
    else:
        for e in client.list_conversion_events(parent=f"properties/{property_id}"):
            events.append(_proto_to_dict(e))
    cache_set(events, "key_events", property_id)
    return events


def get_attribution_settings(property_id):
    cached = cache_get("attribution_settings", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    try:
        att = client.get_attribution_settings(name=f"properties/{property_id}/attributionSettings")
        out = _proto_to_dict(att)
    except Exception as e:
        out = {"error": str(e)}
    cache_set(out, "attribution_settings", property_id)
    return out


def list_platform_links(property_id):
    cached = cache_get("platform_links", property_id)
    if cached:
        return cached
    client = _get_admin_client()
    alpha = _get_admin_alpha_client()
    out = {}

    def _try(name, fn):
        try:
            out[name] = [_proto_to_dict(x) for x in fn()]
        except Exception as e:
            out[name] = [{"error": str(e)}]

    _try(
        "google_ads_links", lambda: client.list_google_ads_links(parent=f"properties/{property_id}")
    )
    _try(
        "search_ads_360_links",
        lambda: client.list_search_ads360_links(parent=f"properties/{property_id}"),
    )
    _try(
        "display_video_360_advertiser_links",
        lambda: client.list_display_video360_advertiser_links(parent=f"properties/{property_id}"),
    )
    _try("bigquery_links", lambda: alpha.list_big_query_links(parent=f"properties/{property_id}"))
    _try(
        "search_console_links",
        lambda: alpha.list_search_console_links(parent=f"properties/{property_id}"),
    )

    cache_set(out, "platform_links", property_id)
    return out


# ---------- event create / edit rules (v1alpha, per data stream) ----------


def list_event_rules(property_id, stream_id):
    """List both edit rules and create rules for one data stream."""
    client = _get_admin_alpha_client()
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    edits = [_proto_to_dict(r) for r in client.list_event_edit_rules(parent=parent)]
    creates = [_proto_to_dict(r) for r in client.list_event_create_rules(parent=parent)]
    return {"edit_rules": edits, "create_rules": creates}


def create_event_edit_rule(property_id, stream_id, definition):
    from google.analytics.admin_v1alpha.types import EventEditRule

    client = _get_admin_alpha_client(write=True)
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    rule = _dict_to_proto(definition, EventEditRule)
    created = client.create_event_edit_rule(parent=parent, event_edit_rule=rule)
    return _proto_to_dict(created)


def update_event_edit_rule(rule_name, definition):
    from google.analytics.admin_v1alpha.types import EventEditRule
    from google.protobuf.field_mask_pb2 import FieldMask

    client = _get_admin_alpha_client(write=True)
    rule = _dict_to_proto({**definition, "name": rule_name}, EventEditRule)
    mask = FieldMask(paths=list(definition.keys()))
    updated = client.update_event_edit_rule(event_edit_rule=rule, update_mask=mask)
    return _proto_to_dict(updated)


def delete_event_edit_rule(rule_name):
    client = _get_admin_alpha_client(write=True)
    client.delete_event_edit_rule(name=rule_name)
    return {"status": "deleted", "name": rule_name}


def reorder_event_edit_rules(property_id, stream_id, ordered_names):
    client = _get_admin_alpha_client(write=True)
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    client.reorder_event_edit_rules(parent=parent, event_edit_rules=list(ordered_names))
    return {"status": "reordered", "count": len(ordered_names)}


def create_event_create_rule(property_id, stream_id, definition):
    from google.analytics.admin_v1alpha.types import EventCreateRule

    client = _get_admin_alpha_client(write=True)
    parent = f"properties/{property_id}/dataStreams/{stream_id}"
    rule = _dict_to_proto(definition, EventCreateRule)
    created = client.create_event_create_rule(parent=parent, event_create_rule=rule)
    return _proto_to_dict(created)


def delete_event_create_rule(rule_name):
    client = _get_admin_alpha_client(write=True)
    client.delete_event_create_rule(name=rule_name)
    return {"status": "deleted", "name": rule_name}


# ---------- audiences (v1alpha) ----------


def list_audiences(property_id):
    client = _get_admin_alpha_client()
    return [_proto_to_dict(a) for a in client.list_audiences(parent=f"properties/{property_id}")]


def get_audience(audience_name):
    client = _get_admin_alpha_client()
    return _proto_to_dict(client.get_audience(name=audience_name))


def create_audience(property_id, definition):
    from google.analytics.admin_v1alpha.types import Audience

    if definition.get("membership_duration_days", 0) > AUDIENCE_DURATION_MAX_DAYS:
        raise ValueError(f"membership_duration_days must be <= {AUDIENCE_DURATION_MAX_DAYS}")
    client = _get_admin_alpha_client(write=True)
    audience = _dict_to_proto(definition, Audience)
    created = client.create_audience(parent=f"properties/{property_id}", audience=audience)
    return _proto_to_dict(created)


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
    return _proto_to_dict(updated)


def archive_audience(audience_name):
    client = _get_admin_alpha_client(write=True)
    # archive_audience is not a flattened method; it takes a request object.
    client.archive_audience(request={"name": audience_name})
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


def create_custom_dimension(property_id, parameter_name, display_name, scope, description=""):
    from google.analytics.admin_v1beta.types import CustomDimension

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
    return _proto_to_dict(created)


def archive_custom_dimension(name):
    client = _get_admin_client(write=True)
    client.archive_custom_dimension(name=name)
    return {"status": "archived", "name": name}


def create_custom_metric(
    property_id, parameter_name, display_name, measurement_unit, scope="EVENT", description=""
):
    from google.analytics.admin_v1beta.types import CustomMetric

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
    return _proto_to_dict(created)


def archive_custom_metric(name):
    client = _get_admin_client(write=True)
    client.archive_custom_metric(name=name)
    return {"status": "archived", "name": name}


# ---------- key events (v1beta) ----------


def create_key_event(property_id, event_name, counting_method="ONCE_PER_EVENT"):
    from google.analytics.admin_v1beta.types import KeyEvent

    existing = list_key_events(property_id)
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
    return _proto_to_dict(created)


def delete_key_event(name):
    client = _get_admin_client(write=True)
    client.delete_key_event(name=name)
    return {"status": "deleted", "name": name}


# ---------- CLI ----------


def main():
    parser = argparse.ArgumentParser(description="GA4 Admin API wrapper")
    parser.add_argument("--property")
    parser.add_argument("--stream", help="Data stream ID (for event rule commands)")

    # reads
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--streams", action="store_true")
    parser.add_argument("--enhanced-measurement", action="store_true")
    parser.add_argument("--data-filters", action="store_true")
    parser.add_argument("--custom-defs", action="store_true")
    parser.add_argument("--key-events", action="store_true")
    parser.add_argument("--attribution-settings", action="store_true")
    parser.add_argument("--links", action="store_true")
    parser.add_argument("--list-event-rules", action="store_true")
    parser.add_argument("--list-audiences", action="store_true")

    # writes
    parser.add_argument("--add-edit-rule", metavar="JSON_PATH")
    parser.add_argument("--add-create-rule", metavar="JSON_PATH")
    parser.add_argument("--rule-name", help="Full resource name for --delete-rule")
    parser.add_argument("--delete-edit-rule", action="store_true")
    parser.add_argument("--delete-create-rule", action="store_true")
    parser.add_argument("--create-audience", metavar="JSON_PATH")
    parser.add_argument("--audience-name", help="Full resource name for audience ops")
    parser.add_argument("--archive-audience", action="store_true")
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
    parser.add_argument("--archive-custom-dim", metavar="NAME")
    parser.add_argument("--archive-custom-metric", metavar="NAME")
    parser.add_argument("--add-key-event", metavar="EVENT_NAME")
    parser.add_argument("--counting-method", default="ONCE_PER_EVENT")
    parser.add_argument("--delete-key-event", metavar="NAME")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        out = _dispatch(args)
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1

    if out is None:
        parser.print_help()
        return 1
    print(json.dumps(out, indent=2, default=str))
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
