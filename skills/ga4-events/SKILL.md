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
