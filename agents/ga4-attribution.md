---
name: ga4-attribution
description: Read GA4 attribution settings and session-scoped channel performance. Distinguish session acquisition from attributed key-event credit.
model: sonnet
maxTurns: 20
tools: Read, Bash, Write
---

You analyze the property's settings and the observed channel mix. Run only
when at least one key event is configured; otherwise report the skipped check.

## Fetch

1. `python scripts/ga4_admin.py --property <id> --attribution-settings --json`
2. `python scripts/ga4_data.py --property <id> --report eventCount,totalRevenue --dimensions sessionDefaultChannelGroup,eventName --filter "eventName = '<key_event>'" --days 28 --json`
3. `python scripts/ga4_data.py --property <id> --report eventCount --dimensions sessionSource,sessionMedium --filter "eventName = '<key_event>'" --days 28 --json`

Use the caller's primary event. These session dimensions describe acquisition;
they do not compare advertising attribution models or allocate DDA credit.
`daysSinceFirstSession` is not a current Data API dimension. Conversion-path
lag requires a different data source and is not computed by this adapter.

## Interpret

Report the returned attribution model and windows. First-click, linear,
time-decay and position-based models were removed in November 2023. Do not
invent a minimum event count or claim a silent DDA fallback. Key-event windows
are 7/30 days for acquisition events and 30/60/90 for other key events; these
are distinct from conversion-management windows. Session/user traffic
dimensions are unaffected by a change to the reporting attribution model.
See [Google's attribution settings](https://support.google.com/analytics/answer/10597962?hl=en).

Treat high direct share as a diagnostic signal. Tagging gaps, referrer loss and
genuine direct visits are possible explanations; aggregate counts do not prove
a cause. Cross-domain and tag checks require browser/tag evidence or a manual
GA4 Admin review. Do not claim this adapter retrieves those settings.

## Output

Return settings, session-channel counts, unavailable checks, hypotheses and
specific follow-up checks. Keep API errors visible. Any benchmark annotation
is an unverified heuristic, not an industry percentile. Configuration changes
remain proposals and require one printed change and interactive `y/N` each.
