---
name: ga4-quality
description: "GA4 data quality and integrity audit. Sampling, (not set) density, (direct)/(none) bloat, self-referrals, threshold suppression, bot indicators, internal traffic filter status. Use when user says 'data quality', 'can I trust this data', 'why is direct so high', 'sampling'."
user-invokable: true
argument-hint: "<property-id> [--days N]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.1.0"
  category: ga4
---

# GA4 Data Quality Audit

## Process

1. Verify auth
2. Spawn `ga4-quality` agent

## Output

The agent produces a confidence label (High / Medium / Low / Very Low) that downstream agents reference. Save the label to `.ga4-cache/<property-id>/quality-confidence.json` so subsequent agent runs can read it without re-running the quality audit.
