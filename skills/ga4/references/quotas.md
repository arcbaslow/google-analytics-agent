# GA4 API quotas

Verified 2026-09-30. The adapters use the generated clients' default retry
behavior; they do not implement a custom 2/4/8-second retry loop or a shared
quota scheduler. Do not promise automatic recovery from exhausted quota.

## Data API

Core, Realtime and Funnel have separate quota categories. For each category:

| Per-property limit | Standard | 360 |
|---|---:|---:|
| Tokens/day | 200,000 | 2,000,000 |
| Tokens/hour | 40,000 | 400,000 |
| Tokens/project/hour | 14,000 | 140,000 |
| Concurrent requests | 10 | 50 |
| Server errors/project/hour | 10 | 50 |

Potentially thresholded requests have a separate 120/hour allowance.
`runFunnelReport` charges Funnel quotas. Request cost depends on the query;
use returned quota metadata instead of assuming a fixed cost. The Chat
category is separate and this toolkit does not call it.
[Official Data API quotas](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas).

## Admin API

Per project: 1,200 requests/minute, 600 requests/minute/user;
600 writes/minute, 180 writes/minute/user. The user-deletion daily limit is
500/property; this toolkit has no user-deletion adapter.
[Official Admin quotas](https://developers.google.com/analytics/devguides/config/admin/v1/quotas).

## Toolkit behavior

Use `--include-metadata` for Data API quota balances. The 15-minute cache
reuses successful identical queries, including empty results. It does not
cache error-bearing results or deduplicate concurrent in-flight requests.
Surface auth/quota errors and incomplete checks. Do not retry Admin writes
automatically: review the outcome before proposing another operation.
