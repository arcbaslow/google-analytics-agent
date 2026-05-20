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
