---
name: ga4-key-events
description: "Create or delete GA4 key events (formerly Conversions) via the Admin API. Key events feed conversion reports, Google Ads import, and attribution. Limit: 30 per property."
user-invokable: true
argument-hint: "<property-id> [--list|--add <event-name> [--counting-method ONCE_PER_EVENT|ONCE_PER_SESSION]|--delete <name>]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Key Events (Conversions)

Scope required: `analytics.edit`.

## Process

1. List existing key events to confirm headroom (limit: 30).
2. Show the user the proposed event name and counting method, ask `y/n`.
3. Create / delete via the script.

## Commands

| Intent | Command |
|--------|---------|
| List | `python scripts/ga4_admin.py --property X --key-events --json` |
| Create | `python scripts/ga4_admin.py --property X --add-key-event purchase --counting-method ONCE_PER_EVENT --json` |
| Delete | `python scripts/ga4_admin.py --delete-key-event properties/X/keyEvents/123 --json` |

## Counting methods

- `ONCE_PER_EVENT` — every event hit counts (default; matches old "Standard")
- `ONCE_PER_SESSION` — one count per session no matter how many fires

High-frequency events (`add_to_cart`, `page_view`) use `ONCE_PER_EVENT`
when every fire matters. Lead-gen forms and signup events typically use
`ONCE_PER_SESSION` to avoid double-counting accidental resubmissions.

## Common key events by site type

- E-commerce: `purchase`; sometimes `add_to_cart` or `begin_checkout` for
  funnel reporting
- Lead-gen: `generate_lead`, `contact_form_submit`, `request_demo`
- SaaS: `sign_up`, plus an activation event (`completed_onboarding`,
  `first_<feature>`)
- Content / media: `subscribe`, `play_video` past a threshold
- Avoid making low-signal events like `view_item` a key event unless your
  brand-discovery model genuinely needs it; otherwise it pollutes Ads bidding

Every Admin write is gated inside `ga4_admin.py`: it prints a scrubbed proposal
and asks `y/N` for that operation. Run it in an interactive terminal; piped
input, EOF and cancellation refuse the write. There is no bypass flag. MCP
stdio tools provide previews; `confirm=true` returns `confirmation_required`
without terminal approval. Never chain writes.

Key-event capacity uses the API custom flag: default key events do not consume the custom limit. At the Standard boundary, creation reads the current property service level: Standard permits 30 custom key events and Analytics 360 permits 50. Unknown service levels defer enforcement to the API. Auth --check --write reports edit-scope evidence and rejects missing or unknown edit scopes; declared scopes are distinguished from granted scopes and do not establish a property role. Legacy OAuth never adds unconsented scopes to stored credentials. Each write still requires its own y/N approval.

MCP propose_admin_write saves one exact Admin proposal for an expiring, single-use terminal approval. The user must run its approval_command and answer the existing y/N prompt themselves; agents must not supply approval. admin_proposal_status only reads the outcome. There is no MCP execute tool, and confirm=true remains insufficient. Refused or failed proposals cannot be replayed; applied:null means the result is unknown. See docs/APPROVALS.md.
