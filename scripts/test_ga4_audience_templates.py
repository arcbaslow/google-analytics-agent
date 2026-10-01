import json
from unittest.mock import Mock

import ga4_admin
import ga4_audience_templates as templates
import ga4_mcp
import pytest
from google.analytics.admin_v1alpha.types import Audience
from google.protobuf.json_format import ParseDict


def parse(definition):
    return Audience.wrap(ParseDict(definition, Audience.pb(Audience())))


def event_filter(expression):
    return expression.and_group.filter_expressions[0].or_group.filter_expressions[0].event_filter


def test_event_template_is_offline_and_has_required_expression_grammar(monkeypatch):
    client = Mock(side_effect=AssertionError("must not resolve credentials"))
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", client)
    definition = ga4_mcp.audience_template("event_participants", "Started", ["start"])
    audience = parse(definition)
    simple = audience.filter_clauses[0].simple_filter
    assert event_filter(simple.filter_expression).event_name == "start"
    assert simple.scope.name == templates.EVENT_SCOPE and audience.membership_duration_days == 30
    client.assert_not_called()


def test_numeric_template_scopes_threshold_to_same_event():
    audience = parse(
        templates.audience_template(
            "event_parameter_threshold",
            "High value event",
            ["purchase"],
            parameter="value",
            threshold=100,
        )
    )
    event = event_filter(audience.filter_clauses[0].simple_filter.filter_expression)
    leaf = event.event_parameter_filter_expression.and_group.filter_expressions[
        0
    ].dimension_or_metric_filter
    assert event.event_name == "purchase" and leaf.field_name == "value"
    assert (
        leaf.numeric_filter.operation.name == "GREATER_THAN"
        and leaf.numeric_filter.value.double_value == 100
    )
    assert "Not a lifetime-value" in audience.description


def test_sequence_order_and_window_are_explicit():
    audience = parse(
        templates.audience_template(
            "event_sequence", "Completed", ["start", "finish"], window_seconds=300
        )
    )
    sequence = audience.filter_clauses[0].sequence_filter
    assert sequence.scope.name == templates.SEQUENCE_SCOPE
    assert sequence.sequence_maximum_duration.total_seconds() == 300
    assert [event_filter(s.filter_expression).event_name for s in sequence.sequence_steps] == [
        "start",
        "finish",
    ]
    assert not sequence.sequence_steps[1].immediately_follows


@pytest.mark.parametrize(
    "update",
    [
        {"template": "ui_disengaged_purchasers"},
        {"display_name": ""},
        {"display_name": "person@example.com"},
        {"events": ["bad name"]},
        {"events": ["a", "a"]},
        {"membership_days": 0},
        {"membership_days": 541},
        {"events": ["a", "b"]},
        {"window_seconds": 1},
        {"parameter": "value", "threshold": 1},
        {"template": "event_parameter_threshold"},
        {"template": "event_parameter_threshold", "parameter": "eventCount", "threshold": 1},
        {"template": "event_parameter_threshold", "parameter": "value", "threshold": float("nan")},
        {"template": "event_sequence", "events": ["a", "b"]},
        {
            "template": "event_sequence",
            "events": ["a", "b"],
            "window_seconds": 1,
            "parameter": "value",
        },
    ],
)
def test_invalid_or_ambiguous_templates_rejected(update):
    args = dict(template="event_participants", display_name="Example", events=["start"]) | update
    with pytest.raises(ValueError):
        templates.audience_template(**args)


def test_cli_outputs_only_definition_for_existing_creation_path(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "templates",
            "--template",
            "event_participants",
            "--display-name",
            "Started",
            "--events",
            "start",
        ],
    )
    assert templates.main() == 0
    assert parse(json.loads(capsys.readouterr().out)).display_name == "Started"
    monkeypatch.setattr(
        "sys.argv",
        [
            "templates",
            "--template",
            "event_participants",
            "--display-name",
            "person@example.com",
            "--events",
            "start",
        ],
    )
    assert templates.main() == 1
    assert "person@example.com" not in capsys.readouterr().err
