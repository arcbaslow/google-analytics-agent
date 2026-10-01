import inspect
import json
from unittest.mock import Mock

import ga4_admin
import ga4_approval as approval
import ga4_mcp
import pytest
from test_ga4_write_confirmation import WRITES


@pytest.fixture(autouse=True)
def isolated_proposals(monkeypatch, tmp_path):
    monkeypatch.setattr(approval, "PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)


def create_proposal():
    return approval.propose("delete_key_event", {"name": "properties/123/keyEvents/1"})


@pytest.mark.parametrize("operation,args", WRITES)
def test_all_operations_bind_defaults_then_require_one_prompt(monkeypatch, operation, args):
    client = Mock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **kw: client)
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda **kw: client)
    monkeypatch.setattr(ga4_admin, "list_key_events", lambda *a, **kw: [])
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda _: {"ok": True})
    bound = inspect.signature(getattr(ga4_admin, operation)).bind(*args)
    proposal = ga4_mcp.propose_admin_write(operation, dict(bound.arguments))
    assert proposal["applied"] is False and client.method_calls == []
    prompt = Mock(return_value="y")
    monkeypatch.setattr("builtins.input", prompt)
    result = approval.approve(proposal["proposal_id"], proposal["digest"])
    assert result["applied"] is True
    prompt.assert_called_once_with()
    assert len(client.method_calls) == 1
    assert (
        ga4_mcp.admin_proposal_status(proposal["proposal_id"], proposal["digest"])["applied"]
        is True
    )
    with pytest.raises(ga4_admin.ConfirmationRequiredError, match="consumed"):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    assert len(client.method_calls) == 1


@pytest.mark.parametrize("answer", ["n", "", "yes"])
def test_refusal_consumes_proposal_without_client_access(monkeypatch, answer):
    proposal = create_proposal()
    factory = Mock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", factory)
    monkeypatch.setattr("builtins.input", lambda: answer)
    with pytest.raises(ga4_admin.ConfirmationRequiredError):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    assert (
        approval.proposal_status(proposal["proposal_id"], proposal["digest"])["status"]
        == "cancelled"
    )
    factory.assert_not_called()


def test_expiry_is_checked_again_after_human_prompt(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(approval.time, "time", lambda: clock[0])
    proposal = create_proposal()
    factory = Mock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", factory)

    def answer():
        clock[0] = proposal["expires_at"]
        return "y"

    monkeypatch.setattr("builtins.input", answer)
    with pytest.raises(ga4_admin.ConfirmationRequiredError, match="expired"):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    factory.assert_not_called()


def test_tampering_fails_digest_check(monkeypatch):
    proposal = create_proposal()
    path = approval._path(proposal["proposal_id"])
    payload = json.loads(path.read_text())
    payload["proposal"]["arguments"]["name"] = "properties/999/keyEvents/1"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="digest"):
        approval.approve(proposal["proposal_id"], proposal["digest"])


def test_stdio_cannot_claim_or_approve(monkeypatch):
    proposal = create_proposal()
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: False)
    prompt = Mock()
    monkeypatch.setattr("builtins.input", prompt)
    with pytest.raises(ga4_admin.ConfirmationRequiredError):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    prompt.assert_not_called()
    assert (
        approval.proposal_status(proposal["proposal_id"], proposal["digest"])["status"] == "pending"
    )


def test_failure_is_not_reported_as_definitely_unapplied(monkeypatch):
    proposal = create_proposal()
    client = Mock()
    client.delete_key_event.side_effect = RuntimeError("connection lost person@example.com")
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **kw: client)
    monkeypatch.setattr("builtins.input", lambda: "y")
    with pytest.raises(RuntimeError):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    out = approval.proposal_status(proposal["proposal_id"], proposal["digest"])
    assert out["applied"] is None and "person@example.com" not in str(out)


@pytest.mark.parametrize(
    "operation,args,ttl",
    [
        ("get_property_details", {"property_id": "123"}, 300),
        ("delete_key_event", {"name": "properties/123/keyEvents/1"}, 0),
        (
            "create_audience",
            {"property_id": "123", "definition": {"display_name": "person@example.com"}},
            300,
        ),
    ],
)
def test_invalid_or_sensitive_proposals_are_not_saved(operation, args, ttl):
    with pytest.raises(ValueError):
        approval.propose(operation, args, ttl)
    assert not approval.PROPOSALS_DIR.exists()


def test_expired_proposal_and_invalid_identifiers(monkeypatch):
    proposal = create_proposal()
    monkeypatch.setattr(approval.time, "time", lambda: proposal["expires_at"])
    assert (
        approval.proposal_status(proposal["proposal_id"], proposal["digest"])["status"] == "expired"
    )
    with pytest.raises(ga4_admin.ConfirmationRequiredError, match="expired"):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    with pytest.raises(ValueError, match="identifier"):
        approval.proposal_status("../outside", proposal["digest"])
    with pytest.raises(ValueError, match="digest"):
        approval.proposal_status(proposal["proposal_id"], "bad")


def test_changed_resolved_operation_cannot_use_old_approval(monkeypatch):
    proposal = create_proposal()
    monkeypatch.setattr(ga4_admin, "delete_key_event", ga4_admin.archive_custom_dimension)
    monkeypatch.setattr("builtins.input", lambda: "y")
    factory = Mock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", factory)
    with pytest.raises(ga4_admin.ConfirmationRequiredError, match="differs"):
        approval.approve(proposal["proposal_id"], proposal["digest"])
    factory.assert_not_called()


def test_claimed_without_result_is_unknown_and_cli_can_inspect(monkeypatch, capsys):
    proposal = create_proposal()
    approval._write_new(approval._path(proposal["proposal_id"], ".claimed"), {})
    monkeypatch.setattr(
        approval.sys,
        "argv",
        ["ga4_approval", "--status", proposal["proposal_id"], "--digest", proposal["digest"]],
    )
    assert approval.main() == 0
    assert json.loads(capsys.readouterr().out)["applied"] is None
