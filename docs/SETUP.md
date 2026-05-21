# Setup

The default auth path uses Google's own ADC flow through gcloud. You do not
need to create a Cloud OAuth client of your own. The fallback path
(client-secret JSON) is only there for environments where gcloud cannot be
installed.

## 1. Install gcloud

[Cloud SDK install docs](https://cloud.google.com/sdk/docs/install). On macOS
via Homebrew: `brew install --cask google-cloud-sdk`. On Windows: download
the installer from the Cloud SDK page.

Verify:

```
gcloud --version
```

## 2. Enable APIs on any Cloud project you have access to

The project doesn't need to be dedicated to this plugin. You just need a
project where the GA4 Data and Admin APIs are enabled, because user ADC
needs a "quota project" to bill API calls against.

```
gcloud config set project <PROJECT_ID>
gcloud services enable analyticsdata.googleapis.com analyticsadmin.googleapis.com
```

## 3. Install Python deps

The fastest path is [`uv`](https://github.com/astral-sh/uv):

```
uv venv
uv pip install -r scripts/requirements.txt
```

Or plain `pip`:

```
python -m venv .venv
source .venv/bin/activate              # or .venv\Scripts\Activate.ps1 on Windows
pip install -r scripts/requirements.txt
```

For PDF report rendering (optional — markdown is the default):

```
pip install -e ".[pdf]"
```

For development (running tests, lint):

```
pip install -e ".[dev]"
```

## 4. Authenticate (default path: gcloud ADC)

For read-only analysis:

```
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/analytics.readonly,\
https://www.googleapis.com/auth/cloud-platform
```

For write features (audiences, event rules, custom dims, key events), include
`analytics.edit`:

```
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/analytics.edit,\
https://www.googleapis.com/auth/cloud-platform
```

Set the quota project:

```
gcloud auth application-default set-quota-project <PROJECT_ID>
```

Verify the plugin can resolve credentials:

```
python scripts/ga4_auth.py --check
python scripts/ga4_auth.py --properties
```

If you forget the gcloud command, the plugin can print it:

```
python scripts/ga4_auth.py --adc          # read scope
python scripts/ga4_auth.py --adc --write  # write scope
```

## 5. Grant GA4 property access

For each GA4 property you want to analyze, ensure the Google account you
authenticated with above has at least Viewer access at the property level.
This is granted in the GA4 UI, separately from Cloud IAM:

> Property → Property Settings → Property Access Management

Marketer or Analyst roles may be insufficient for some Admin API reads
(data filters, attribution settings). Viewer or higher is recommended for
the read path; Editor or higher for writes.

## 6. Try a single command

```
python scripts/ga4_events.py --property 123456789 --list-events --days 7 --json
```

If events come back, you're set.

## 7. Profile the property (recommended first step)

Before any audit, run the context profiler. It reads the property's
web-stream URL, fetches the live site, and caches a profile of vertical,
platform, framework, and sitemap shape that every other audit attaches
to:

```
python scripts/ga4_context.py --property 123456789 --analyze --json
```

The result is stored under `~/.claude/ga4-context/<id>.json`. Audits
read it automatically; pass `--vertical <name>` to any audit to override
the inferred vertical when picking benchmark bands.

## 8. Run the full audit

From any runtime (Codex, Gemini CLI, plain shell):

```
python scripts/ga4_audit.py --property 123456789 --output audit.md
```

The driver runs context → quality → events → funnel → conversions →
property (and attribution if any key events are configured), then
renders a markdown report (`--format md`, default) with benchmark
verdicts attached to every quantified finding. Pass `--format html` or
`--format pdf` for the other renderings.

From inside Claude Code:

```
/ga4 audit 123456789
```

This goes through the LLM-powered specialist agents and produces a
richer report. The mechanical driver above is the same shape but
deterministic, useful in CI or under runtimes without subagent support.

## 9. Inspect industry benchmarks

```
python scripts/ga4_benchmarks.py --list-verticals
python scripts/ga4_benchmarks.py --vertical ecommerce --all-metrics
python scripts/ga4_benchmarks.py --compare bounce_rate 0.74 --vertical ecommerce
```

Numbers are conservative directional estimates from public industry
reports (Contentsquare, WordStream, Unbounce, Statista) as of late 2025.
Treat them as order-of-magnitude markers; your own property history is
the better long-term reference.

## Fallback: BYO OAuth client

If you cannot install gcloud (for example, CI without sudo, or a locked-down
workstation), register your own Cloud OAuth client and feed it to the
plugin:

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project, or pick an existing one
3. APIs & Services → Library: enable Google Analytics Data API and Admin API
4. APIs & Services → Credentials → Create Credentials → OAuth client ID
5. If prompted, configure the OAuth consent screen:
   - User type: External (or Internal if you have Workspace)
   - App name: anything (e.g. `claude-ga4-agents`)
   - User support email: yours
   - Scopes: leave default; the plugin requests them at flow time
   - Test users: add your own Google account email
6. Application type: Desktop app
7. Download the JSON credentials file
8. Authenticate the plugin:

```
python scripts/ga4_auth.py --oauth --client-secret-file /path/to/client_secret_xxx.json
```

For write scope, add `--write`:

```
python scripts/ga4_auth.py --oauth --write --client-secret-file /path/to/client_secret_xxx.json
```

Credentials are stored at `~/.claude/ga4-credentials.json` with file mode
0600 on POSIX. Refresh tokens expire after 6 months of inactivity or if you
revoke access in the Google Account permissions page.

## Troubleshooting

**`403 Forbidden` from Data API**
Verify the Data API is enabled on your quota project and the authenticated
account has at least Viewer access on the GA4 property.

**`403 Forbidden` from Admin API**
Same as above for the Admin API. Some Admin calls require Editor at the
property level (audiences, event rules, custom defs, key events).

**`PermissionDenied: User does not have serviceusage.services.use`**
Quota project not set or the account lacks permission on it. Run
`gcloud auth application-default set-quota-project <PROJECT_ID>` against a
project you own.

**Token refresh fails (legacy OAuth path)**
Refresh tokens expire after 6 months of inactivity, or if revoked. Re-run
`--oauth` to get a fresh one.

**"Access blocked: claude-ga4-agents has not completed verification"**
Your OAuth client is in Testing mode and your account isn't on the test
users list. Add your email under OAuth consent screen → Test users, or
publish the OAuth app (Internal apps don't need verification).

**Quota exceeded**
See `skills/ga4/references/quotas.md`. Standard properties: 25,000 tokens
per property per day, 5,000 per property per hour. Adapter responses are
cached for 15 minutes to reduce repeated calls during analysis.
