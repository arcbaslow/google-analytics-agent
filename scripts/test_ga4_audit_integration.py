"""End-to-end integration tests for the audit orchestrator.

Unlike test_ga4_data_integration.py (which replays recorded *wire* payloads
through the deserialization layer), these tests stub the adapter functions at
their module boundary and drive the real orchestrate() + render_markdown()
code paths. Every analysis "agent" body, the threshold logic, the funnel rate
plumbing, the benchmark enrichment, and the markdown renderer all run for
real — only the I/O adapters (Data API, Admin API, site profiler) are
replaced with canned scenario fixtures.

Two scenarios live under fixtures/audit/:
  - healthy.json : clean property, produces no Critical findings, high confidence
  - problem.json : sampled + direct-heavy + leaky + over-keyed, many findings

Driving both through the same machinery proves the orchestrator wires the
agents together correctly and that severities, confidence, and benchmark
verdicts flow into the rendered report.
"""

import json
from pathlib import Path

import ga4_admin
import ga4_audit
import ga4_context
import ga4_data
import ga4_definitions
import ga4_events
import ga4_funnel
import ga4_report

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def _load_scenario(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _wire(monkeypatch, scenario):
    """Patch every adapter the orchestrator calls so the audit runs offline."""

    monkeypatch.setattr(
        ga4_context, "build_property_context", lambda pid, force=False: scenario["context"]
    )

    def fake_run_report(*args, **kwargs):
        dims = kwargs.get("dimensions") or (args[2] if len(args) > 2 else [])
        metrics = kwargs.get("metrics") or (args[1] if len(args) > 1 else [])
        key = dims[0] if dims else "date"
        # The segments agent reads the channel breakdown with sessions/keyEvents,
        # while attribution reads it with eventCount. Route them to distinct
        # fixtures so each gets the metric shape it expects.
        if key == "sessionDefaultChannelGroup" and "keyEvents" in metrics:
            key = "sessionDefaultChannelGroup_segments"
        return scenario["run_report"][key]

    monkeypatch.setattr(ga4_data, "run_report", fake_run_report)
    # No saved segments in these scenarios; the segments agent exercises cohorts only.
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [])

    monkeypatch.setattr(ga4_events, "list_events", lambda pid, days=7: scenario["list_events"])
    monkeypatch.setattr(
        ga4_events,
        "event_params_coverage",
        lambda pid, event_name, days=7: scenario["event_params_coverage"].get(event_name, {}),
    )

    monkeypatch.setattr(
        ga4_funnel,
        "build_funnel",
        lambda property_id, steps=None, days=28, check_postpayment=False: scenario["build_funnel"],
    )

    monkeypatch.setattr(ga4_admin, "list_key_events", lambda pid: scenario["list_key_events"])
    monkeypatch.setattr(
        ga4_admin, "get_attribution_settings", lambda pid: scenario["attribution_settings"]
    )
    monkeypatch.setattr(ga4_admin, "get_property_details", lambda pid: scenario["property_details"])
    monkeypatch.setattr(ga4_admin, "list_data_streams", lambda pid: scenario["data_streams"])
    monkeypatch.setattr(ga4_admin, "list_data_filters", lambda pid: scenario["data_filters"])
    monkeypatch.setattr(ga4_admin, "list_custom_defs", lambda pid: scenario["custom_defs"])


def _all_findings(agents_output):
    out = []
    for ao in agents_output:
        for f in ao.get("findings", []):
            out.append({**f, "source": ao["agent"]})
    return out


def _titles(findings, severity=None):
    return [f["title"] for f in findings if severity is None or f.get("severity") == severity]


# ---------- healthy scenario ----------


