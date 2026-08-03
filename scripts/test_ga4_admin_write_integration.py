"""Integration tests for the ga4_admin write path.

The existing test_ga4_admin_write.py mocks _dict_to_proto / _proto_to_dict and
patches sys.modules so the proto layer never actually runs. These tests do the
opposite: they exercise the *real* proto-plus types end to end. Only the gRPC
client is mocked. For each write op we:

  1. pass a plain definition dict (what a user JSON file holds),
  2. let the real _dict_to_proto / type constructor build the request proto,
  3. hand back a recorded API response (camelCase wire JSON under
     fixtures/admin_api/, loaded into the real proto-plus type), and
  4. assert both the request the client received and the parsed response.

This is what catches proto-schema regressions. _dict_to_proto used to call
json_format.ParseDict directly on a proto-plus message, which raises
"Unknown field ... DESCRIPTOR" — a bug invisible to the mocked unit tests
because they stubbed that function out. test_dict_to_proto_parses_real_type
locks the fix in.
"""

from pathlib import Path
from unittest.mock import MagicMock

import ga4_admin
from google.analytics.admin_v1alpha.types import Audience, EventCreateRule, EventEditRule
from google.analytics.admin_v1beta.types import CustomDimension, CustomMetric, KeyEvent

FIXTURES = Path(__file__).parent / "fixtures" / "admin_api"


def _load(proto_cls, name):
    return proto_cls.from_json((FIXTURES / name).read_text(encoding="utf-8"))


def _alpha(monkeypatch, method, response):
    client = MagicMock()
    getattr(client, method).return_value = response
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: client)
    return client


def _beta(monkeypatch, method, response):
    client = MagicMock()
    getattr(client, method).return_value = response
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    return client


# ---------- the bug fix, isolated ----------


def test_dict_to_proto_parses_real_proto_plus_type():
    """Regression: _dict_to_proto must populate a real proto-plus Admin type.

    Pre-fix this raised AttributeError("Unknown field ... DESCRIPTOR") because
    json_format.ParseDict cannot target a proto-plus wrapper directly."""
    rule = ga4_admin._dict_to_proto(
        {
            "display_name": "Normalize purchase",
            "event_conditions": [
                {"field": "event_name", "comparison_type": "EQUALS", "value": "purchase"}
            ],
        },
        EventEditRule,
    )
    parsed = ga4_admin._proto_to_dict(rule)
    assert parsed["display_name"] == "Normalize purchase"
    assert parsed["event_conditions"][0]["value"] == "purchase"


def test_dict_to_proto_accepts_camelcase_and_drops_unknown_fields():
    """ParseDict tolerates camelCase JSON (Google's docs use it) and the
    ignore_unknown_fields path must still hold after the fix."""
    rule = ga4_admin._dict_to_proto(
        {"displayName": "Camel", "thisFieldDoesNotExist": 1}, EventEditRule
    )
    assert ga4_admin._proto_to_dict(rule)["display_name"] == "Camel"


# ---------- event edit rules (v1alpha, _dict_to_proto) ----------


def test_create_event_edit_rule_builds_request_and_parses_response(monkeypatch):
    client = _alpha(
        monkeypatch, "create_event_edit_rule", _load(EventEditRule, "event_edit_rule_created.json")
    )

    out = ga4_admin.create_event_edit_rule(
        "123",
        "9",
        {
            "display_name": "Normalize purchase",
            "event_conditions": [
                {"field": "event_name", "comparison_type": "EQUALS", "value": "purchase"}
            ],
            "parameter_mutations": [{"parameter": "currency", "parameter_value": "USD"}],
        },
    )

    kw = client.create_event_edit_rule.call_args.kwargs
    assert kw["parent"] == "properties/123/dataStreams/9"
    sent = kw["event_edit_rule"]
    assert sent.display_name == "Normalize purchase"
    assert sent.event_conditions[0].value == "purchase"
    assert sent.parameter_mutations[0].parameter_value == "USD"

    assert out["name"] == "properties/123/dataStreams/9/eventEditRules/5"
    assert out["parameter_mutations"][0]["parameter_value"] == "USD"


def test_update_event_edit_rule_sets_mask_from_definition_keys(monkeypatch):
    client = _alpha(
        monkeypatch, "update_event_edit_rule", _load(EventEditRule, "event_edit_rule_created.json")
    )

    out = ga4_admin.update_event_edit_rule(
        "properties/123/dataStreams/9/eventEditRules/5", {"display_name": "Renamed rule"}
    )

    kw = client.update_event_edit_rule.call_args.kwargs
    assert kw["event_edit_rule"].name == "properties/123/dataStreams/9/eventEditRules/5"
    assert kw["event_edit_rule"].display_name == "Renamed rule"
    assert list(kw["update_mask"].paths) == ["display_name"]
    assert out["name"].endswith("/eventEditRules/5")


# ---------- event create rules (v1alpha, _dict_to_proto) ----------


def test_create_event_create_rule_builds_request_and_parses_response(monkeypatch):
    client = _alpha(
        monkeypatch,
        "create_event_create_rule",
        _load(EventCreateRule, "event_create_rule_created.json"),
    )

    out = ga4_admin.create_event_create_rule(
        "123",
        "9",
        {
            "destination_event": "generate_lead",
            "event_conditions": [
                {"field": "event_name", "comparison_type": "EQUALS", "value": "contact_submit"}
            ],
            "source_copy_parameters": True,
        },
    )

    kw = client.create_event_create_rule.call_args.kwargs
    assert kw["parent"] == "properties/123/dataStreams/9"
    assert kw["event_create_rule"].destination_event == "generate_lead"
    assert kw["event_create_rule"].source_copy_parameters is True
    assert out["destination_event"] == "generate_lead"


