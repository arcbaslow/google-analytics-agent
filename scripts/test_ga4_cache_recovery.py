import json
from pathlib import Path
from unittest.mock import MagicMock

import ga4_admin
import ga4_data
import ga4_utils
import pytest
from google.analytics.data_v1beta.types import RunReportResponse


def cache_path(key):
    return ga4_utils.CACHE_DIR / f"{ga4_utils._cache_key(key)}.json"


@pytest.mark.parametrize("content", ['{"partial":', "\ud800", '{"error": "quota exceeded"}'])
def test_corrupt_or_error_cache_is_a_miss(content):
    ga4_utils.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path("bad").write_bytes(content.encode("utf-8", errors="surrogatepass"))
    assert ga4_utils.cache_get("bad") is None


def test_unreadable_cache_is_a_miss(monkeypatch):
    monkeypatch.setattr(Path, "stat", MagicMock(side_effect=PermissionError))
    assert ga4_utils.cache_get("bad") is None


@pytest.mark.parametrize(
    "value",
    [
        {"error": "quota"},
        [{"enhanced_measurement_error": "denied"}],
        {"links": [{"error": "auth"}]},
    ],
)
def test_errors_are_not_cached(value):
    ga4_utils.cache_set(value, "bad")
    assert not cache_path("bad").exists()


def test_atomic_replace_keeps_previous_complete_entry_on_failure(monkeypatch):
    ga4_utils.cache_set({"old": True}, "atomic")

    def blocked(source, destination):
        assert json.loads(Path(source).read_text()) == {"new": True}
        assert json.loads(Path(destination).read_text()) == {"old": True}
        raise PermissionError

    monkeypatch.setattr(ga4_utils.os, "replace", blocked)
    ga4_utils.cache_set({"new": True}, "atomic")
    assert ga4_utils.cache_get("atomic") == {"old": True}
    assert list(ga4_utils.CACHE_DIR.glob("*.tmp")) == []


def test_empty_admin_results_are_reused(monkeypatch):
    client = MagicMock()
    client.list_key_events.return_value = []
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **_: client)
    assert ga4_admin.list_key_events("123") == []
    assert ga4_admin.list_key_events("123") == []
    client.list_key_events.assert_called_once()


def test_transient_admin_error_does_not_poison_next_read(monkeypatch):
    client = MagicMock()
    client.get_attribution_settings.side_effect = [RuntimeError("quota"), {"ok": True}]
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda **_: client)
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda m: m)
    assert "error" in ga4_admin.get_attribution_settings("123")
    assert ga4_admin.get_attribution_settings("123") == {"ok": True}
    assert client.get_attribution_settings.call_count == 2


def test_report_cache_preserves_requested_header_order(monkeypatch):
    client = MagicMock()
    client.run_report.side_effect = lambda req: RunReportResponse(
        dimension_headers=[{"name": d.name} for d in req.dimensions],
        metric_headers=[{"name": m.name} for m in req.metrics],
    )
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    for metrics, dimensions in [
        (["sessions", "activeUsers"], ["country", "city"]),
        (["activeUsers", "sessions"], ["city", "country"]),
    ]:
        result = ga4_data.run_report("123", metrics, dimensions)
        assert result["metrics"] == metrics
        assert result["dimensions"] == dimensions
    assert client.run_report.call_count == 2


def test_failed_api_write_preserves_cache_and_does_not_claim_success(monkeypatch):
    ga4_utils.cache_set([{"name": "old"}], "key_events", "123")
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "y")
    client = MagicMock()
    client.delete_key_event.side_effect = RuntimeError("quota")
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **_: client)
    with pytest.raises(RuntimeError, match="quota"):
        ga4_admin.delete_key_event("properties/123/keyEvents/1")
    assert ga4_utils.cache_get("key_events", "123") == [{"name": "old"}]


def test_failed_disk_invalidation_bypasses_old_entry(monkeypatch):
    ga4_utils.cache_set({"old": True}, "stale")
    monkeypatch.setattr(Path, "unlink", MagicMock(side_effect=PermissionError))
    with pytest.warns(RuntimeWarning, match="invalidation failed"):
        ga4_utils.cache_invalidate("stale")
    assert ga4_utils.cache_get("stale") is None
