---
name: ga4-property
description: "GA4 property configuration audit. Data streams, retention, cross-domain, internal traffic filters, referral exclusions, enhanced measurement, custom dimensions, platform links (Ads, Search Console, BigQuery, Merchant Center). Use when user says 'property setup', 'configuration', 'is my GA4 set up right'."
user-invokable: true
argument-hint: "<property-id>"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.1.0"
  category: ga4
---

# GA4 Property Configuration Audit

## Process

1. Verify auth
2. Spawn `ga4-property` agent
