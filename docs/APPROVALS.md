# Admin proposals and terminal approval

MCP can prepare a write without performing it. Call `propose_admin_write`
with an Admin adapter operation name and its Python keyword arguments.
The supported names are listed in `ga4_approval.OPERATIONS`; each represents
one existing writer. For example:

```json
{"operation":"create_key_event","arguments":{"property_id":"123","event_name":"qualified_lead"}}
```

The result contains the resolved arguments, proposal ID, digest, expiry and
an `approval_command`. The user runs that command in their own terminal,
reviews the printed proposal and answers `y` to the existing `y/N` prompt.
An agent must not type the answer or run the command on the user's behalf.
MCP has no proposal execution tool. Existing `confirm=true` arguments cannot
replace terminal approval.

The default lifetime is five minutes; `expires_seconds` accepts 30 to 900.
The executor checks the digest before claiming the proposal, then checks the
resolved operation and expiry again after the prompt. Each proposal is
consumed once, including refusal or failure. A changed target or payload
needs a new proposal. A failed or interrupted RPC may have reached Google:
inspect the property before deciding whether to propose another write.

Use MCP `admin_proposal_status(proposal_id, digest)` or the CLI
`ga4_approval.py --status ID --digest DIGEST` to inspect the outcome.
`applied: null` means the outcome is unknown, not that the write failed to
reach the property. Proposals contain no credentials and are stored under
`~/.claude/ga4-proposals/`. Inputs changed by the PII scrubber are rejected
before storage so the approval view cannot hide a sensitive argument.

Proposal files and outcome receipts remain for local review. The directory
inherits the user's filesystem protections; this is not a security boundary
against another process that controls the same user account. It does prevent
MCP callers from supplying an approval boolean, reusing a consumed proposal,
or executing a changed proposal under the original digest.
