---
name: ga4-audiences
description: "Manage GA4 Audiences via the Admin API. Create, list, archive, rename. Audiences are stored cohorts based on event/dimension filters, usable in reports and Google Ads. Triggers: 'create audience', 'audience definition', 'cohort builder', 'high-intent users'."
user-invokable: true
argument-hint: "<property-id> [--list|--create <file>|--archive <name>|--rename <name>]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Audiences

Audiences are **immutable post-create** for their filter clauses — only
`display_name` and `description` can be changed afterward. To alter the
filter, archive the existing audience and create a new one.

Scope required: `analytics.edit`.

## Process

1. Verify auth.
2. For proposals based on observed funnel drop-off, spawn the `ga4-audience-builder` agent.
3. Print the JSON definition and ask `y/n` before creating.
4. Run the script.

## Direct commands

| Intent | Command |
|--------|---------|
| List audiences | `python scripts/ga4_admin.py --property X --list-audiences --json` |
| Create audience | `python scripts/ga4_admin.py --property X --create-audience audience.json --json` |
| Archive audience | `python scripts/ga4_admin.py --audience-name <full> --archive-audience --json` |

## Definition shape

```json
{
  "display_name": "Cart abandoners (7d)",
  "description": "Users who added to cart but did not purchase",
  "membership_duration_days": 7,
  "filter_clauses": [
    {
      "clause_type": "INCLUDE",
      "simple_filter": {
        "scope": "AUDIENCE_FILTER_SCOPE_ACROSS_ALL_SESSIONS",
        "filter_expression": {
          "event_filter": {"event_name": "add_to_cart"}
        }
      }
    },
    {
      "clause_type": "EXCLUDE",
      "simple_filter": {
        "scope": "AUDIENCE_FILTER_SCOPE_ACROSS_ALL_SESSIONS",
        "filter_expression": {
          "event_filter": {"event_name": "purchase"}
        }
      }
    }
  ]
}
```

## Limits

- 100 audiences per property (400 on GA4 360).
- `membership_duration_days` must be ≤ 540.
- Up to 14 days of historical backfill on creation.

## Useful audience patterns

- **Cart abandoners**: include `add_to_cart`, exclude `purchase`, 7-day membership
- **Engaged readers**: include `page_view` with engagement_time_msec > 60000, scope WITHIN_SAME_SESSION
- **High-value purchasers**: include `purchase` where `value` >= threshold, scope ACROSS_ALL_SESSIONS
- **Inactive in last 30 days**: invert via NOT on `session_start`, scope ACROSS_ALL_SESSIONS
