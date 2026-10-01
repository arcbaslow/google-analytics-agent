# Audience proposals

`ga4_audience_templates.py` builds definitions locally and validates them
against the installed alpha Audience protobuf schema. It never resolves
credentials or creates an audience. MCP `audience_template` returns the same
definition. All output is scrubbed; inputs changed by scrubbing are rejected
so a proposal cannot silently change meaning.

```sh
python scripts/ga4_audience_templates.py --template event_participants \
  --display-name "Started application" --events application_start
python scripts/ga4_audience_templates.py --template event_parameter_threshold \
  --display-name "High value event" --events purchase --parameter value --threshold 100
python scripts/ga4_audience_templates.py --template event_sequence \
  --display-name "Completed application" --events application_start,application_submit \
  --window-seconds 3600 --membership-days 30
```

The three templates have deliberately explicit semantics:

- `event_participants`: a user triggers the one named event.
- `event_parameter_threshold`: the named event has a numeric parameter
  strictly greater than the threshold in that same event. This is not a
  lifetime-value sum or a measured population percentile. `eventCount` is
  rejected because it has separate aggregate semantics in the public API.
  Verify that the parameter and its type are available for the property.
- `event_sequence`: 2–5 unique events occur in order across sessions within
  the supplied 1–2592000-second window. Other events can occur between steps.

Membership is 1–540 days (default 30). Membership duration is not a lookback
condition or a disengagement interval. Display names are 1–100 characters.
The generated description states the filter meaning. Definitions use the
required top-level AND/OR structure; event-parameter filters use the separate
AND-of-leaves grammar.

Review the JSON and save it as an audience definition if wanted. Creation is
a separate action through `ga4_admin.py --property ID --create-audience FILE`
or the MCP proposal handoff described in [APPROVALS.md](APPROVALS.md). The
existing gate prints the exact definition and requires the user's terminal
`y/N`. Do not chain creation with any other write. No new write path exists.

These are toolkit templates backed by public filters. They do not claim to
reproduce GA4's high-value or disengaged-purchaser UI templates. The release
note alone does not specify those UI conditions, so exact replicas remain
unverified and are not shipped. Protobuf tests validate request structure;
they do not establish live eligibility, field availability or audience size.

Source: [Audience filters, scopes, sequences and numeric values](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1alpha/properties.audiences).
