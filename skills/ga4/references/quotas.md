# GA4 Data API and Admin API Quotas

Reference for the rate-limit-aware fetch logic in `ga4_data.py` and `ga4_admin.py`.

## Data API (standard properties)

| Quota | Limit | Refresh |
|-------|-------|---------|
| Core tokens per project per day | 200,000 | Daily |
| Core tokens per property per day | 25,000 | Daily |
| Core tokens per property per hour | 5,000 | Hourly |
| Concurrent requests per property | 10 | - |
| Server errors per property per hour | 50 | Hourly |
| Realtime tokens per property per day | 25,000 | Daily |

Each `runReport` call consumes 1+ tokens depending on dimension/metric complexity. Complex breakdowns (5+ dimensions, custom dimensions) can consume 5-10 tokens each.

## Data API (GA4 360 properties)

Same shape, much higher limits:

| Quota | Limit |
|-------|-------|
| Core tokens per property per day | 1,000,000 |
| Core tokens per property per hour | 50,000 |
| Concurrent requests per property | 50 |

## Funnel Report (v1alpha)

`runFunnelReport` is on the v1alpha endpoint. Quota tier still counts against core tokens but with higher cost per call (typically 10-50 tokens per funnel report depending on step count and breakdowns).

## Admin API

| Quota | Limit |
|-------|-------|
| Read calls per project per minute | 600 |
| Read calls per user per minute | 60 |
| Write calls per project per minute | 60 |

## Backoff strategy

On HTTP 429 (quota exceeded):
1. Read `Retry-After` header if present
2. Otherwise exponential backoff: 2s, 4s, 8s, 16s, 32s, then fail
3. Surface as partial result with "rate limited" flag rather than full failure

On HTTP 503 (server error):
- Same exponential backoff, max 3 retries

## Caching

`ga4_utils.cache_get/cache_set` provide 15-min TTL local JSON cache. For multi-agent parallel audits, this prevents the same property/date-range query from hitting the API multiple times.

Cache key includes property ID, query params, and date range. Different agents querying the same data structure benefit from cross-agent cache hits.
