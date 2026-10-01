# Contributing

Patches welcome. Keep changes small and focused.

## Setup

```
git clone https://github.com/arcbaslow/google-analytics-agent
cd google-analytics-agent
uv venv && uv pip install -e ".[dev]"
# or: python -m venv .venv && pip install -e ".[dev]"
```

## Before you push

```
ruff check scripts/
ruff format --check scripts/
mypy
pytest scripts/ -q --cov=scripts --cov-report=term-missing --cov-fail-under=93
```

All must pass. `.github/workflows/tests.yml` is the source of truth. CI runs them on every PR across Python 3.10 / 3.11 /
3.12 / 3.13, with both the minimum Data/Admin clients and the current resolver
selection. To reproduce the minimum-client job in a separate environment:

```
pip install -e ".[dev]" -c constraints/minimum-google.txt
pip check
```

Then run the four checks above. The constraints cover Data/Admin and the optional BigQuery SDK, not
every transitive dependency. Keep them aligned with the lower bounds in
`pyproject.toml`. Optional reporting-identity contract tests skip on clients
without that method; the unsupported-result test still runs.

Coverage measures production modules only: `scripts/test_*.py` and
`scripts/conftest.py` are omitted by `pyproject.toml`. The floor remains 93%
for both dependency jobs. BigQuery's declared minimum is tested alongside the
Analytics minima. Do not remove production files from the denominator
to accommodate optional SDK methods. Use real SDK messages and client specs
with mocked transports to test request contracts. Optional annotation,
reporting-identity, UPD and advertising fields skip only when absent; their
unsupported behavior is tested separately.

The dev extra includes the optional BigQuery client, SQLGlot and DuckDB for
synthetic in-memory SQL tests. These tests do not submit jobs or use ADC.
They check generated-query semantics after dialect translation; they do not
prove live BigQuery SQL compatibility or cost estimates.

## Commit style

Plain imperative sentence, sentence-case acceptable. No Conventional
Commits prefixes (`feat:`, `fix:`, `chore:`). No `Co-Authored-By:`
trailers, no `Generated with...` footers, no emoji.

Examples of the desired tone:

- `add Open PageRank fallback for missing API key`
- `fix transcript-id uniqueness check off-by-one`
- `pin upper bound on google-analytics-data`
- `rewrite SETUP.md auth section`

PR refs `(#NNN)` only when one exists.

## What I'll accept

The repo is in maintenance mode. New features require an explicit owner
decision, as described in CLAUDE.md. Bugfixes and documentation corrections
do not require a new feature decision.

- Bug fixes with a regression test
- New source-backed benchmarks or vertical-specific tables in `scripts/ga4_benchmarks.py`
- New write surfaces backed by the official Admin API
- Documentation fixes
- CI improvements

## What I'll push back on

- Vendoring proprietary data (Ahrefs, Semrush, Moz beyond their free tiers)
- Adding paid SaaS dependencies
- Removing the multi-runtime instruction files (CLAUDE / AGENTS / GEMINI)
- Big rewrites without a discussion first — open an issue describing the
  shape before the work

## Local-only files

- `.secrets/` — your real credentials. Already gitignored.
- `~/.claude/ga4-credentials.json` — legacy OAuth token.
- `~/.config/gcloud/application_default_credentials.json` — gcloud ADC token.

If you accidentally stage any of these, `git restore --staged <file>`
before committing.

## Tests

Every adapter is mocked. CI never hits a real GA4 property, never burns
API quota, and runs against four Python versions in parallel. Keep it
that way: any test that touches the network must be guarded behind an
env var and skipped by default.

## License

By contributing you agree your changes are released under the MIT
license, same as the rest of the repo.
