---
name: ga4-conversions
description: "GA4 key events (conversions) configuration audit. Validates which events are marked as key events, conversion value reporting, counting method, refund handling. Use when user says 'conversions', 'key events', 'are my key events configured right'."
user-invokable: true
argument-hint: "<property-id> [--days N]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.1.0"
  category: ga4
---

# GA4 Key Events Configuration Audit

## Process

1. Verify auth
2. Spawn `ga4-conversions` agent

## After analysis

If at least one key event configured, offer:
"Want to see attribution at each funnel step? Use `/ga4 attribution <property-id>`"
