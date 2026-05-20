---
name: ga4-events-edit
description: "Edit GA4 events via the Admin API. Wraps EventEditRule (rename/rewrite incoming events, modify parameters) and EventCreateRule (synthesize new events from existing ones). Per-data-stream. Triggers: 'rename an event', 'change event parameter', 'create event rule', 'modify event'."
user-invokable: true
argument-hint: "<property-id> [--stream <id>] [--list|--add-edit <file>|--add-create <file>|--delete <rule-name>]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Edit Events

EventCreateRule and EventEditRule live **per data stream**, not per property,
so every command needs both `--property` and `--stream`.

Scope required: `analytics.edit`. If the user is on read-only auth, instruct
them to run:

```
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/cloud-platform
```

## Process

1. Verify auth: `python scripts/ga4_auth.py --check`
2. If the user does not pass `--stream`, list streams with
   `python scripts/ga4_admin.py --property <id> --streams --json` and ask them
   to pick.
3. For diagnostic-driven proposals, spawn the `ga4-events-editor` agent.
4. Print the resolved rule JSON to the user and ask `y/n` before any write.
5. Run the script.

## Direct commands

| Intent | Command |
|--------|---------|
| List rules on a stream | `python scripts/ga4_admin.py --property X --stream Y --list-event-rules --json` |
| Add an edit rule | `python scripts/ga4_admin.py --property X --stream Y --add-edit-rule rule.json --json` |
| Add a create rule | `python scripts/ga4_admin.py --property X --stream Y --add-create-rule rule.json --json` |
| Delete an edit rule | `python scripts/ga4_admin.py --rule-name <full> --delete-edit-rule --json` |
| Delete a create rule | `python scripts/ga4_admin.py --rule-name <full> --delete-create-rule --json` |

## Rule JSON shapes

`EventEditRule` (rewrite an existing event):

```json
{
  "display_name": "Normalize signup events",
  "event_conditions": [
    {"field": "event_name", "comparison_type": "EQUAL", "value": "signed_up"}
  ],
  "parameter_mutations": [
    {"parameter": "event_name", "parameter_value": "sign_up"}
  ]
}
```

`EventCreateRule` (synthesize a new event from another):

```json
{
  "destination_event": "engaged_view",
  "event_conditions": [
    {"field": "event_name", "comparison_type": "EQUAL", "value": "page_view"},
    {"field": "engagement_time_msec", "comparison_type": "GREATER_THAN", "value": "30000"}
  ],
  "source_copy_parameters": true,
  "parameter_mutations": []
}
```

## Limits and constraints

- v1alpha API — schema may change; recheck on SDK bump.
- Web streams only (per current Admin docs).
- Edit rules run in a defined order; use `reorder_event_edit_rules` to rearrange.
- Edit rules **cannot** modify events produced by create rules.

## Common mistakes to flag

- Renaming `purchase` — breaks every conversion report and Ads import. Refuse without explicit confirmation in the message.
- Mutating `transaction_id` — kills duplicate-purchase detection.
- Creating a synthesized event whose name collides with a real one — produces double-counting.
