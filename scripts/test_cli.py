"""CLI entry-point tests.

Each ga4_*.py exposes a main() that parses argv and dispatches to the
already-tested library functions. These tests drive main() with a mocked
argv and stubbed adapters to cover the argparse wiring, the dispatch
branches, and the error/return-code paths. No network, no real auth.
"""

import json
import sys

import ga4_admin
import ga4_audit
import ga4_auth
import ga4_benchmarks
import ga4_context
import ga4_data
import ga4_definitions
import ga4_events
import ga4_funnel
import ga4_report
import pytest


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["prog", *args])


# ---------- ga4_data ----------


def test_data_main_report(monkeypatch, capsys):
    monkeypatch.setattr(ga4_data, "run_report", lambda *a, **k: {"rows": [{"x": "1"}]})
    _argv(monkeypatch, "--property", "123", "--report", "sessions", "--dimensions", "date")
    assert ga4_data.main() == 0
    assert "rows" in capsys.readouterr().out


def test_data_main_funnel(monkeypatch):
    monkeypatch.setattr(ga4_data, "run_funnel_report", lambda *a, **k: {"steps": ["a", "b"]})
    _argv(monkeypatch, "--property", "123", "--funnel-report", "--steps", "a,b")
    assert ga4_data.main() == 0


def test_data_main_funnel_requires_steps(monkeypatch):
    _argv(monkeypatch, "--property", "123", "--funnel-report")
    assert ga4_data.main() == 1


def test_data_main_requires_report(monkeypatch):
    _argv(monkeypatch, "--property", "123")
    assert ga4_data.main() == 1


