---
name: ga4-segments
description: "GA4 funnel drop-off cohort analysis. Breaks down each funnel step by device, source/medium, country, landing page, new-vs-returning. Funnel steps are taken from the caller and the analysis is taxonomy-agnostic. Use when user says 'segment', 'cohort', 'which devices', 'which channels', 'why is segment X lower'."
user-invokable: true
argument-hint: "<property-id> [--days N] [--breakdown device|source|country|landing|new-vs-returning|all]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.1.0"
  category: ga4
---

# GA4 Funnel Segment Analysis

## Process

1. Verify auth
2. Spawn `ga4-segments` agent

## Breakdowns

Default `all`: device, channel group, source, medium, country, landing page, new-vs-returning.

Override with `--breakdown <dim>` to run a single dimension.

## Confidence inheritance

If a recent ga4-quality run reports sampling >10% or `(not set)` density >20% on a dimension, the agent will mark that breakdown as "directional only" in output.

## After analysis

Offer: "Want to drill into a specific segment? Re-run with `--breakdown <dim>` for the dimension that caught your eye."
