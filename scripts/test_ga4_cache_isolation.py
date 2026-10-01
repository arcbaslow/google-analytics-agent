"""Identity and generation checks never resolve real credentials."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import ga4_context
import ga4_utils as utils
import pytest


def client(account="one", scopes=None):
    return SimpleNamespace(
        transport=SimpleNamespace(
            _credentials=SimpleNamespace(
                account=account, scopes=scopes or ["read"], token="synthetic-access-token"
            )
        )
    )


def test_identity_and_scope_isolation():
    first = utils.cache_namespace(client())
    other = utils.cache_namespace(client("two"))
    changed_scope = utils.cache_namespace(client(scopes=["read", "edit"]))
    assert len({first, other, changed_scope}) == 3
    utils.cache_set({"sessions": 1}, "report", "123", namespace=first)
    assert utils.cache_get("report", "123", namespace=other) is None
    assert utils.cache_get("report", "123", namespace=changed_scope) is None
    assert utils.cache_get("report", "123", namespace=first) == {"sessions": 1}
    assert "synthetic-access-token" not in str(list(utils.CACHE_DIR.iterdir()))


def test_invalidation_covers_queries_and_principals_but_not_other_properties():
    for namespace in ("one", "two"):
        utils.cache_set([1], "read", "123", namespace=namespace)
        utils.cache_set([2], "report", "123", "query", namespace=namespace)
        utils.cache_set([3], "read", "456", namespace=namespace)
    utils.cache_invalidate("key_events", "123")
    for namespace in ("one", "two"):
        assert utils.cache_get("read", "123", namespace=namespace) is None
        assert utils.cache_get("report", "123", "query", namespace=namespace) is None
        assert utils.cache_get("read", "456", namespace=namespace) == [3]


def test_another_process_invalidation_prevents_inflight_refill():
    assert utils.cache_get("read", "123", namespace="one") is None
    code = "import sys; from pathlib import Path; import ga4_utils as u; u.CACHE_DIR=Path(sys.argv[1]); u.cache_invalidate('write','123')"
    subprocess.run(
        [sys.executable, "-c", code, str(utils.CACHE_DIR)], cwd=Path(__file__).parent, check=True
    )
    utils.cache_set({"stale": True}, "read", "123", namespace="one")
    assert utils.cache_get("read", "123", namespace="one") is None
    utils.cache_set({"fresh": True}, "read", "123", namespace="one")
    assert utils.cache_get("read", "123", namespace="one") == {"fresh": True}


def test_expired_cleanup_preserves_unrelated_and_fresh_files():
    utils.cache_set({}, "old")
    old, _ = utils._cache_paths(("old",))
    os.utime(old, (0, 0))
    unrelated = utils.CACHE_DIR / "notes.json"
    unrelated.write_text("do not read or remove", encoding="utf-8")
    utils.cache_set({}, "fresh")
    assert utils.cleanup_cache() == {"removed": 1}
    assert unrelated.exists() and utils.cache_get("fresh") == {}


def test_context_ttl_corruption_and_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(ga4_context, "CONTEXT_DIR", tmp_path)
    saved = ga4_context.save_context("123", {"site": {"summary": "test"}})
    os.utime(saved, (0, 0))
    assert ga4_context.load_context("123") is None
    saved = ga4_context.save_context("123", {"site": {"summary": "test"}})
    saved.write_text("{broken", encoding="utf-8")
    assert ga4_context.load_context("123") is None
    ga4_context.save_context("123", {"site": {"summary": "test"}})
    monkeypatch.setattr(ga4_context, "_context_namespace", lambda: "different")
    assert ga4_context.load_context("123") is None
    with pytest.raises(ValueError):
        ga4_context.save_context("../outside", {})


def test_orphan_lock_disables_cache_without_removing_lock(monkeypatch):
    _, epoch = utils._cache_paths(("locked",))
    utils.CACHE_DIR.mkdir()
    lock = epoch.with_suffix(".lock")
    lock.write_text("", encoding="ascii")
    monkeypatch.setattr(utils.time, "sleep", lambda _: None)
    assert utils.cache_get("locked") is None
    utils.cache_set({}, "locked")
    assert lock.exists()
