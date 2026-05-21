# Security policy

## Reporting a vulnerability

Open a private security advisory on the repo:
https://github.com/arcbaslow/google-analytics-agent/security/advisories/new

Please do not file public issues for security problems.

## What's in scope

- Credential handling in `scripts/ga4_auth.py` and any path that touches
  `~/.claude/ga4-credentials.json` or gcloud ADC files
- PII handling in `scripts/ga4_utils.py` (the `scrub_pii` denylist +
  regex pass)
- Any code path that sends user data to a third-party endpoint
- Any command that performs an Admin API write (event rules, audiences,
  custom defs, key events) without an explicit confirmation prompt
- Dependency-chain vulnerabilities in the Google client libraries
  pinned in `scripts/requirements.txt`

## What's out of scope

- Misuse of the toolkit against a property you do not own
- Bugs in the upstream Google APIs themselves — report those to Google
- Issues that require an attacker with shell access to the user's
  machine (they already own `~/.claude/`)

## Where credentials live on disk

- gcloud ADC (default path):
  `~/.config/gcloud/application_default_credentials.json`
- Legacy OAuth (fallback path):
  `~/.claude/ga4-credentials.json` (file mode `0600` on POSIX)
- Service account / external account:
  `GOOGLE_APPLICATION_CREDENTIALS` env var

The toolkit never logs credentials to stdout, never sends them to a
third party, and never bakes them into report files. Cached API
responses under `~/.claude/ga4-cache/` are scrubbed of PII (emails,
phone numbers, ID-like keys) before being written.

## Disclosure timeline

I aim to acknowledge security reports within 7 days and ship a fix or
mitigation within 30 days. For high-severity issues affecting active
users, both windows shrink.