def test_data_main_handles_exception(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(ga4_data, "run_report", boom)
    _argv(monkeypatch, "--property", "123", "--report", "sessions")
    assert ga4_data.main() == 1


# ---------- ga4_funnel ----------


def test_funnel_main_explicit_steps(monkeypatch):
    monkeypatch.setattr(ga4_funnel, "build_funnel", lambda **k: {"steps": k["steps"]})
    _argv(monkeypatch, "--property", "123", "--steps", "view_item,purchase")
    assert ga4_funnel.main() == 0


def test_funnel_main_default_preset(monkeypatch):
    seen = {}
    monkeypatch.setattr(ga4_funnel, "build_funnel", lambda **k: seen.update(k) or {"ok": True})
    _argv(monkeypatch, "--property", "123")
    assert ga4_funnel.main() == 0
    assert seen["steps"] == list(ga4_funnel.ECOMM_FUNNEL_PRESET)


def test_funnel_main_handles_exception(monkeypatch):
    def boom(**k):
        raise RuntimeError("nope")

    monkeypatch.setattr(ga4_funnel, "build_funnel", boom)
    _argv(monkeypatch, "--property", "123", "--steps", "a,b")
    assert ga4_funnel.main() == 1


# ---------- ga4_context ----------


def test_context_main_url(monkeypatch):
    monkeypatch.setattr(ga4_context, "analyze_website", lambda url: {"url": url})
    _argv(monkeypatch, "--url", "https://example.com")
    assert ga4_context.main() == 0


def test_context_main_show_present(monkeypatch):
    monkeypatch.setattr(ga4_context, "load_context", lambda pid: {"site": {"summary": "s"}})
    _argv(monkeypatch, "--property", "123", "--show")
    assert ga4_context.main() == 0


def test_context_main_show_missing(monkeypatch, capsys):
    monkeypatch.setattr(ga4_context, "load_context", lambda pid: None)
    _argv(monkeypatch, "--property", "123", "--show")
    assert ga4_context.main() == 0
    assert "no context cached" in capsys.readouterr().out


def test_context_main_delete(monkeypatch):
    monkeypatch.setattr(ga4_context, "delete_context", lambda pid: {"status": "deleted"})
    _argv(monkeypatch, "--property", "123", "--delete")
    assert ga4_context.main() == 0


def test_context_main_analyze_requires_property(monkeypatch):
    _argv(monkeypatch, "--analyze")
    assert ga4_context.main() == 1


def test_context_main_no_action_prints_help(monkeypatch):
    _argv(monkeypatch, "--property", "123")
    assert ga4_context.main() == 1


# ---------- ga4_events ----------


def test_events_main_list(monkeypatch):
    monkeypatch.setattr(ga4_events, "list_events", lambda pid, days: {"rows": []})
    _argv(monkeypatch, "--property", "123", "--list-events")
    assert ga4_events.main() == 0


def test_events_main_check(monkeypatch):
    monkeypatch.setattr(ga4_events, "check_events", lambda pid, names, days: {"events": {}})
    _argv(monkeypatch, "--property", "123", "--check-events", "purchase,sign_up")
    assert ga4_events.main() == 0


def test_events_main_event_params(monkeypatch):
    monkeypatch.setattr(ga4_events, "event_params_coverage", lambda pid, ev, days: {"event": ev})
    _argv(monkeypatch, "--property", "123", "--event-params", "purchase")
    assert ga4_events.main() == 0


def test_events_main_detect_postpayment(monkeypatch):
    monkeypatch.setattr(ga4_events, "detect_postpayment_api", lambda pid, days: {"verdict": "ok"})
    _argv(monkeypatch, "--property", "123", "--detect-postpayment-api")
    assert ga4_events.main() == 0


def test_events_main_no_action_prints_help(monkeypatch):
    _argv(monkeypatch, "--property", "123")
    assert ga4_events.main() == 1


def test_events_main_handles_exception(monkeypatch):
    def boom(pid, days):
        raise RuntimeError("x")

    monkeypatch.setattr(ga4_events, "list_events", boom)
    _argv(monkeypatch, "--property", "123", "--list-events")
    assert ga4_events.main() == 1


# ---------- ga4_benchmarks (pure, no mocks needed) ----------


def test_benchmarks_main_list_verticals(monkeypatch):
    _argv(monkeypatch, "--list-verticals")
    assert ga4_benchmarks.main() == 0


def test_benchmarks_main_compare(monkeypatch):
    _argv(monkeypatch, "--compare", "bounce_rate", "0.5", "--vertical", "ecommerce")
    assert ga4_benchmarks.main() == 0


def test_benchmarks_main_compare_non_numeric(monkeypatch):
    _argv(monkeypatch, "--compare", "bounce_rate", "notanumber")
    assert ga4_benchmarks.main() == 1


def test_benchmarks_main_vertical(monkeypatch):
    _argv(monkeypatch, "--vertical", "ecommerce")
    assert ga4_benchmarks.main() == 0


def test_benchmarks_main_vertical_all_metrics(monkeypatch):
    _argv(monkeypatch, "--vertical", "ecommerce", "--all-metrics")
    assert ga4_benchmarks.main() == 0


def test_benchmarks_main_no_args_prints_help(monkeypatch):
    _argv(monkeypatch)
    assert ga4_benchmarks.main() == 1


# ---------- ga4_admin ----------


@pytest.mark.parametrize(
    "flag,attr,retval",
    [
        ("--details", "get_property_details", {"displayName": "x"}),
        ("--streams", "list_data_streams", []),
        ("--enhanced-measurement", "get_enhanced_measurement", []),
        ("--data-filters", "list_data_filters", []),
        ("--custom-defs", "list_custom_defs", {}),
        ("--key-events", "list_key_events", []),
        ("--attribution-settings", "get_attribution_settings", {}),
        ("--links", "list_platform_links", {}),
        ("--list-audiences", "list_audiences", []),
    ],
)
def test_admin_main_read_flags(monkeypatch, flag, attr, retval):
    monkeypatch.setattr(ga4_admin, attr, lambda *a, **k: retval)
    _argv(monkeypatch, "--property", "123", flag)
    assert ga4_admin.main() == 0


def test_admin_main_add_key_event(monkeypatch):
    monkeypatch.setattr(ga4_admin, "create_key_event", lambda *a, **k: {"name": "ke"})
    _argv(monkeypatch, "--property", "123", "--add-key-event", "purchase")
    assert ga4_admin.main() == 0


def test_admin_main_add_custom_dim(monkeypatch):
    monkeypatch.setattr(ga4_admin, "create_custom_dimension", lambda *a, **k: {"name": "d"})
    _argv(
        monkeypatch,
        "--property",
        "123",
        "--add-custom-dim",
        "--parameter-name",
        "brand",
        "--display-name",
        "Brand",
    )
    assert ga4_admin.main() == 0


def test_admin_main_archive_audience(monkeypatch):
    monkeypatch.setattr(ga4_admin, "archive_audience", lambda name: {"status": "archived"})
    _argv(monkeypatch, "--audience-name", "properties/1/audiences/5", "--archive-audience")
    assert ga4_admin.main() == 0


def test_admin_main_no_action_prints_help(monkeypatch):
    _argv(monkeypatch, "--property", "123")
    assert ga4_admin.main() == 1


def test_admin_main_handles_exception(monkeypatch):
    def boom(pid):
        raise RuntimeError("denied")

    monkeypatch.setattr(ga4_admin, "get_property_details", boom)
    _argv(monkeypatch, "--property", "123", "--details")
    assert ga4_admin.main() == 1


# ---------- ga4_definitions ----------


def test_definitions_main_save_segment(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_definitions, "save_segment", lambda *a, **k: tmp_path / "s.json")
    _argv(
        monkeypatch,
        "--save-segment",
        "buyers",
        "--field",
        "eventName",
        "--op",
        "EXACT",
        "--value",
        "purchase",
    )
    assert ga4_definitions.main() == 0


def test_definitions_main_save_segment_in_list(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_definitions, "save_segment", lambda *a, **k: tmp_path / "s.json")
    _argv(
        monkeypatch,
        "--save-segment",
        "us",
        "--field",
        "country",
        "--op",
        "IN",
        "--values",
        "US,CA",
    )
    assert ga4_definitions.main() == 0


def test_definitions_main_save_segment_bad_args(monkeypatch):
    _argv(monkeypatch, "--save-segment", "x", "--field", "eventName")
    assert ga4_definitions.main() == 1


def test_definitions_main_list_segments(monkeypatch):
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [{"name": "a"}])
    _argv(monkeypatch, "--list-segments")
    assert ga4_definitions.main() == 0


