"""Tests for ga4_auth helpers that don't require the network."""

import pytest

import ga4_auth


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
