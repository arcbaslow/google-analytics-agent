"""
Shared utilities: JSON cache (15-min TTL), PII scrubber, currency normalization.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path.home() / ".claude" / "ga4-cache"
CACHE_TTL_SECONDS = 15 * 60

# PII patterns - drop any param matching these regexes from event data before agent analysis
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
PII_PARAM_DENY = {
    "email",
    "user_email",
    "phone",
    "user_phone",
    "first_name",
    "last_name",
    "full_name",
    "address",
    "user_address",
    "ip",
    "user_ip",
    "national_id",
    "ssn",
    "iin",
    "inn",
    "nin",
    "passport",
    "tax_id",
    "credit_card",
}


def _cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cache_get(*parts: Any) -> dict[str, Any] | None:
    """Return cached JSON if present and fresh, else None."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(*parts)}.json"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
        return None
    with open(path) as f:
        return json.load(f)


def cache_set(value: dict[str, Any], *parts: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(*parts)}.json"
    with open(path, "w") as f:
        json.dump(value, f, default=str)


def scrub_pii(data: Any) -> Any:
    """
    Recursively scrub PII from arbitrary JSON-like data.
    Drops keys in the deny list, redacts string values matching email/phone regexes.
    """
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if k.lower() in PII_PARAM_DENY:
                continue
            out[k] = scrub_pii(v)
        return out
    if isinstance(data, list):
        return [scrub_pii(x) for x in data]
    if isinstance(data, str):
        # Skip scrubbing on pure numeric values (GA4 metrics come back as strings like "30620956.912")
        if re.match(r"^-?\d+(\.\d+)?$", data):
            return data
        s = EMAIL_RE.sub("[email-redacted]", data)
        s = PHONE_RE.sub("[phone-redacted]", s)
        return s
    return data


def normalize_currency(value: float, from_code: str, to_code: str = "USD", fx_rates: dict[str, float] | None = None) -> float:
    """
    Convert a revenue figure from one currency to another. Uses a static FX
    table by default; replace `fx_rates` with a live source or per-day
    historical rates for production use.

    `fx_rates` is a dict of rate FROM each currency TO USD; the conversion
    pivots through USD.
    """
    if from_code == to_code:
        return value
    rates_to_usd = fx_rates or _DEFAULT_FX_TO_USD
    if from_code not in rates_to_usd or to_code not in rates_to_usd:
        raise ValueError(f"Missing FX rate for {from_code} or {to_code}")
    usd = value * rates_to_usd[from_code]
    return usd / rates_to_usd[to_code]


# Static FX table - rates TO USD. Update periodically or replace with live source.
# Values as of mid-2025, adjust as needed.
_DEFAULT_FX_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 1 / 150.0,
    "CNY": 1 / 7.2,
    "INR": 1 / 83.0,
    "AUD": 1 / 1.5,
    "CAD": 1 / 1.35,
    "BRL": 1 / 5.0,
    "MXN": 1 / 17.0,
    "RUB": 1 / 90.0,
    "TRY": 1 / 33.0,
    "UAH": 1 / 41.0,
    "KZT": 1 / 450.0,
}


def format_confidence(sampling_pct: float | None, not_set_pct: float | None = None) -> str:
    """Map quality metrics to a confidence label."""
    s = sampling_pct or 0
    ns = not_set_pct or 0
    if s > 30 or ns > 30:
        return "very_low"
    if s > 10 or ns > 20:
        return "low"
    if s > 1 or ns > 10:
        return "medium"
    return "high"
