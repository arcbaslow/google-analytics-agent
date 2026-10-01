"""Every Admin writer needs a separate, interactive approval before API access."""

import json
from unittest.mock import MagicMock

import ga4_admin
import ga4_mcp
import pytest

WRITES = [
    ("create_event_edit_rule", ("123", "9", {"display_name": "Rule"})),
    (
        "update_event_edit_rule",
        ("properties/123/dataStreams/9/eventEditRules/1", {"display_name": "Rule"}),
    ),
    ("delete_event_edit_rule", ("properties/123/dataStreams/9/eventEditRules/1",)),
    ("reorder_event_edit_rules", ("123", "9", ["properties/123/dataStreams/9/eventEditRules/1"])),
    ("create_event_create_rule", ("123", "9", {"destination_event": "lead"})),
    ("delete_event_create_rule", ("properties/123/dataStreams/9/eventCreateRules/1",)),
    ("create_audience", ("123", {"display_name": "Buyers", "membership_duration_days": 7})),
    ("update_audience_metadata", ("properties/123/audiences/1", "Buyers")),
    ("archive_audience", ("properties/123/audiences/1",)),
    ("create_custom_dimension", ("123", "plan", "Plan", "EVENT")),
    ("archive_custom_dimension", ("properties/123/customDimensions/1",)),
    ("create_custom_metric", ("123", "score", "Score", "STANDARD")),
    ("archive_custom_metric", ("properties/123/customMetrics/1",)),
    ("create_key_event", ("123", "lead")),
    ("delete_key_event", ("properties/123/keyEvents/1",)),
]


@pytest.mark.parametrize("name,args", WRITES)
@pytest.mark.parametrize("answer", ["", "n", "yes", "y"])
def test_each_write_requires_one_approval(monkeypatch, capsys, name, args, answer):
    factory = MagicMock()
    client = factory.return_value
    monkeypatch.setattr(ga4_admin, "_get_admin_client", factory)
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", factory)
    monkeypatch.setattr(ga4_admin, "list_key_events", lambda _, **kw: [])
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda _: {"ok": True})
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)
    prompt = MagicMock(return_value=answer)
    monkeypatch.setattr("builtins.input", prompt)
    if answer == "y":
        getattr(ga4_admin, name)(*args)
        assert len(client.method_calls) == 1
    else:
        with pytest.raises(ga4_admin.ConfirmationRequiredError):
            getattr(ga4_admin, name)(*args)
        factory.assert_not_called()
    prompt.assert_called_once_with()
    captured = capsys.readouterr()
    assert captured.out == ""
    proposal, _ = captured.err.split("Apply this change? [y/N]")
    assert json.loads(proposal)["operation"] == name


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_interrupted_approval_is_cancelled(monkeypatch, error):
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=error))
    factory = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", factory)
    with pytest.raises(ga4_admin.ConfirmationRequiredError):
        ga4_admin.delete_key_event("properties/123/keyEvents/1")
    factory.assert_not_called()


def test_mcp_confirm_cannot_consume_protocol_input_or_write(monkeypatch):
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: False)
    prompt, factory = MagicMock(), MagicMock()
    monkeypatch.setattr("builtins.input", prompt)
    monkeypatch.setattr(ga4_admin, "_get_admin_client", factory)
    out = ga4_mcp.add_key_event("123", "purchase", confirm=True)
    assert out["error"] == "confirmation_required"
    assert out["applied"] is False
    prompt.assert_not_called()
    factory.assert_not_called()


def test_cli_rejects_multiple_actions_before_dispatch(monkeypatch):
    monkeypatch.setattr(
        ga4_admin.sys, "argv", ["ga4_admin", "--details", "--add-key-event", "lead"]
    )
    dispatch = MagicMock()
    monkeypatch.setattr(ga4_admin, "_dispatch", dispatch)
    with pytest.raises(SystemExit) as exc:
        ga4_admin.main()
    assert exc.value.code == 2
    dispatch.assert_not_called()


def test_proposal_is_frozen_while_waiting_for_confirmation(monkeypatch):
    definition = {"display_name": "Original"}
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)

    def answer():
        definition["display_name"] = "Changed"
        return "y"

    monkeypatch.setattr("builtins.input", answer)
    client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda **_: client)
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda _: {})
    ga4_admin.create_audience("123", definition)
    assert client.create_audience.call_args.kwargs["audience"].display_name == "Original"
