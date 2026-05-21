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
pytest scripts/ -q
```

Both must pass. CI runs them on every PR across Python 3.10 / 3.11 /
3.12 / 3.13.

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

- Bug fixes with a regression test
- New benchmarks or vertical-specific tables in `scripts/ga4_benchmarks.py`
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
