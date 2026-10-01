# Advertising conversion reports

`ga4_advertising.py` uses the Data API alpha conversion surface. This is
separate from key events and session acquisition reports. Property eligibility
is decided by Google; no live eligibility check was performed during development.
Older supported clients return `unsupported` before resolving credentials.

Discover conversion actions first:

```sh
python scripts/ga4_advertising.py --property 123 --metadata
```

Use the returned `conversion_action` resource names in a report:

```sh
python scripts/ga4_advertising.py --property 123 --start-date 2026-09-01 --end-date 2026-09-30 --metrics allConversionsByConversionDate --dimensions defaultChannelGroup --conversion-actions conversionActions/456 --attribution-model DATA_DRIVEN
```

Omitting `--conversion-actions` requests all available conversions. Model choices
are `DATA_DRIVEN` and `LAST_CLICK`. Dates are explicit. Conversion-date and
interaction-date metrics have different meanings; select their actual schema
names instead of renaming key-event metrics. `section_verified` is true only
when every returned page identifies `SECTION_ADVERTISING`. A warning means
the response has not established that section.

Reads are uncached, scrubbed, and subject to the shared request budget and
`--limit`, `--page-size`, `--max-pages` bounds. Check `complete` before treating
the result as exhaustive. MCP exposes `conversion_metadata` and
`advertising_report` with the same adapters. No conversion settings are changed.

Sources: [conversion reporting basics](https://developers.google.com/analytics/devguides/reporting/data/v1/conversions-api-basics),
[advertising schema](https://developers.google.com/analytics/devguides/reporting/data/v1/conversions-api-schema),
[alpha runReport](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1alpha/properties/runReport).
