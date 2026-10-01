"""Persist one Admin proposal for an expiring, single-use terminal approval.

There is deliberately no MCP execution tool. This module never supplies y to
the existing Admin confirmation gate and never unwraps a decorated writer.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

import ga4_admin
from ga4_transport import error_result
from ga4_utils import scrub_pii, scrub_response

PROPOSALS_DIR = Path.home() / ".claude" / "ga4-proposals"
OPERATIONS = (
    "create_event_edit_rule",
    "update_event_edit_rule",
    "delete_event_edit_rule",
    "reorder_event_edit_rules",
    "create_event_create_rule",
    "delete_event_create_rule",
    "create_audience",
    "update_audience_metadata",
    "archive_audience",
    "create_custom_dimension",
    "archive_custom_dimension",
    "create_custom_metric",
    "archive_custom_metric",
    "create_key_event",
    "delete_key_event",
)
_ALPHABET = str.maketrans("0123456789abcdef", "abcdefghijklmnop")


def _opaque(value):
    # Alphabetic base16 preserves entropy without looking like a phone number
    # to the mandatory response scrubber. These are opaque identifiers.
    return value.hex().translate(_ALPHABET)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload):
    return _opaque(hashlib.sha256(_canonical(payload).encode()).digest())


def _path(proposal_id, suffix=".json"):
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[a-p]{32}", proposal_id):
        raise ValueError("invalid proposal identifier")
    path = PROPOSALS_DIR / (proposal_id + suffix)
    if path.is_symlink():
        raise ValueError("proposal paths must not be symlinks")
    return path


def _write_new(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(value, file, allow_nan=False)


@scrub_response
def propose(operation, arguments, expires_seconds=300):
    """Bind defaults without auth or API access; reject hidden sensitive input."""
    if operation not in OPERATIONS:
        raise ValueError("unsupported Admin write operation")
    if type(expires_seconds) is not int or not 30 <= expires_seconds <= 900:
        raise ValueError("expires_seconds must be between 30 and 900")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    bound = inspect.signature(getattr(ga4_admin, operation)).bind(**arguments)
    bound.apply_defaults()
    proposal = json.loads(_canonical({"operation": operation, "arguments": bound.arguments}))
    if scrub_pii(proposal) != proposal:
        raise ValueError(
            "proposal contains sensitive values; remove them before requesting approval"
        )
    if len(_canonical(proposal).encode()) > 64000:
        raise ValueError("proposal exceeds 64 KB")
    proposal_id = _opaque(secrets.token_bytes(16))
    payload = {"id": proposal_id, "proposal": proposal, "expires_at": time.time() + expires_seconds}
    digest = _digest(payload)
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_new(_path(proposal_id), payload)
    return {
        "proposal_id": proposal_id,
        "digest": digest,
        "proposal": proposal,
        "expires_at": payload["expires_at"],
        "applied": False,
        "approval_command": f"python scripts/ga4_approval.py --approve {proposal_id} --digest {digest}",
        "instruction": "The user must run this command in their own terminal, review the proposal, and answer y/N. Do not supply the answer for them.",
    }


def _load(proposal_id, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[a-p]{64}", digest):
        raise ValueError("invalid proposal digest")
    path = _path(proposal_id)
    if path.stat().st_size > 68000:
        raise ValueError("proposal exceeds size limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("id") != proposal_id or not secrets.compare_digest(_digest(payload), digest):
        raise ValueError("proposal changed or digest does not match")
    if payload["proposal"]["operation"] not in OPERATIONS:
        raise ValueError("unsupported Admin write operation")
    return payload


@scrub_response
def proposal_status(proposal_id, digest):
    payload = _load(proposal_id, digest)
    result = _path(proposal_id, ".result.json")
    if result.exists():
        try:
            return json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"status": "execution_unknown", "applied": None}
    if _path(proposal_id, ".claimed").exists():
        return {"status": "execution_unknown", "applied": None}
    return {
        "status": "expired" if time.time() >= payload["expires_at"] else "pending",
        "applied": False,
        "proposal": payload["proposal"],
    }


@scrub_response
def approve(proposal_id, digest):
    """Consume one proposal, then invoke exactly one unchanged confirmation gate."""
    payload = _load(proposal_id, digest)
    if not sys.stdin.isatty():
        raise ga4_admin.ConfirmationRequiredError(
            "Approval requires the user's interactive terminal."
        )
    if time.time() >= payload["expires_at"]:
        raise ga4_admin.ConfirmationRequiredError("Proposal expired; request a new proposal.")
    try:
        _write_new(_path(proposal_id, ".claimed"), {"claimed": True})
    except FileExistsError:
        raise ga4_admin.ConfirmationRequiredError(
            "Proposal already consumed; inspect its status."
        ) from None

    def precondition(resolved):
        if time.time() >= payload["expires_at"]:
            raise ga4_admin.ConfirmationRequiredError("Proposal expired while awaiting approval.")
        if _canonical(resolved) != _canonical(payload["proposal"]):
            raise ga4_admin.ConfirmationRequiredError(
                "Resolved operation differs from the proposal."
            )

    token = ga4_admin._WRITE_PRECONDITION.set(precondition)
    outcome = {"status": "execution_unknown", "applied": None}
    try:
        result = getattr(ga4_admin, payload["proposal"]["operation"])(
            **payload["proposal"]["arguments"]
        )
        outcome = {"status": "applied", "applied": True, "result": result}
    except ga4_admin.ConfirmationRequiredError as exc:
        outcome = {"status": "cancelled", "applied": False, **error_result(exc)}
        raise
    except Exception as exc:
        # A failed RPC may have reached the service. Never auto-replay it.
        outcome = {"status": "execution_failed", "applied": None, **error_result(exc)}
        raise
    finally:
        ga4_admin._WRITE_PRECONDITION.reset(token)
        _write_new(_path(proposal_id, ".result.json"), scrub_pii(outcome))
    return outcome


def main():
    parser = argparse.ArgumentParser(description="Approve one saved GA4 Admin proposal")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--approve", metavar="PROPOSAL_ID")
    actions.add_argument("--status", metavar="PROPOSAL_ID")
    parser.add_argument("--digest", required=True)
    args = parser.parse_args()
    try:
        result = (
            approve(args.approve, args.digest)
            if args.approve
            else proposal_status(args.status, args.digest)
        )
    except Exception as exc:
        print(json.dumps(error_result(exc)), file=sys.stderr)
        return 1
    print(json.dumps(scrub_pii(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
