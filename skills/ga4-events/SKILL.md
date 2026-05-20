---
name: ga4-events
description: "GA4 event taxonomy validation. Lists distinct events on a property, checks event presence, validates required parameters against a configurable schema, surfaces gaps (missing events, low-coverage parameters, duplicate IDs). Includes an opt-in heuristic for the post-payment redirect-back issue that affects e-commerce funnels."
user-invokable: true
argument-hint: "<property-id> [--days N] [--check-events e1,e2,...] [--required-params <json>]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Event Taxonomy Validation

A generic taxonomy validator. The built-in required-parameter table covers
Google's recommended e-commerce events as one example; for other event
schemas (lead-gen, content, SaaS engagement, custom), supply your own table
via `--required-params`.

## Process

1. Verify auth.
2. Spawn the `ga4-events` agent.
3. Default window: 7 days (event-shape sampling, not trend analysis).

## Built-in checks

| Check | What it does |
|-------|---------------|
| Presence | Does the event fire at all in the window? |
| Required parameters | What share of events carry each required parameter? |
| Identifier uniqueness | For events with an ID (e.g. `purchase.transaction_id`), is it unique? |
| Volume sanity | Outlier days where event volume drops or spikes sharply |
| Post-payment heuristic (opt-in) | `add_payment_info` count within 10% of `purchase` count → fires after the payment gateway redirect-back |

## After analysis

Offer: "Want to see the funnel with validated steps? Use `/ga4 funnel <property-id>`"
