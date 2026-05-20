---
name: ga4-funnel
description: "GA4 step-by-step funnel analysis. Builds an N-step funnel from any list of event names, computes step conversion and drop-off rates, identifies the leakiest step, and supports breakdown by a single dimension. Use when user says 'funnel', 'drop-off', 'where are users dropping', 'conversion rate'."
user-invokable: true
argument-hint: "<property-id> [--days N] [--steps e1,e2,...] [--preset ecomm] [--breakdown <dim>] [--check-postpayment]"
license: MIT
metadata:
  author: Dilshat Rakhimov
  version: "0.2.0"
  category: ga4
---

# GA4 Funnel Analysis

## Process

1. Verify auth: `python scripts/ga4_auth.py --check`
2. If the user did not specify `--steps` or `--preset`, propose a funnel
   based on what events fire on the property and ask for confirmation.
3. Validate event coverage with the events script:
   `python scripts/ga4_events.py --property <id> --check-events <step1,step2,...> --days 7`
4. Spawn the `ga4-funnel` agent with the property ID and validated step list.
5. Return agent output with an optional follow-up offer.

## Funnel inputs

- `--steps event1,event2,event3` — arbitrary list of GA4 event names; the funnel runs in the listed order.
- `--preset ecomm` — convenience preset for the recommended e-commerce purchase funnel: `view_item -> add_to_cart -> begin_checkout -> add_payment_info -> purchase`.
- Neither flag: the agent proposes a funnel based on which events fire on the property.

## Optional checks

- `--check-postpayment` (off by default): runs the post-payment heuristic
  against `add_payment_info`. If the count is within 10% of `purchase`, the
  event fires after the payment-gateway redirect-back and the step is
  dropped from the funnel with a Critical finding.
- `--breakdown <dim>` — funnel split by one dimension (e.g.
  `deviceCategory`, `sessionDefaultChannelGroup`).

## Date range

Default 28 days. Override with `--days N`.

## After analysis

Offer: "Want to break down the drop-off by segment? Use `/ga4 segments <property-id>`"
