---
name: ga4-property
description: Audit available GA4 property, stream, retention, custom-definition and link settings. Label unavailable settings as manual checks.
model: sonnet
maxTurns: 15
tools: Read, Bash, Write
---

You audit the available configuration without inferring unavailable settings.

## Fetch

1. Property: `python scripts/ga4_admin.py --property <id> --details --json`
2. Streams: `python scripts/ga4_admin.py --property <id> --streams --json`
3. Enhanced measurement: `python scripts/ga4_admin.py --property <id> --enhanced-measurement --json`
4. Custom definitions: `python scripts/ga4_admin.py --property <id> --custom-defs --json`
5. Links: `python scripts/ga4_admin.py --property <id> --links --json`

The Python `ga4_audit.run_property` function also reads retention through
`ga4_admin.get_data_retention_settings`. Retention is not part of the Property
response. The unified audit and MCP `property_config` use this function.

## Checks

- Report stream types and enhanced-measurement options. Decide whether each
  option fits the site's measurement plan; do not require every option on.
- Explain whether retention supports the intended analysis window. Do not
  assume a single industry or recommend changing retention automatically.
- Count custom definitions by scope. Standard limits include 50 event and
  25 user dimensions, and 50 event metrics; consult the current limits for
  item dimensions and 360 properties before proposing a write.
  [Configuration limits](https://support.google.com/analytics/answer/12229528?hl=en).
- Links returned by the adapter cover Google Ads, SA360, DV360 and BigQuery.
  Search Console links and data filters return `status: unsupported` and need
  manual inspection in GA4 Admin. Merchant Center links are not fetched.
- Cross-domain settings, unwanted referrals and actual tag deployment are
  manual/browser checks. A stream existing does not prove a tag is deployed.
- Reporting identity uses User-ID, device ID and modeling according to the
  selected mode. Do not describe Google Signals as an identity component.
  [Reporting identity](https://support.google.com/analytics/answer/10976610?hl=en).

## Output

Separate verified configuration, errors and manual checks. Explain relevance
to the property's goals before assigning severity. A missing product link is
not automatically a defect. Return the fetched evidence with each finding.
The query cache lasts 15 minutes; partial error results are not cached.

Cache freshness tolerates up to one second of filesystem clock skew; larger
future timestamps and entries aged 15 minutes or more are misses.

Read the selected reporting identity with
`python scripts/ga4_admin.py --property X --reporting-identity --json`
or MCP `reporting_identity(property_id)`. This alpha read uses the 15-minute
cache and response scrubber. Older SDKs without the method return
`status: unsupported`. Report the selected mode as context for user counts;
there is no identity write or universal recommendation to switch modes.

Google clients: require Data 0.18.16+ and Admin 0.23.0+ (both below 1.0).
Supported Admin calls use explicit beta clients and matching message types;
alpha-only methods keep explicit alpha imports. Reporting identity needs
Admin 0.25.0+ and otherwise returns `status: unsupported`. CI tests minimum
and current Data/Admin clients; newer optional response fields remain optional.

Discover report fields with `ga4_data.py --property X --metadata --json` or
MCP `report_metadata(property_id)`. For an explicit Core report preflight,
use `ga4_data.py --property X --check-compatibility --metrics sessions --dimensions date --json`
or MCP `check_compatibility(property_id, metrics, dimensions)`.
Compatibility is uncached and does not validate funnels or realtime. Metadata
uses the 15-minute cache; successful custom-definition and key-event writes
invalidate it. Both reads scrub responses. No report triggers these reads
automatically. See docs/REPORT_FIELDS.md for filters and limits.
