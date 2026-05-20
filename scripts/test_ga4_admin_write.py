"""Tests for ga4_admin write surfaces.

The Admin client itself is mocked. These tests assert that we call the
right method on the right client variant and that the validation layer
rejects bad input before hitting the network.
"""

from unittest.mock import MagicMock, patch

import pytest

import ga4_admin


# ---------- parameter name validation ----------

def test_validate_param_name_accepts_simple():
    ga4_admin._validate_parameter_name("brand", "EVENT")


def test_validate_param_name_rejects_leading_digit():
    with pytest.raises(ValueError, match="must start with a letter"):
        ga4_admin._validate_parameter_name("1brand", "EVENT")


def test_validate_param_name_rejects_invalid_chars():
    with pytest.raises(ValueError, match="must start with a letter"):
        ga4_admin._validate_parameter_name("brand-x", "EVENT")


def test_validate_param_name_rejects_too_long_event():
    with pytest.raises(ValueError, match="exceeds 40"):
        ga4_admin._validate_parameter_name("a" * 41, "EVENT")


def test_validate_param_name_user_scope_limit_is_24():
    ga4_admin._validate_parameter_name("a" * 24, "USER")
    with pytest.raises(ValueError, match="exceeds 24"):
        ga4_admin._validate_parameter_name("a" * 25, "USER")


def test_validate_param_name_rejects_unknown_scope():
    with pytest.raises(ValueError, match="unknown scope"):
        ga4_admin._validate_parameter_name("brand", "SESSION")


# ---------- audience duration validation ----------

def test_create_audience_rejects_over_540_days(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: mock_client)
    with pytest.raises(ValueError, match="membership_duration_days"):
        ga4_admin.create_audience("123", {"display_name": "x", "membership_duration_days": 600})
    mock_client.create_audience.assert_not_called()


# ---------- key event limit ----------

def test_create_key_event_blocks_at_limit(monkeypatch):
    monkeypatch.setattr(ga4_admin, "list_key_events", lambda pid: [{"name": f"ke-{i}"} for i in range(30)])
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: mock_client)
    with pytest.raises(ValueError, match="limit 30"):
        ga4_admin.create_key_event("123", "purchase")
    mock_client.create_key_event.assert_not_called()


def test_create_key_event_under_limit_calls_api(monkeypatch):
    monkeypatch.setattr(ga4_admin, "list_key_events", lambda pid: [])
    mock_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp._pb = {"name": "properties/123/keyEvents/abc", "eventName": "purchase"}
    mock_client.create_key_event.return_value = fake_resp

    fake_types = MagicMock()
    fake_types.KeyEvent.CountingMethod = {"ONCE_PER_EVENT": 1}

    with patch.dict("sys.modules", {"google.analytics.admin_v1beta": MagicMock(),
                                      "google.analytics.admin_v1beta.types": fake_types}):
        monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: mock_client)
        with patch.object(ga4_admin, "_proto_to_dict", return_value={"event_name": "purchase"}):
            out = ga4_admin.create_key_event("123", "purchase")
    assert mock_client.create_key_event.called
    assert out["event_name"] == "purchase"


# ---------- event rule deletes pass through ----------

def test_delete_event_edit_rule_calls_alpha(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: mock_client)
    out = ga4_admin.delete_event_edit_rule("properties/123/dataStreams/9/eventEditRules/55")
    assert out["status"] == "deleted"
    mock_client.delete_event_edit_rule.assert_called_once_with(
        name="properties/123/dataStreams/9/eventEditRules/55"
    )


def test_archive_audience_calls_alpha(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: mock_client)
    out = ga4_admin.archive_audience("properties/123/audiences/55")
    assert out["status"] == "archived"
    mock_client.archive_audience.assert_called_once_with(name="properties/123/audiences/55")
