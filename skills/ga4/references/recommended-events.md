# GA4 Recommended E-commerce Events

Canonical reference. Use this when validating event taxonomy and writing implementation recommendations.

## Funnel events (in v1 scope)

| Event | When it fires | Required params | Optional params |
|-------|---------------|-----------------|-----------------|
| `view_item` | Product detail page view | `currency`, `value`, `items[]` | `affiliation`, `coupon` |
| `add_to_cart` | Item added to cart | `currency`, `value`, `items[]` | - |
| `begin_checkout` | Checkout flow started | `currency`, `value`, `items[]` | `coupon` |
| `add_payment_info` | Payment info submitted | `currency`, `value`, `items[]` | `payment_type`, `coupon` |
| `purchase` | Order confirmed | `currency`, `value`, `items[]`, `transaction_id` (unique) | `affiliation`, `coupon`, `shipping`, `tax` |

## Adjacent events (not in v1 funnel, but useful for downstream agents)

| Event | When | Required |
|-------|------|----------|
| `view_item_list` | Listing page (PLP) | `item_list_name`, `items[]` |
| `select_item` | Click on listing item | `item_list_name`, `items[]` |
| `view_promotion` | Promo banner viewed | `items[]` with promotion params |
| `select_promotion` | Promo banner clicked | `items[]` with promotion params |
| `add_to_wishlist` | Item wishlisted | `currency`, `value`, `items[]` |
| `remove_from_cart` | Item removed | `currency`, `value`, `items[]` |
| `add_shipping_info` | Shipping submitted | `currency`, `value`, `items[]`, `shipping_tier` |
| `refund` | Refund processed | `currency`, `value`, `transaction_id`, optional `items[]` |

## `items[]` array required fields

Each item object should include at minimum:

| Field | Notes |
|-------|-------|
| `item_id` | SKU or product ID |
| `item_name` | Product name |
| `price` | Unit price in currency |
| `quantity` | Units of this item in this event |

Recommended additions:
- `item_brand`
- `item_category` (and `item_category2..5` for taxonomy depth)
- `item_variant`
- `discount`
- `index` (position in list, for view_item_list and select_item)

## Validation thresholds

- Required parameter coverage below 95% = High finding
- `purchase` event missing `transaction_id` or value coverage below 100% = Critical
- `items[]` array empty/missing above 5% of events = High
- `transaction_id` duplicate rate above 5% = Critical (revenue inflation)

## Payment-gateway gotchas

- When a payment provider redirects the user out of the page and back,
  the `add_payment_info` event is often tagged on the *return* (after
  payment), not on the submission. This makes step 4 of the funnel
  misleading because it only counts users who already paid. Detect by
  comparing `add_payment_info` count to `purchase` count over a 7-day
  window; within 10% = post-payment firing. The `--check-postpayment`
  flag on `ga4_funnel.py` runs this heuristic.
- Marketplace and aggregator handoffs: when cart-to-purchase happens
  off-property (e.g. on a partner marketplace), `purchase` may never
  reach the originating GA4 property. Flag if `begin_checkout` is
  healthy but `purchase` volume is anomalously low; recommend server-
  side Measurement Protocol push from the partner.

## Heading

The "E-commerce" framing of this reference document is one taxonomy that
the toolkit understands well; for non-ecomm taxonomies (lead-gen, SaaS,
content), supply your own required-parameter table via
`scripts/ga4_events.py --event-params` and an analogous validation rubric.
