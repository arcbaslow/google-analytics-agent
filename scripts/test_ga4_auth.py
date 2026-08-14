"""Tests for ga4_auth helpers that don't require the network."""

import datetime
import json
from types import SimpleNamespace
from unittest import mock

import ga4_auth
import pytest


def test_scopes_for_read():
    scopes = ga4_auth.scopes_for(write=False)
    assert scopes == ["https://www.googleapis.com/auth/analytics.readonly"]


def test_scopes_for_write_includes_edit():
    scopes = ga4_auth.scopes_for(write=True)
    assert "https://www.googleapis.com/auth/analytics.edit" in scopes
    assert "https://www.googleapis.com/auth/analytics.readonly" in scopes


def test_adc_command_read_path():
    cmd = ga4_auth.adc_command(write=False)
    assert cmd.startswith("gcloud auth application-default login")
    assert "analytics.readonly" in cmd
    assert "cloud-platform" in cmd
    assert "analytics.edit" not in cmd


def test_adc_command_write_path():
    cmd = ga4_auth.adc_command(write=True)
    assert "analytics.edit" in cmd
    assert "analytics.readonly" in cmd


def test_auth_required_error_carries_hint():
    err = ga4_auth.AuthRequiredError("hint text")
    assert err.hint == "hint text"
    assert str(err) == "hint text"


def test_get_credentials_falls_back_when_no_adc(monkeypatch, fake_creds):
    """When google.auth.default raises and a legacy file exists, we use it."""
    import google.auth.exceptions

    def _raise(**_):
        raise google.auth.exceptions.DefaultCredentialsError("no adc in test env")

    monkeypatch.setattr("google.auth.default", _raise)

    def _fake_refresh(cd):
        return cd

    monkeypatch.setattr(ga4_auth, "refresh_if_needed", _fake_refresh)

    creds = ga4_auth.get_credentials(write=False)
    assert ga4_auth.credentials_source(creds) == "legacy_oauth"


def test_get_credentials_raises_when_nothing_resolves(monkeypatch, tmp_cache_dir):
    import google.auth.exceptions

    def _raise(**_):
        raise google.auth.exceptions.DefaultCredentialsError("no adc")

    monkeypatch.setattr("google.auth.default", _raise)
    # CREDENTIALS_PATH is already redirected to a tmp dir by conftest, no file
    with pytest.raises(ga4_auth.AuthRequiredError) as excinfo:
        ga4_auth.get_credentials()
    assert "gcloud auth application-default login" in excinfo.value.hint


# ---------- ADC resolution + source tagging ----------


def test_get_credentials_tags_gcloud_adc_source(monkeypatch):
    fake = mock.MagicMock()
    monkeypatch.setattr("google.auth.default", lambda **kw: (fake, "proj"))
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    creds = ga4_auth.get_credentials(write=False)
    assert ga4_auth.credentials_source(creds) == "gcloud_adc"


def test_get_credentials_tags_env_source_when_env_var_set(monkeypatch):
    fake = mock.MagicMock()
    monkeypatch.setattr("google.auth.default", lambda **kw: (fake, "proj"))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/some/sa.json")
    creds = ga4_auth.get_credentials(write=True)
    assert ga4_auth.credentials_source(creds) == "env_GOOGLE_APPLICATION_CREDENTIALS"


def test_credentials_source_defaults_to_unknown():
    assert ga4_auth.credentials_source(object()) == "unknown"


# ---------- token expiry math ----------


def test_expiring_soon_none_is_true():
    assert ga4_auth._expiring_soon(None) is True


def test_expiring_soon_far_future_is_false():
    assert ga4_auth._expiring_soon("2099-01-01T00:00:00") is False


def test_expiring_soon_past_is_true():
    assert ga4_auth._expiring_soon("2000-01-01T00:00:00") is True


# ---------- legacy credential file IO ----------


def test_save_and_load_credentials_roundtrip(tmp_cache_dir):
    payload = {"token": "t", "refresh_token": "r", "scopes": []}
    ga4_auth._save_credentials(payload)
    assert ga4_auth.CREDENTIALS_PATH.exists()
    assert ga4_auth._load_credentials() == payload


def test_load_credentials_missing_returns_none(tmp_cache_dir):
    assert ga4_auth._load_credentials() is None


# ---------- legacy OAuth token refresh ----------


def test_refresh_if_needed_skips_when_not_expiring(monkeypatch):
    class FakeCreds:
        def __init__(self, **kw):
            self.expired = False

        def refresh(self, request):
            raise AssertionError("refresh must not be called when token is fresh")

    monkeypatch.setattr("google.oauth2.credentials.Credentials", FakeCreds)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: object())

    cd = {
        "token": "t",
        "refresh_token": "r",
        "token_uri": "u",
        "client_id": "c",
        "client_secret": "s",
        "scopes": [],
        "expiry": "2099-01-01T00:00:00",
    }
    out = ga4_auth.refresh_if_needed(dict(cd))
    assert out["token"] == "t"