# ---------- audiences (v1alpha, _dict_to_proto) ----------


def test_create_audience_builds_request_and_parses_nested_response(monkeypatch):
    client = _alpha(monkeypatch, "create_audience", _load(Audience, "audience_created.json"))

    out = ga4_admin.create_audience(
        "123",
        {
            "display_name": "Cart abandoners (7d)",
            "description": "Added to cart, did not purchase within 7 days",
            "membership_duration_days": 7,
        },
    )

    kw = client.create_audience.call_args.kwargs
    assert kw["parent"] == "properties/123"
    assert kw["audience"].display_name == "Cart abandoners (7d)"
    assert kw["audience"].membership_duration_days == 7

    assert out["name"] == "properties/123/audiences/77"
    # nested filter clauses on the response deserialize through _proto_to_dict
    assert out["filter_clauses"][0]["clause_type"] == "INCLUDE"


def test_update_audience_metadata_masks_only_provided_fields(monkeypatch):
    client = _alpha(monkeypatch, "update_audience", _load(Audience, "audience_created.json"))

    out = ga4_admin.update_audience_metadata(
        "properties/123/audiences/77", display_name="Renamed segment"
    )

    kw = client.update_audience.call_args.kwargs
    assert kw["audience"].name == "properties/123/audiences/77"
    assert kw["audience"].display_name == "Renamed segment"
    assert list(kw["update_mask"].paths) == ["display_name"]
    assert out["name"] == "properties/123/audiences/77"


# ---------- custom dimensions / metrics (v1beta, direct constructor) ----------


def test_create_custom_dimension_builds_request_and_parses_response(monkeypatch):
    client = _beta(
        monkeypatch,
        "create_custom_dimension",
        _load(CustomDimension, "custom_dimension_created.json"),
    )

    out = ga4_admin.create_custom_dimension(
        "123", "membership_tier", "Membership tier", "EVENT", "Loyalty tier at event time"
    )

    kw = client.create_custom_dimension.call_args.kwargs
    assert kw["parent"] == "properties/123"
    dim = kw["custom_dimension"]
    assert dim.parameter_name == "membership_tier"
    assert dim.scope == CustomDimension.DimensionScope.EVENT

    assert out["name"] == "properties/123/customDimensions/41"
    assert out["scope"] == "EVENT"


def test_create_custom_metric_builds_request_and_parses_response(monkeypatch):
    client = _beta(
        monkeypatch, "create_custom_metric", _load(CustomMetric, "custom_metric_created.json")
    )

    out = ga4_admin.create_custom_metric(
        "123", "shipping_cost", "Shipping cost", "CURRENCY", "EVENT", "Shipping charged at checkout"
    )

    kw = client.create_custom_metric.call_args.kwargs
    assert kw["parent"] == "properties/123"
    metric = kw["custom_metric"]
    assert metric.parameter_name == "shipping_cost"
    assert metric.measurement_unit == CustomMetric.MeasurementUnit.CURRENCY

    assert out["name"] == "properties/123/customMetrics/12"
    assert out["measurement_unit"] == "CURRENCY"


# ---------- key events (v1beta, direct constructor + limit gate) ----------


def test_create_key_event_under_limit_builds_request_and_parses_response(monkeypatch):
    monkeypatch.setattr(ga4_admin, "list_key_events", lambda pid: [])
    client = _beta(monkeypatch, "create_key_event", _load(KeyEvent, "key_event_created.json"))

    out = ga4_admin.create_key_event("123", "purchase")

    kw = client.create_key_event.call_args.kwargs
    assert kw["parent"] == "properties/123"
    assert kw["key_event"].event_name == "purchase"

    assert out["name"] == "properties/123/keyEvents/88"
    assert out["event_name"] == "purchase"
    assert out["counting_method"] == "ONCE_PER_EVENT"


# ---------- regression: client/type surface mismatch ----------


def test_admin_types_come_from_the_same_surface_as_the_client():
    """Guards the live-API failure the mocked tests above cannot catch.

    ga4_admin builds request messages and takes the client from two different
    imports. When those resolve to different API versions the GAPIC layer
    raises "Parameter to initialize message field must be dict or instance of
    same class". Every message type must come from the same module the client
    does.
    """
    import google.analytics.admin as surface

    from scripts import ga4_admin as mod

    for name in ("CustomDimension", "CustomMetric", "KeyEvent"):
        resolved = mod._admin_type(name)
        if hasattr(surface, name):
            assert resolved is getattr(surface, name), (
                f"{name} resolved to {resolved.__module__}, "
                f"client surface exposes {getattr(surface, name).__module__}"
            )


def test_no_module_level_v1beta_type_imports_in_write_helpers():
    """The three create_* helpers must not re-introduce the split import."""
    import inspect

    from scripts import ga4_admin as mod

    for fn in (mod.create_custom_dimension, mod.create_custom_metric, mod.create_key_event):
        src = inspect.getsource(fn)
        assert "admin_v1beta.types import" not in src, (
            f"{fn.__name__} imports message types from admin_v1beta while the client "
            "comes from google.analytics.admin - this fails against the live API"
        )