def test_healthy_audit_produces_no_critical_findings(monkeypatch):
    _wire(monkeypatch, _load_scenario("healthy.json"))

    agents_output, context, vertical, confidence = ga4_audit.orchestrate("100001", days=28)

    assert vertical == "ecommerce"
    assert confidence == "high"

    findings = _all_findings(agents_output)
    assert _titles(findings, "Critical") == []

    # Even a healthy funnel surfaces its leakiest step and an overall-CR note.
    high = _titles(findings, "High")
    assert any(t.startswith("Leakiest step") for t in high)
    assert "Overall funnel conversion rate" in _titles(findings, "Low")

    # Full ecomm taxonomy means parameter coverage was actually checked and
    # passed — no coverage findings.
    assert not any("coverage below" in t for t in _titles(findings))

    # Attribution ran (key events exist) and direct share was healthy.
    agents = {ao["agent"] for ao in agents_output}
    assert "ga4-attribution" in agents

    # Segments ran in conversion mode with balanced cohorts -> no underperformers.
    assert "ga4-segments" in agents
    seg = next(ao for ao in agents_output if ao["agent"] == "ga4-segments")
    assert seg["data"]["mode"] == "conversion"
    assert not any(f["title"].startswith("Underperforming") for f in seg["findings"])


def test_healthy_audit_markdown_carries_context_and_benchmarks(monkeypatch):
    _wire(monkeypatch, _load_scenario("healthy.json"))

    agents_output, context, vertical, confidence = ga4_audit.orchestrate("100001", days=28)
    md = ga4_report.render_markdown(
        "100001", agents_output, confidence=confidence, context=context, vertical=vertical
    )

    assert "# GA4 Audit — property 100001" in md
    assert "_Data confidence: **high**_" in md
    assert "_Benchmark vertical: **ecommerce**_" in md
    assert "## Property Context" in md
    assert "## Executive Summary" in md
    assert "## Action Plan" in md
    assert "## Per-Agent Output" in md

    # No Critical section should render for the healthy property.
    assert "### Critical" not in md
    # The overall-CR finding (6%) beats the ecommerce p75 (4.2%) -> good band,
    # and the benchmark verdict is rendered inline.
    assert "vertical ecommerce" in md
    assert "band above_p75" in md


# ---------- problem scenario ----------


def test_problem_audit_flags_every_agent(monkeypatch):
    _wire(monkeypatch, _load_scenario("problem.json"))

    agents_output, context, vertical, confidence = ga4_audit.orchestrate("200002", days=28)

    assert vertical == "ecommerce"
    assert confidence == "low"  # 20% sampling -> low confidence

    findings = _all_findings(agents_output)
    crit = _titles(findings, "Critical")
    high = _titles(findings, "High")
    med = _titles(findings, "Medium")

    # Quality: direct share > 50% is Critical, (not set) > 10% is High, sampling > 10% is High.
    assert "High (direct)/(none) share" in crit
    assert "High (not set) share on sessionSource" in high
    assert "Sampling rate above 10% on 28-day session report" in high

    # Events: only 4/5 ecomm events fire -> partial taxonomy.
    assert "Partial e-commerce taxonomy" in high

    # Funnel: leakiest step is High; the post-payment warning escalates to Critical.
    assert any(t.startswith("Leakiest step") for t in high)
    assert "Funnel warning" in crit

    # Conversions: 31 key events exceeds the 30-event ceiling.
    assert "Too many key events configured" in high

    # Property: short retention is High, a Testing-mode filter is Medium.
    assert "Data retention shorter than 14 months" in high
    assert any("Testing mode" in t for t in med)

    # Attribution: direct share on the primary conversion is over 50% -> Critical.
    assert "Direct share on primary conversion above 30%" in crit

    # Segments: the dominant mobile cohort converts far below the site average.
    assert any(t.startswith("Underperforming") and "mobile" in t for t in high)

    assert len(crit) >= 3


def test_problem_audit_markdown_groups_by_severity(monkeypatch):
    _wire(monkeypatch, _load_scenario("problem.json"))

    agents_output, context, vertical, confidence = ga4_audit.orchestrate("200002", days=28)
    md = ga4_report.render_markdown(
        "200002", agents_output, confidence=confidence, context=context, vertical=vertical
    )

    assert "_Data confidence: **low**_" in md
    assert "### Critical" in md
    assert "### High" in md
    assert "### Medium" in md

    # The Critical section must precede the High section in the action plan.
    assert md.index("### Critical") < md.index("### High") < md.index("### Medium")

    # Benchmark enrichment: 55% direct share is far above the ecommerce p75
    # (32%), a "lower_better" metric -> critical interpretation rendered inline.
    assert "interpretation critical" in md