def test_definitions_main_run_report_requires_property(monkeypatch):
    _argv(monkeypatch, "--run-report", "weekly")
    assert ga4_definitions.main() == 1


def test_definitions_main_run_report(monkeypatch):
    monkeypatch.setattr(ga4_definitions, "run_report_def", lambda *a, **k: {"rows": []})
    _argv(monkeypatch, "--run-report", "weekly", "--property", "123")
    assert ga4_definitions.main() == 0


def test_definitions_main_writes_output_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_definitions, "list_segments", lambda: [{"name": "a"}])
    out = tmp_path / "segs.json"
    _argv(monkeypatch, "--list-segments", "--output", str(out))
    assert ga4_definitions.main() == 0
    assert out.exists()


def test_definitions_main_no_action_prints_help(monkeypatch):
    _argv(monkeypatch)
    assert ga4_definitions.main() == 1


# ---------- ga4_auth ----------


def test_auth_main_adc(monkeypatch, capsys):
    _argv(monkeypatch, "--adc")
    assert ga4_auth.main() == 0
    assert "gcloud auth application-default login" in capsys.readouterr().out


def test_auth_main_adc_write(monkeypatch, capsys):
    _argv(monkeypatch, "--adc", "--write")
    assert ga4_auth.main() == 0
    assert "analytics.edit" in capsys.readouterr().out


def test_auth_main_quota_project(monkeypatch):
    monkeypatch.setattr(ga4_auth, "set_quota_project", lambda pid: {"status": "ok"})
    _argv(monkeypatch, "--quota-project", "proj-1")
    assert ga4_auth.main() == 0


def test_auth_main_check_ok(monkeypatch):
    monkeypatch.setattr(ga4_auth, "check_auth", lambda: True)
    _argv(monkeypatch, "--check")
    assert ga4_auth.main() == 0


def test_auth_main_check_fail(monkeypatch):
    monkeypatch.setattr(ga4_auth, "check_auth", lambda: False)
    _argv(monkeypatch, "--check")
    assert ga4_auth.main() == 1


