from types import SimpleNamespace
from unittest.mock import MagicMock

import ga4_admin
import ga4_mcp
import pytest
from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient
from google.analytics.admin_v1alpha.types import ReportingIdentitySettings


@pytest.mark.parametrize("identity", ["BLENDED", "OBSERVED", "DEVICE_BASED"])
def test_reporting_identity_read_is_cached_and_never_writes(monkeypatch, identity):
    client = MagicMock(spec=AnalyticsAdminServiceClient)
    client.get_reporting_identity_settings.return_value = ReportingIdentitySettings(
        name="properties/123/reportingIdentitySettings",
        reporting_identity=identity,
    )
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", factory)
    assert ga4_admin.get_reporting_identity_settings("123")["reporting_identity"] == identity
    assert ga4_mcp.reporting_identity("123")["reporting_identity"] == identity
    factory.assert_called_once_with()
    client.get_reporting_identity_settings.assert_called_once_with(
        name="properties/123/reportingIdentitySettings"
    )
    assert len(client.method_calls) == 1


def test_older_client_returns_unsupported_without_call(monkeypatch):
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda: SimpleNamespace())
    assert ga4_admin.get_reporting_identity_settings("123")["status"] == "unsupported"


def test_reporting_identity_cli_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(
        ga4_admin.sys, "argv", ["ga4_admin", "--property", "123", "--reporting-identity", "--json"]
    )
    read = MagicMock(return_value={"reporting_identity": "OBSERVED"})
    monkeypatch.setattr(ga4_admin, "get_reporting_identity_settings", read)
    assert ga4_admin.main() == 0
    read.assert_called_once_with("123")
    assert "OBSERVED" in capsys.readouterr().out


def test_identity_error_is_not_cached_and_mcp_still_scrubs(monkeypatch):
    client = MagicMock(spec=AnalyticsAdminServiceClient)
    client.get_reporting_identity_settings.side_effect = RuntimeError("person@example.com denied")
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda: client)
    with pytest.raises(RuntimeError, match="email-redacted"):
        ga4_mcp.reporting_identity("123")
    client.get_reporting_identity_settings.side_effect = None
    client.get_reporting_identity_settings.return_value = ReportingIdentitySettings(
        reporting_identity="BLENDED"
    )
    assert ga4_mcp.reporting_identity("123")["reporting_identity"] == "BLENDED"
    assert client.get_reporting_identity_settings.call_count == 2
