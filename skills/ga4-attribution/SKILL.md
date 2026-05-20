---
name: ga4-attribution
description: "GA4 attribution analysis at each funnel step. Attribution model, lookback windows, conversion lag, channel performance, (direct)/(none) diagnosis. Use when user says 'attribution', 'channels', 'direct traffic', 'which source converts best'."
user-invokable: true
argument-hint: "<property-id> [--days N]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.1.0"
  category: ga4
---

# GA4 Attribution Analysis

## Process

1. Verify auth
2. Check at least one key event configured: `python scripts/ga4_admin.py --property <id> --key-events --json`
3. If none, return "no key events configured, configure at least `purchase` as a key event first"
4. Spawn `ga4-attribution` agent

## Date range

Default 28 days. For conversion-lag analysis, agent may extend to 90 days internally.
