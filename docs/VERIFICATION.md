# Verification

## Roadmap completion — 2026-10-01

Continued from `52d00f0` on `roadmap-work`. The owner explicitly authorized
all remaining items, including larger implementations. All actionable Now,
Next and Later items are implemented. The previously rejected ideas and
questions about established behavior remain in [ROADMAP.md](ROADMAP.md).
Package version remains 0.5.3. This continuation is committed locally; it
was not pushed, merged, tagged, published or submitted as a pull request.

### Environment and checks

Both environments use Windows and Python 3.12.14. Current clients: Data
0.23.2, Admin 0.30.1, BigQuery 3.45.2. Minimum clients: Data 0.18.16, Admin
0.23.0, BigQuery 3.25.0. The minimum constraints now include BigQuery.
Other transitive dependency minima and intermediate releases were not tested.
The optional BigQuery SDK is free; executing queries against a user's project
can incur charges. No jobs were submitted in this work.

| Check | Starting current | Starting minimum | Final current | Final minimum |
| --- | --- | --- | --- | --- |
| pip check | Pass | Pass | Pass | Pass |
| Ruff lint/format | Pass, 44 files | Pass, 44 files | Pass, 65 files | Pass, 65 files |
| Mypy | Pass, 13 source files | Pass, 13 source files | Pass, 19 source files | Pass, 19 source files |
| Mocked tests | 529 passed, 1 skipped | 526 passed, 4 skipped | 723 passed, 1 skipped | 715 passed, 9 skipped |
| Coverage | 96.25%, includes tests | 95.86%, includes tests | 94.52%, production only | 93.63%, production only |

The coverage percentages use different denominators: the final configuration
omits test modules and conftest, retaining the same 93% floor. All production
modules remain included, including optional alpha paths. Skips reflect SDK
capabilities; unsupported-result tests still run. The minimum environment
emits two upstream protobuf 4 deprecation warnings about Python 3.14, which
is outside the configured CI matrix. Mypy passes with its existing settings;
untyped function bodies are not fully checked.

The checks follow `.github/workflows/tests.yml`: pip check, Ruff lint, Ruff
format, mypy, and pytest with coverage. Every commit followed passing checks
in both environments. An external pytest guard kept synthetic credential
file IO in memory, disabled ADC discovery, and blocked socket connections.
No credential files or `.secrets/` were read, created or staged. Temporary
SQL fixtures, cache tests and reports used isolated test directories or
memory. No live GA4 property, auth flow, write or BigQuery job was used.

New tests include all 15 real Admin request contracts, SDK response parsing,
refusal/expiry/replay and post-prompt proposal binding, cache identity and
cross-process invalidation, SQL denominator/sequence semantics on synthetic
in-memory rows, DNS address pinning with original TLS hostname verification,
and Windows CSV newline behavior. The runtime instruction additions match
across AGENTS.md, CLAUDE.md and GEMINI.md. Local documentation links and
`git diff --check` pass.

### Implementation commits in this continuation

| Commit | Change |
| --- | --- |
| `34c2433` | Correct parameter coverage and session key-event rates |
| `1080a0d` | Bound pagination and validate saved-report options |
| `03c77bf` | Preserve funnel intent and parse API step totals |
| `2051db0` | Bound read retries and classify API failures |
| `4ee3dc9` | Isolate cached reads and prevent stale concurrent refills |
| `97570b3` | Read consent settings and identify missing evidence |
| `43930e9` | Respect custom key-event limits and granted edit scopes |
| `909a8b4` | Bind MCP proposals to single-use terminal approval |
| `68c43ca` | Add bounded alpha advertising conversion reports |
| `4578a44` | Add cost-bounded BigQuery aggregate evidence |
| `5b396f0` | Add realtime and same-property comparisons |
| `a84fe41` | Read annotations and scoped configuration history |
| `52a7645` | Build validated audience-template proposals |
| `e2b1da2` | Pin context fetches to validated public addresses |
| `b3475d5` | Bound account/property discovery reads |
| `ebfd437` | Preserve CSV line endings when saving reports |
| `cb9dd44` | Enforce production-only coverage and real SDK contracts |
| `d448326` | Preserve saved-comparison resource identifiers |
| `7a7ea76` | Test the minimum supported BigQuery client |