def test_refresh_if_needed_refreshes_and_persists_when_expired(monkeypatch):
    saved = {}
    monkeypatch.setattr(ga4_auth, "_save_credentials", lambda cd: saved.update(cd))

    class FakeCreds:
        def __init__(self, **kw):
            self.expired = True
            self.token = "new-token"
            self.expiry = datetime.datetime(2099, 1, 1)

        def refresh(self, request):
            self.refreshed = True

    monkeypatch.setattr("google.oauth2.credentials.Credentials", FakeCreds)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: object())

    cd = {
        "token": "old",
        "refresh_token": "r",
        "token_uri": "u",
        "client_id": "c",
        "client_secret": "s",
        "scopes": [],
        "expiry": "2000-01-01T00:00:00",
    }
    out = ga4_auth.refresh_if_needed(cd)
    assert out["token"] == "new-token"
    assert out["expiry"].startswith("2099")
    assert saved["token"] == "new-token"


# ---------- OAuth installed-app fallback ----------


def test_run_oauth_flow_saves_payload(monkeypatch, tmp_cache_dir):
    import google_auth_oauthlib.flow as oflow

    creds_obj = mock.MagicMock(
        token="tok",
        refresh_token="ref",
        token_uri="uri",
        client_id="cid",
        client_secret="sec",
        scopes=["s"],
        expiry=datetime.datetime(2099, 1, 1),
    )
    flow = mock.MagicMock()
    flow.run_local_server.return_value = creds_obj
    fake_cls = mock.MagicMock()
    fake_cls.from_client_secrets_file.return_value = flow
    monkeypatch.setattr(oflow, "InstalledAppFlow", fake_cls)

    payload = ga4_auth.run_oauth_flow("/path/secret.json", write=True)
    assert payload["token"] == "tok"
    assert payload["expiry"].startswith("2099")
    assert ga4_auth.CREDENTIALS_PATH.exists()
    fake_cls.from_client_secrets_file.assert_called_once()


# ---------- ADC quota project ----------


def test_set_quota_project_ok(monkeypatch):
    monkeypatch.setattr(
        ga4_auth.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr="")
    )
    assert ga4_auth.set_quota_project("proj-1") == {"status": "ok", "project": "proj-1"}


def test_set_quota_project_reports_gcloud_error(monkeypatch):
    monkeypatch.setattr(
        ga4_auth.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr="boom\n")
    )
    out = ga4_auth.set_quota_project("proj-1")
    assert out["status"] == "error"
    assert out["stderr"] == "boom"


def test_set_quota_project_handles_missing_gcloud(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(ga4_auth.subprocess, "run", _raise)
    assert ga4_auth.set_quota_project("proj-1")["status"] == "gcloud_not_found"


# ---------- check_auth ----------


def test_check_auth_success(monkeypatch, capsys):
    creds = mock.MagicMock(expiry=datetime.datetime(2099, 1, 1))
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda write=False: creds)
    monkeypatch.setattr(ga4_auth, "credentials_source", lambda c: "gcloud_adc")

    assert ga4_auth.check_auth() is True
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["source"] == "gcloud_adc"
    assert out["expiry"].startswith("2099")


def test_check_auth_no_credentials(monkeypatch, capsys):
    def _raise(write=False):
        raise ga4_auth.AuthRequiredError("run gcloud ...")

    monkeypatch.setattr(ga4_auth, "get_credentials", _raise)
    assert ga4_auth.check_auth() is False
    assert json.loads(capsys.readouterr().out)["status"] == "no_credentials"


def test_check_auth_unexpected_error(monkeypatch, capsys):
    def _raise(write=False):
        raise ValueError("weird")

    monkeypatch.setattr(ga4_auth, "get_credentials", _raise)
    assert ga4_auth.check_auth() is False
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "error"
    assert out["type"] == "ValueError"


# ---------- list_properties ----------


def test_list_properties_flattens_account_summaries(monkeypatch):
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda write=False: mock.MagicMock())

    prop = mock.MagicMock(property="properties/12345", display_name="Acme")
    summary = mock.MagicMock(display_name="Acme Account", property_summaries=[prop])
    client = mock.MagicMock()
    client.list_account_summaries.return_value = [summary]
    monkeypatch.setattr(
        "google.analytics.admin.AnalyticsAdminServiceClient", lambda credentials=None: client
    )

    props = ga4_auth.list_properties()
    assert props == [
        {"property_id": "12345", "display_name": "Acme", "parent_account": "Acme Account"}
    ]
