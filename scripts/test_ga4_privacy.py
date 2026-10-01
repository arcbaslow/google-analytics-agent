"""Check the response boundaries with synthetic personal data only."""

import json
from unittest.mock import MagicMock

import ga4_admin
import ga4_context
import ga4_data
import ga4_mcp
import ga4_report
import ga4_utils
import pytest
from google.analytics.admin_v1alpha.types import Audience, Property


@pytest.mark.parametrize(
    "key",
    [
        "userId",
        "client_id",
        "userPseudoId",
        "ipAddress",
        "customEvent:phone",
        "customUser:fullName",
    ],
)
def test_sensitive_keys_include_numeric_identifiers(key):
    assert ga4_utils.scrub_pii({key: "1234567890", "activeUsers": "1234567890"}) == {
        "activeUsers": "1234567890"
    }


def test_encoded_emails_query_ids_and_resource_names():
    source = {
        "pageLocation": "https://example.com/?userId=1234567890&q=a%2540example.com",
        "name": "properties/123456789/dataStreams/987654321",
        "revenue": "1234567890.12",
        "rule": {"parameter": "userId", "parameter_value": "1234567890"},
    }
    out = ga4_utils.scrub_pii(source)
    assert "example.com" not in out["pageLocation"].split("q=")[1]
    assert "1234567890" not in out["pageLocation"]
    assert out["rule"]["parameter_value"] == "[redacted]"
    assert out["name"] == source["name"]
    assert out["revenue"] == source["revenue"]
    assert source["rule"]["parameter_value"] == "1234567890"


def test_scrubbing_preserves_iso_dates_and_timestamps():
    assert ga4_utils.scrub_pii("2099-01-01T00:00:00") == "2099-01-01T00:00:00"
    assert ga4_utils.scrub_pii("2026-09-30") == "2026-09-30"


def test_cache_scrubs_old_entries_and_new_writes():
    payload = {"userId": "1234567890", "text": "person@example.com"}
    ga4_utils.cache_set(payload, "privacy")
    path = ga4_utils.CACHE_DIR / f"{ga4_utils._cache_key('privacy')}.json"
    assert "person@example.com" not in path.read_text()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert ga4_utils.cache_get("privacy") == {"text": "[email-redacted]"}


def test_admin_uncached_cached_and_write_responses_are_scrubbed(monkeypatch):
    client = MagicMock()
    client.get_property.return_value = Property(display_name="person@example.com")
    client.create_audience.return_value = Audience(display_name="person@example.com")
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **_: client)
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda **_: client)
    for _ in range(2):
        assert ga4_admin.get_property_details("123")["display_name"] == "[email-redacted]"
    client.get_property.assert_called_once()
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "y")
    assert (
        ga4_admin.create_audience("123", {"display_name": "Buyers"})["display_name"]
        == "[email-redacted]"
    )


def test_context_storage_scrubs_both_directions(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_context, "CONTEXT_DIR", tmp_path)
    path = ga4_context.save_context("123", {"summary": "person@example.com"})
    assert "person@example.com" not in path.read_text()
    path.write_text('{"summary": "person@example.com"}', encoding="utf-8")
    assert ga4_context.load_context("123")["summary"] == "[email-redacted]"


@pytest.mark.parametrize("format", ["markdown", "html"])
def test_rendered_reports_scrub_structured_input(format):
    payload = {
        "rows": [
            {
                "pageLocation": "person@example.com",
                "customUser:userId": "1234567890",
                "activeUsers": "8",
            }
        ]
    }
    rendered = getattr(ga4_report, f"render_custom_report_{format}")({"name": "Report"}, payload)
    assert "person@example.com" not in rendered
    assert "1234567890" not in rendered
    assert "activeUsers" in rendered


def test_mcp_preview_results_and_errors_are_scrubbed(monkeypatch):
    assert "person@example.com" not in str(
        ga4_mcp.create_audience("123", {"display_name": "person@example.com"})
    )
    monkeypatch.setattr(ga4_data, "run_report", lambda **_: {})

    def fail(*args, **kwargs):
        raise ValueError("rejected person@example.com")

    monkeypatch.setattr(ga4_data, "run_report", fail)
    out = ga4_mcp.report("123", ["activeUsers"], [])
    assert out["error"] == "invalid_request"
    assert "person@example.com" not in str(out)


def test_cli_error_does_not_echo_personal_values(monkeypatch, capsys):
    monkeypatch.setattr(
        ga4_data.sys, "argv", ["ga4_data", "--property", "123", "--report", "activeUsers"]
    )
    monkeypatch.setattr(
        ga4_data, "run_report", MagicMock(side_effect=ValueError("person@example.com"))
    )
    assert ga4_data.main() == 1
    assert "person@example.com" not in capsys.readouterr().err