The final documentation commit records this review; its hash is in the branch log.

### Deliberately unbuilt or unverified

- Static FX defaults remain unchanged: there is no sourced historical-rate
  dataset or established base-currency feature contract.
- Unknown fields in Admin JSON remain ignored because an existing regression
  test explicitly requires that behavior. Strict parsing needs an owner
  decision; unknown proposal fields are not sent to the API.
- Duplicate user/default dimension ordering remains a question: no service
  rejection was established, so ordering semantics were left unchanged.
- Exact lifecycle UI audience replicas are not shipped: published release
  notes do not define their conditions. Public-filter templates are shipped.
- Autonomous/batched writes, `--yes`, audience-member exports, paid benchmark
  feeds, a hosted dashboard and a replacement framework remain rejected.
  The alpha conversational API remains unnecessary overlap with the agent.
- Benchmark cells still lack defensible per-cell public provenance and remain
  labeled unverified heuristics. No replacement numbers were invented.
- Live roles/scopes, quotas, property-specific compatibility, propagation,
  alpha eligibility, audience populations and end-to-end writes remain
  unverified. BigQuery SQL was translated and executed offline; live SQL
  acceptance, export completeness, IAM and billing were not verified.
- Local checks cover Windows/Python 3.12 only. The configured Ubuntu matrix
  on Python 3.10–3.13 was not executed remotely. Competitor offerings were
  researched from public sources, not installed or security-audited.
- PII scrubbing is heuristic. Existing user caches were not inspected. Role
  revocation and shared-disk invalidation failures can leave cached data until
  expiry. Context uses the OS DNS resolver; its resolution latency is not a
  Python-controlled deadline, and proxy-only sites are intentionally unsupported.

The sections below are historical records and describe the scope and limits
at those earlier checkpoints.

## Next: report field discovery — 2026-09-30

Continued after `74a3335`, which completed the Google client compatibility
item. Added explicit beta `getMetadata` and `checkCompatibility` adapters,
CLI actions and MCP tools. The API contracts and limitations are documented
with official sources in [REPORT_FIELDS.md](REPORT_FIELDS.md).

The 31 new mocked tests use real request/response messages. They cover
field names/types, empty lists, privacy in output and disk cache, property
isolation, cache bypass, filter precedence, CLI dispatch and action conflicts,
scrubbed quota/API errors, and the absence of automatic preflight calls.
All six custom-definition/key-event writes are checked for metadata-cache
invalidation after success and preservation after failure or refusal. Each
write still prompts once; no live API or real credentials were used.

| Check | Minimum Data/Admin | Current Data/Admin |
| --- | --- | --- |
| Versions | 0.18.16 / 0.23.0 | 0.23.2 / 0.30.1 |
| `pip check` | Pass | Pass |
| Ruff lint and format | Pass, 44 files | Pass, 44 files |
| Mypy | Pass, 13 source files | Pass, 13 source files |
| Mocked pytest with CI coverage floor | 526 passed, 4 skipped | 529 passed, 1 skipped |
| Coverage | 95.86% | 96.25% |

The starting current-client baseline for this continuation was 495 passed
and 96.07%. Skips and local environment limits are as described below. The
coverage floor remains 93%, and the denominator still includes tests.
All checks passed before each local implementation commit. No push or release.

Unbuilt Next items retain their roadmap rationale: pagination and saved-report
limits need a contract; metric/funnel semantics need decisions; quota/retry,
cache identity and MCP approval work need broader designs. Consent diagnostics,
key-event limit verification and coverage policy remain queued. No Later
features were added. Live field availability, compatibility, permissions and
propagation remain deliberately unverified; local tests ran only on Python
3.12.14/Windows, with the external no-network/no-credential-file guard.

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