def test_auth_main_properties(monkeypatch):
    monkeypatch.setattr(ga4_auth, "list_properties", lambda: [{"property_id": "1"}])
    _argv(monkeypatch, "--properties")
    assert ga4_auth.main() == 0


def test_auth_main_properties_auth_error(monkeypatch):
    def _raise():
        raise ga4_auth.AuthRequiredError("run gcloud")

    monkeypatch.setattr(ga4_auth, "list_properties", _raise)
    _argv(monkeypatch, "--properties")
    assert ga4_auth.main() == 1


def test_auth_main_oauth_requires_client_secret(monkeypatch):
    _argv(monkeypatch, "--oauth")
    assert ga4_auth.main() == 1


def test_auth_main_oauth(monkeypatch):
    monkeypatch.setattr(ga4_auth, "run_oauth_flow", lambda path, write=False: {"token": "t"})
    _argv(monkeypatch, "--oauth", "--client-secret-file", "/tmp/secret.json")
    assert ga4_auth.main() == 0


def test_auth_main_no_args_prints_help(monkeypatch):
    _argv(monkeypatch)
    assert ga4_auth.main() == 1


# ---------- ga4_audit ----------


def _stub_orchestrate(*a, **k):
    agents = [{"agent": "ga4-quality", "summary": "ok", "findings": [], "data": {}}]
    return agents, {"site": {"inferred": {"vertical": "ecommerce"}}}, "ecommerce", "high"


def test_audit_main_json(monkeypatch, capsys):
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda write=False: object())
    monkeypatch.setattr(ga4_audit, "orchestrate", _stub_orchestrate)
    _argv(monkeypatch, "--property", "123", "--format", "json")
    assert ga4_audit.main() == 0
    assert "ga4-quality" in capsys.readouterr().out


def test_audit_main_markdown(monkeypatch):
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda write=False: object())
    monkeypatch.setattr(ga4_audit, "orchestrate", _stub_orchestrate)
    _argv(monkeypatch, "--property", "123", "--format", "md")
    assert ga4_audit.main() == 0


def test_audit_main_writes_output_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda write=False: object())
    monkeypatch.setattr(ga4_audit, "orchestrate", _stub_orchestrate)
    out = tmp_path / "audit.md"
    _argv(monkeypatch, "--property", "123", "--format", "md", "--output", str(out))
    assert ga4_audit.main() == 0
    assert out.exists()


def test_audit_main_auth_error_returns_2(monkeypatch):
    def _raise(write=False):
        raise ga4_auth.AuthRequiredError("run gcloud")

    monkeypatch.setattr(ga4_auth, "get_credentials", _raise)
    _argv(monkeypatch, "--property", "123")
    assert ga4_audit.main() == 2


def test_audit_main_orchestrate_error_returns_1(monkeypatch):
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda write=False: object())

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ga4_audit, "orchestrate", boom)
    _argv(monkeypatch, "--property", "123")
    assert ga4_audit.main() == 1


# ---------- ga4_report ----------


def test_report_main_markdown(monkeypatch, tmp_path):
    agent_json = tmp_path / "agent.json"
    agent_json.write_text(
        json.dumps({"agent": "ga4-quality", "summary": "ok", "findings": [], "data": {}}),
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    _argv(
        monkeypatch,
        "--property",
        "123",
        "--inputs",
        str(agent_json),
        "--format",
        "md",
        "--output",
        str(out),
    )
    assert ga4_report.main() == 0
    assert out.exists()
    assert "GA4 Audit" in out.read_text(encoding="utf-8")


def test_report_main_html(monkeypatch, tmp_path):
    agent_json = tmp_path / "agent.json"
    agent_json.write_text(
        json.dumps({"agent": "ga4-quality", "summary": "ok", "findings": []}), encoding="utf-8"
    )
    out = tmp_path / "report.html"
    _argv(
        monkeypatch,
        "--property",
        "123",
        "--inputs",
        str(agent_json),
        "--format",
        "html",
        "--output",
        str(out),
    )
    assert ga4_report.main() == 0
    assert out.exists()
