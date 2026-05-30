"""Tests for ga4_admin read surfaces.

The proto round-trip is covered by test_ga4_admin_write_integration.py; here
_proto_to_dict is stubbed to an identity so the focus is each reader's own
orchestration: cache short-circuiting, result mapping, the
list_key_events/list_conversion_events fallback, per-call error wrapping, and
platform-link aggregation. The Admin client is always mocked — no network.
"""

from types import SimpleNamespace
from unittest import mock

import ga4_admin


def _identity_ptd(monkeypatch):
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda m: m)


# ---------- caching ----------


def test_get_property_details_second_call_served_from_cache(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    client.get_property.return_value = {"displayName": "Acme"}
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    _identity_ptd(monkeypatch)

    first = ga4_admin.get_property_details("123")
    second = ga4_admin.get_property_details("123")

    assert first == second == {"displayName": "Acme"}
    assert client.get_property.call_count == 1  # second call hit the cache


# ---------- simple list mapping ----------


def test_list_data_streams_serializes_each_stream(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    client.list_data_streams.return_value = ["s1", "s2"]
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda m: {"stream": m})

    assert ga4_admin.list_data_streams("123") == [{"stream": "s1"}, {"stream": "s2"}]


def test_list_custom_defs_groups_dimensions_and_metrics(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    client.list_custom_dimensions.return_value = ["d1"]
    client.list_custom_metrics.return_value = ["m1", "m2"]
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    _identity_ptd(monkeypatch)

    out = ga4_admin.list_custom_defs("123")
    assert out == {"custom_dimensions": ["d1"], "custom_metrics": ["m1", "m2"]}


# ---------- key events: list_key_events vs list_conversion_events ----------


def test_list_key_events_uses_key_events_method_when_available(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    client.list_key_events.return_value = ["ke1", "ke2"]
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    _identity_ptd(monkeypatch)

    assert ga4_admin.list_key_events("123") == ["ke1", "ke2"]


def test_list_key_events_falls_back_to_conversion_events(monkeypatch, tmp_cache_dir):
    # An older client without list_key_events should use list_conversion_events.
    client = SimpleNamespace(list_conversion_events=lambda parent: ["ce1"])
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    _identity_ptd(monkeypatch)

    assert ga4_admin.list_key_events("123") == ["ce1"]


# ---------- error wrapping ----------


def test_get_attribution_settings_wraps_error(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    client.get_attribution_settings.side_effect = RuntimeError("nope")
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)

    out = ga4_admin.get_attribution_settings("123")
    assert out["error"] == "nope"


def test_list_data_filters_wraps_error(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    client.list_data_filters.side_effect = RuntimeError("boom")
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: client)

    assert ga4_admin.list_data_filters("123") == [{"error": "boom"}]


# ---------- enhanced measurement ----------


def test_get_enhanced_measurement_attaches_settings_for_web_streams(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    web_stream = mock.MagicMock()
    web_stream.name = "properties/123/dataStreams/9"
    client.list_data_streams.return_value = [web_stream]
    client.get_enhanced_measurement_settings.return_value = {"streamEnabled": True}

    monkeypatch.setattr(
        ga4_admin,
        "_proto_to_dict",
        lambda m: {"webStreamData": {"defaultUri": "https://x"}} if m is web_stream else m,
    )
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)

    out = ga4_admin.get_enhanced_measurement("123")
    assert out[0]["enhanced_measurement"] == {"streamEnabled": True}


def test_get_enhanced_measurement_records_settings_error(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    web_stream = mock.MagicMock()
    web_stream.name = "properties/123/dataStreams/9"
    client.list_data_streams.return_value = [web_stream]
    client.get_enhanced_measurement_settings.side_effect = RuntimeError("denied")

    monkeypatch.setattr(
        ga4_admin,
        "_proto_to_dict",
        lambda m: {"webStreamData": {}} if m is web_stream else m,
    )
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)

    out = ga4_admin.get_enhanced_measurement("123")
    assert "enhanced_measurement_error" in out[0]


def test_get_enhanced_measurement_skips_non_web_streams(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    other_stream = mock.MagicMock()
    client.list_data_streams.return_value = [other_stream]
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda m: {"type_": "IOS_APP_DATA_STREAM"})
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)

    out = ga4_admin.get_enhanced_measurement("123")
    assert "enhanced_measurement" not in out[0]
    client.get_enhanced_measurement_settings.assert_not_called()


# ---------- platform links aggregation ----------


def test_list_platform_links_aggregates_with_per_type_errors(monkeypatch, tmp_cache_dir):
    client = mock.MagicMock()
    alpha = mock.MagicMock()
    client.list_google_ads_links.return_value = ["gads"]
    client.list_search_ads360_links.side_effect = RuntimeError("sa360 fail")
    client.list_display_video360_advertiser_links.return_value = []
    alpha.list_big_query_links.return_value = ["bq"]
    alpha.list_search_console_links.return_value = []

    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: alpha)
    _identity_ptd(monkeypatch)

    out = ga4_admin.list_platform_links("123")
    assert out["google_ads_links"] == ["gads"]
    assert out["search_ads_360_links"] == [{"error": "sa360 fail"}]
    assert out["bigquery_links"] == ["bq"]
    assert out["search_console_links"] == []
