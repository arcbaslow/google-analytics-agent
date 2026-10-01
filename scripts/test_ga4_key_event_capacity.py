"""Key-event limits use service level and the SDK custom flag."""

from unittest.mock import Mock

import ga4_admin
import ga4_auth
import pytest
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import KeyEvent, Property
from google.oauth2.credentials import Credentials


@pytest.mark.parametrize(
    "level,count,allowed",
    [
        ("GOOGLE_ANALYTICS_STANDARD", 30, False),
        ("GOOGLE_ANALYTICS_360", 30, True),
        ("GOOGLE_ANALYTICS_360", 50, False),
        ("SERVICE_LEVEL_UNSPECIFIED", 50, True),
    ],
)
def test_live_capacity_preflight(monkeypatch, level, count, allowed):
    client = Mock(spec=AnalyticsAdminServiceClient)
    client.get_property.return_value = Property(service_level=level)
    client.list_key_events.return_value = [
        KeyEvent(event_name=f"custom_{i}", custom=True) for i in range(count)
    ] + [KeyEvent(event_name="purchase")]
    client.create_key_event.return_value = KeyEvent(event_name="new_action", custom=True)
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **kw: client)
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "y")
    if allowed:
        assert ga4_admin.create_key_event("123", "new_action")["custom"] is True
    else:
        with pytest.raises(ValueError, match="limit"):
            ga4_admin.create_key_event("123", "new_action")
    assert client.create_key_event.call_count == int(allowed)
    client.get_property.assert_called_once()


def test_default_event_false_flag_survives_serialization(monkeypatch):
    client = Mock(spec=AnalyticsAdminServiceClient)
    client.list_key_events.return_value = [KeyEvent(event_name="purchase", custom=False)]
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda: client)
    events = ga4_admin.list_key_events("123")
    assert events[0]["custom"] is False
    assert ga4_admin.custom_key_event_count(events) == 0


def test_legacy_auth_does_not_invent_edit_scope(monkeypatch):
    payload = {"scopes": ga4_auth.SCOPES_READ.copy()}
    monkeypatch.setattr(ga4_auth, "_load_credentials", lambda: payload)
    refresh = Mock()
    monkeypatch.setattr(ga4_auth, "refresh_if_needed", refresh)
    with pytest.raises(ga4_auth.AuthRequiredError, match="Edit scope"):
        ga4_auth._legacy_credentials(True)
    assert payload["scopes"] == ga4_auth.SCOPES_READ
    refresh.assert_not_called()


@pytest.mark.parametrize(
    "scopes,granted,expected",
    [
        (ga4_auth.SCOPES_EDIT, None, "present"),
        (ga4_auth.SCOPES_EDIT, ga4_auth.SCOPES_READ, "missing"),
        (None, None, "unknown"),
    ],
)
def test_edit_scope_evidence(scopes, granted, expected):
    credentials = Credentials(token="synthetic", scopes=scopes, granted_scopes=granted)
    assert ga4_auth.edit_scope_status(credentials)["edit_scope"] == expected
    if expected == "present":
        ga4_auth.require_edit_scope(credentials)
    else:
        with pytest.raises(ga4_auth.AuthRequiredError):
            ga4_auth.require_edit_scope(credentials)
