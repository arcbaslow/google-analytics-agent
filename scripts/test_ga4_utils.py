"""Tests for ga4_utils: cache, PII scrub, FX, confidence."""

import time

import pytest

import ga4_utils


def test_cache_set_get_hit():
    ga4_utils.cache_set({"value": 42}, "test_key", "a", "b")
    cached = ga4_utils.cache_get("test_key", "a", "b")
    assert cached == {"value": 42}


def test_cache_get_miss():
    assert ga4_utils.cache_get("nonexistent_key") is None


def test_cache_expiry(monkeypatch):
    ga4_utils.cache_set({"value": 1}, "expiry_key")
    # Force expiry
    monkeypatch.setattr(ga4_utils, "CACHE_TTL_SECONDS", 0)
    time.sleep(0.01)
    assert ga4_utils.cache_get("expiry_key") is None


def test_scrub_pii_email_in_string():
    out = ga4_utils.scrub_pii("Contact me at john@example.com today")
    assert "[email-redacted]" in out
    assert "john@example.com" not in out


def test_scrub_pii_phone_in_string():
    out = ga4_utils.scrub_pii("Call +7 (777) 123-4567 for support")
    assert "[phone-redacted]" in out


def test_scrub_pii_drops_deny_keys():
    out = ga4_utils.scrub_pii({"email": "x@x.com", "iin": "123456789012", "city": "Almaty"})
    assert "email" not in out
    assert "iin" not in out
    assert out["city"] == "Almaty"


def test_scrub_pii_recursive():
    data = {
        "user": {"email": "secret@x.com", "name": "Dilshat"},
        "events": [{"phone": "+77001234567", "type": "purchase"}],
    }
    out = ga4_utils.scrub_pii(data)
    assert "email" not in out["user"]
    assert out["user"]["name"] == "Dilshat"
    assert "phone" not in out["events"][0]
    assert out["events"][0]["type"] == "purchase"


def test_currency_normalize_same():
    assert ga4_utils.normalize_currency(100.0, "USD", "USD") == 100.0


def test_currency_normalize_kzt_to_usd():
    # KZT is one of several currencies in the FX table; this exercises the
    # conversion math through the USD pivot.
    result = ga4_utils.normalize_currency(45000.0, "KZT", "USD")
    # 45000 KZT * (1/450) USD/KZT = 100 USD
    assert abs(result - 100.0) < 0.01


def test_currency_normalize_unknown_raises():
    with pytest.raises(ValueError):
        ga4_utils.normalize_currency(100.0, "XYZ", "USD")


def test_format_confidence_high():
    assert ga4_utils.format_confidence(0.5, 1.0) == "high"


def test_format_confidence_medium():
    assert ga4_utils.format_confidence(5.0, 5.0) == "medium"


def test_format_confidence_low():
    assert ga4_utils.format_confidence(15.0, 5.0) == "low"


def test_format_confidence_very_low_sampling():
    assert ga4_utils.format_confidence(40.0, 5.0) == "very_low"


def test_format_confidence_very_low_not_set():
    assert ga4_utils.format_confidence(5.0, 40.0) == "very_low"


def test_format_confidence_handles_none():
    assert ga4_utils.format_confidence(None, None) == "high"
