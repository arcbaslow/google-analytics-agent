"""
Shared utilities: JSON cache (15-min TTL), PII scrubber, currency normalization.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

CACHE_DIR = Path.home() / ".claude" / "ga4-cache"
CACHE_TTL_SECONDS = 15 * 60
_INVALIDATED_PATHS: set[Path] = set()

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
    "user_id",
    "client_id",
    "user_pseudo_id",
    "ip_address",
}


def _sensitive_key(key: str) -> bool:
    name = re.sub(r"[^a-z0-9]", "", key.rsplit(":", 1)[-1].lower())
    return name in {k.replace("_", "") for k in PII_PARAM_DENY}


def scrub_response(fn):
    """Scrub public JSON-like responses without changing request arguments."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return scrub_pii(fn(*args, **kwargs))

    return wrapper


def _cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _has_error(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (str(k).endswith("error") and bool(v)) or _has_error(v) for k, v in value.items()
        )
    return isinstance(value, list) and any(_has_error(v) for v in value)


def cache_get(*parts: Any) -> Any:
    """Return cached JSON if present and fresh, else None."""
    path = CACHE_DIR / f"{_cache_key(*parts)}.json"
    if path in _INVALIDATED_PATHS:
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if not 0 <= age < CACHE_TTL_SECONDS:
            return None
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return None if _has_error(value) else scrub_pii(value)
    except (OSError, ValueError):
        return None


def cache_set(value: Any, *parts: Any) -> None:
    if _has_error(value):
        return
    path = CACHE_DIR / f"{_cache_key(*parts)}.json"
    temporary = None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CACHE_DIR, suffix=".tmp", delete=False
        ) as f:
            temporary = Path(f.name)
            json.dump(scrub_pii(value), f, default=str)
        os.replace(temporary, path)
        _INVALIDATED_PATHS.discard(path)
    except OSError:
        pass  # Cache availability must not determine whether a read succeeds.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def cache_invalidate(*parts: Any) -> None:
    """Drop the cached entry for these key parts, if any. Writes call this for
    every cached read they change, otherwise the read serves the pre-write
    state until the TTL runs out."""
    path = CACHE_DIR / f"{_cache_key(*parts)}.json"
    _INVALIDATED_PATHS.add(path)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        warnings.warn(
            "Cache invalidation failed on disk; bypassing this entry in this process. "
            "Other processes may serve the old entry until its 15-minute TTL expires.",
            RuntimeWarning,
            stacklevel=2,
        )


def scrub_pii(data: Any) -> Any:
    """
    Recursively scrub PII from arbitrary JSON-like data.
    Drops keys in the deny list, redacts string values matching email/phone regexes.
    """
    if isinstance(data, dict):
        out = {}
        sensitive_value = any(
            isinstance(data.get(k), str) and _sensitive_key(data[k])
            for k in ("field", "field_name", "fieldName", "parameter")
        )
        for k, v in data.items():
            if _sensitive_key(k):
                continue
            if sensitive_value and k in (
                "value",
                "values",
                "parameter_value",
                "parameterValue",
                "string_filter",
                "stringFilter",
                "in_list_filter",
                "inListFilter",
            ):
                out[k] = "[redacted]"
            else:
                out[scrub_pii(k)] = scrub_pii(v)
        return out
    if isinstance(data, (list, tuple)):
        return [scrub_pii(x) for x in data]
    if isinstance(data, str):
        # Skip scrubbing on pure numeric values (GA4 metrics come back as strings like "30620956.912")
        if re.match(r"^-?\d+(\.\d+)?$", data):
            return data
        # GA resource IDs are structural identifiers, not phone numbers.
        if re.fullmatch(
            r"(?:accounts|properties)/\d+(?:/[A-Za-z][A-Za-z0-9]*/\d+)*(?:/[A-Za-z][A-Za-z0-9]*)?",
            data,
        ):
            return data
        decoded = data
        for _ in range(3):
            decoded = unquote(decoded)
        if EMAIL_RE.search(decoded):
            data = decoded
        try:
            url = urlsplit(data)
            query = parse_qsl(url.query, keep_blank_values=True)
            if url.scheme in ("http", "https") and any(_sensitive_key(k) for k, _ in query):
                data = urlunsplit(
                    url._replace(
                        query=urlencode(
                            [
                                (k, "[redacted]" if _sensitive_key(k) else scrub_pii(v))
                                for k, v in query
                            ]
                        )
                    )
                )
        except ValueError:
            pass
        s = EMAIL_RE.sub("[email-redacted]", data)
        s = PHONE_RE.sub(
            lambda m: m[0] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", m[0]) else "[phone-redacted]",
            s,
        )
        return s
    return data


def normalize_currency(
    value: float, from_code: str, to_code: str = "USD", fx_rates: dict[str, float] | None = None
) -> float:
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
