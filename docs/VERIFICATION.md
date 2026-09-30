# Verification

## Next: Google client compatibility — 2026-09-30

Continued on `roadmap-work` at the owner's request to work through the roadmap.
Starting commit: `2393862`. Baseline checks passed again: 495 tests, 96.07%
coverage, Ruff lint/format and mypy. No live GA4 calls or credential-file IO.
The external offline guard described below was used for every test run.

An isolated environment with the old declared floors (Data 0.18.0, Admin
0.22.0) reproduced missing `EventEditRule` and `ReportingIdentitySettings`
imports during collection. Class inspection found no `KeyEvent` on either
Admin surface. The Data integration subset had one failure and five passes:
`samplingMetadatas` could not be parsed into the old response type.

The new floors are Data 0.18.16 and Admin 0.23.0, based on the upstream
[Data](https://github.com/googleapis/google-cloud-python/blob/main/packages/google-analytics-data/CHANGELOG.md)
and [Admin](https://github.com/googleapis/google-cloud-python/blob/main/packages/google-analytics-admin/CHANGELOG.md)
release histories and the passing tests below. Reporting identity remains
optional below Admin 0.25.0. Request tests now construct real beta request
messages from adapter arguments; client factories are mocked and checked
for the explicit surface and credential scope.

| Check | Minimum Data/Admin | Current Data/Admin |
| --- | --- | --- |
| Versions | 0.18.16 / 0.23.0 | 0.23.2 / 0.30.1 |
| `pip check` | Pass | Pass |
| Ruff lint and format | Pass, 43 files | Pass, 43 files |
| Mypy | Pass, 13 source files | Pass, 13 source files |
| Mocked pytest with CI coverage floor | 495 passed, 4 skipped | 498 passed, 1 skipped |
| Coverage | 95.72% | 96.12% |

Four minimum-client skips cover optional identity responses; the real old
client's unsupported-result test passes there and skips with current clients.
The minimum environment reports two upstream protobuf 4 deprecation warnings.
Both local environments use Windows and Python 3.12.14. CI now defines
minimum/current jobs on all four existing Python versions, but was not run
remotely. Other dependency floors, intermediate versions and live API behavior
remain unverified. No dependency upper bounds or package version changed.

To reproduce the minimum environment, install `.[dev]` with
`-c constraints/minimum-google.txt`, then run `pip check` and the four CI
checks. The constraints limit the two Analytics clients only. The local
pytest command adds `-p offline_guard` with the same `PYTHONPATH` as below.

## Roadmap work — 2026-09-30

Local branch: `roadmap-work`, created from master `aec65cb`. Package version
remains 0.5.3. No push, PR, tag, release or publication was performed.

The full AGENTS.md, CLAUDE.md, GEMINI.md and CONTRIBUTING.md were read before
the README, changelog, security policy, docs, workflows, adapters and matching
wrappers. The owner explicitly authorized the bounded feature run. The Python
adapters remained the source of truth; no replacement framework was added.

### Environment and checks

A fresh `.venv` was created with Python 3.12.14 on Windows and installed with
`python -m pip install -e ".[dev]"`. Resolved Google libraries: Data 0.23.2,
Admin 0.30.1, google-auth 2.59.0, google-auth-oauthlib 1.5.0. Tooling: Ruff
0.16.9, mypy 2.3.1, pytest 9.1.1, pytest-cov 7.1.0, MCP 1.30.0.

`.github/workflows/tests.yml` defines the checks below. Each passed before
each local commit. CI itself was not triggered.

| Check | Baseline | Final implementation |
| --- | --- | --- |
| `python -m ruff check scripts/` | Pass | Pass |
| `python -m ruff format --check scripts/` | Pass, 36 files | Pass, 43 files |
| `python -m mypy` | Pass, 13 source files | Pass, 13 source files |
| `pytest scripts/ -q --cov=scripts --cov-report=term-missing --cov-fail-under=93` | 366 passed | 495 passed |
| Coverage under CI configuration | 95.41% | 96.07% |
| Production-only coverage, same run | 91.68% (2249/2453) | 92.54% (2468/2667) |

The CI denominator includes test modules. Production-only coverage excludes
`test_*.py` and `conftest.py`; no coverage configuration or floor was changed.
Mypy still reports that untyped function bodies are not checked by default.
Python 3.10, 3.11, 3.13 and Ubuntu were not exercised locally. The separate
release workflow's packaging/publishing path was not run for this branch.

To honor the no-credentials-file constraint, this review used an external
pytest plugin, `../ga4-review-tools/offline_guard.py`, outside the repository.
It intercepted synthetic `ga4-credentials.json` IO in memory, blocked access
to `.secrets/`, disabled ADC discovery, and blocked socket connections.
Existing auth tests could still replace the mocked auth functions themselves.
No live GA4 property or real credential file was accessed. The final context
tests also stub DNS. The helper and its coverage JSON are local review aids,
not project dependencies or staged files.

The actual local test command, from the repository in PowerShell, was:

```powershell
$env:PYTHONPATH = 'C:\Program Data\Repository\ga4-review-tools'
.\.venv\Scripts\python.exe -m pytest -p offline_guard scripts/ -q --cov=scripts --cov-report=term-missing --cov-fail-under=93
```

### Commits and scope

| Commit | Change |
| --- | --- |
| `fef9cff` | Record the evidence-backed Now/Next/Later roadmap |
| `b0caabd` | Require interactive approval at all Admin write boundaries |
| `7b3cf94` | Scrub responses and use one filtered saved-report request |
| `3e5d4d9` | Recover from cache corruption, errors and stale entries |
| `15dab92` | Align property checks with public Admin resource contracts |
| `af730fc` | Validate redirect destinations before following them |
| `583f771` | Mark incomplete quality checks and preserve metadata |
| `d36ad80` | Correct wrapper claims and label heuristic benchmarks |
| `ccb0c61` | Allow small filesystem clock skew in cache freshness |
| `091d723` | Add the read-only reporting-identity CLI/MCP surface |

Regression coverage includes all 15 write gates, no-write refusal/EOF/interrupt
paths, MCP stdin protection, privacy boundaries, real protobuf contracts,
corrupt and empty cache entries, cache invalidation failures, redirect hops,
failed quality queries, zero sampling and identity reads. Tests use mocks or
synthetic messages, not live property mutations.

All Now items are implemented. Larger reporting changes, metric-meaning and
funnel-policy questions, minimum-client compatibility, quota retry design,
cache principal isolation, consent diagnostics and an MCP approval channel
remain in [ROADMAP.md](ROADMAP.md). BigQuery, advertising conversions, realtime,
annotations and audience-template expansion are Later work because they add
new semantics, cost/permission concerns or broader interfaces.

### What remains unverified

- The exact public provenance of benchmark cells. Values are unchanged and
  labeled `unverified_heuristic`; no paid/proprietary data was copied.
- Live API permissions, edit scopes, quota behavior, propagation, eligibility
  and property-specific dimension/metric combinations.
- The minimum versions permitted by the dependency ranges and all CI platforms.
- Competitor execution and security: comparisons used public source/docs.
- No past-year BigQuery export schema migration affecting this adapter was
  established. Product/UI releases do not establish public API availability.
- PII scrubbing remains heuristic. Existing user caches were not inspected or
  migrated. Cache principal isolation, in-flight invalidation races and DNS
  rebinding require separate designs recorded in the roadmap.

## Historical release verification — v0.5.2

Date: 2026-09-08. Local environment: Windows, Python 3.12.14; Node.js 24 for GTM Diff.

358 tests passed. The existing CI coverage command reported 95.11%, above its 93% floor. Ruff, formatting and mypy passed. This coverage configuration includes test modules under scripts/.

| Check | Command | Result |
| --- | --- | --- |
| Tests and coverage | `python -m pytest scripts/ -q --cov=scripts --cov-report=term-missing --cov-fail-under=93` | Passed |
| Ruff | `python -m ruff check scripts/` | Passed |
| Format | `python -m ruff format --check scripts/` | Passed |
| Mypy | `python -m mypy` | Passed |

## Documentation and examples

- Executed the offline example commands from README against committed synthetic fixtures.
- Captured the generated output in a browser. Screenshots are output previews, not live dashboards.
- Checked local README links, SVG syntax, image presence, release versions and whitespace.
- Built the release artifacts before publishing. Source archives contain only tracked repository files.

## Scope

The test results above are a dated local run, not a claim that every test was run locally on every CI platform. API responses are mocked where tests require them. Live authentication, account mutations, external-service behavior and paid AI calls were not exercised. The CI badge links to the actual workflow rather than a static passing label.

## Build artifacts

Source distribution and wheel built successfully; `twine check` passed. The offline report/extraction example also passed after loading the module from the extracted wheel, outside the repository.
