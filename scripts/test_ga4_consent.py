from types import SimpleNamespace
from unittest.mock import Mock

import ga4_admin
import ga4_mcp
import pytest
from google.analytics import admin_v1alpha
from google.api_core.exceptions import PermissionDenied


def test_settings_keep_false_values_and_use_cache(monkeypatch):
    settings_type = getattr(admin_v1alpha.types, "UserProvidedDataSettings", None)
    if settings_type is None:
        pytest.skip("optional newer Admin alpha method")
    client = Mock(spec=admin_v1alpha.AnalyticsAdminServiceClient)
    client.get_user_provided_data_settings.return_value = settings_type(
        name="properties/123/userProvidedDataSettings",
        user_provided_data_collection_enabled=True,
        automatically_detected_data_collection_enabled=False,
    )
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda: client)
    out = ga4_mcp.user_provided_data_settings("123")
    assert out["automatically_detected_data_collection_enabled"] is False
    assert ga4_admin.get_user_provided_data_settings("123") == out
    client.get_user_provided_data_settings.assert_called_once_with(
        name="properties/123/userProvidedDataSettings", retry=None, timeout=30
    )


def test_old_client_reports_unsupported(monkeypatch):
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda: SimpleNamespace())
    assert ga4_admin.get_user_provided_data_settings("123")["status"] == "unsupported"


def test_diagnostics_preserve_failures_without_claiming_consent(monkeypatch):
    monkeypatch.setattr(
        ga4_admin,
        "get_user_provided_data_settings",
        Mock(side_effect=PermissionDenied("person@example.com")),
    )
    monkeypatch.setattr(
        ga4_admin, "get_reporting_identity_settings", lambda _: {"reporting_identity": "BLENDED"}
    )
    out = ga4_mcp.consent_diagnostics("123")
    assert out["event_consent_status"] == "not_observed"
    assert out["settings"]["user_provided_data"]["error"] == "permission_denied"
    assert "person@example.com" not in str(out)
    assert len(out["manual_evidence_required"]) == 4


@pytest.mark.parametrize(
    "flag,method",
    [
        ("--user-provided-data", "get_user_provided_data_settings"),
        ("--consent-diagnostics", "get_consent_diagnostics"),
    ],
)
def test_consent_cli_dispatch(monkeypatch, flag, method):
    read = Mock(return_value={"status": "test"})
    monkeypatch.setattr(ga4_admin, method, read)
    monkeypatch.setattr(ga4_admin.sys, "argv", ["ga4_admin", "--property", "123", flag])
    assert ga4_admin.main() == 0
    read.assert_called_once_with("123")
