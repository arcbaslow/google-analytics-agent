---
name: ga4-events
description: "GA4 event taxonomy validation. Lists distinct events on a property, checks event presence, reports the built-in parameter proxies and marks unsupported checks. Includes an opt-in heuristic for the post-payment redirect-back issue that affects e-commerce funnels."
user-invokable: true
argument-hint: "<property-id> [--days N] [--check-events e1,e2,...]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4: Event checks

Verify auth, then use the `ga4-events` agent or the commands in its definition.
Default window is seven days. Named-event presence checks work across taxonomies.

The required-parameter table is fixed in `ga4_events.py`; there is no custom
`--required-params` option. Coverage outputs are aggregated proxies, not raw
parameter completeness. Duplicate-ID detection and nested payload validation
are not implemented. The optional post-payment count comparison does not
establish event order. Return unavailable checks and errors explicitly.

Parameter aggregate metrics return `coverage_pct: null` with `status: not_measurable`; positive revenue is not proof of complete tagging. Segment audits use the API `sessionKeyEventRate` and label findings `session_key_event_rate`.

BigQuery evidence is optional: install .[bigquery] and use ga4_bigquery.py with explicit billing/source projects, dataset, location and dates. It estimates fixed aggregate queries by default; --execute can incur charges and requires explicit user authorization. Enforce --max-bytes (default 1 GiB), inspect unknown job outcomes before resubmitting, and never export individual rows. MCP bigquery_dry_run cannot execute. See docs/BIGQUERY.md for parameter coverage, consent, freshness and first-entry funnel semantics.
