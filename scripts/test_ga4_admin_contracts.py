"""Use real SDK types and client specs, with no client transport or credentials."""

from unittest.mock import MagicMock

import ga4_admin
import ga4_audit
import pytest
from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient as AlphaClient
from google.analytics.admin_v1alpha.types import DataStream, EnhancedMeasurementSettings
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient as BetaClient
from google.analytics.admin_v1beta.types import DataRetentionSettings


def test_real_web_stream_serialization_fetches_enhanced_measurement(monkeypatch):
    client = MagicMock(spec=AlphaClient)
    client.list_data_streams.return_value = [
        DataStream(
            name="properties/123/dataStreams/9",
            type_=DataStream.DataStreamType.WEB_DATA_STREAM,
            web_stream_data=DataStream.WebStreamData(default_uri="https://example.com"),
        )
    ]
    client.get_enhanced_measurement_settings.return_value = EnhancedMeasurementSettings(
        stream_enabled=True
    )
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda **_: client)
    out = ga4_admin.get_enhanced_measurement("123")
    assert out[0]["enhanced_measurement"]["stream_enabled"] is True
    client.get_enhanced_measurement_settings.assert_called_once_with(
        name="properties/123/dataStreams/9/enhancedMeasurementSettings"
    )


def test_retention_uses_separate_resource_and_cache(monkeypatch):
    client = MagicMock(spec=BetaClient)
    client.get_data_retention_settings.return_value = DataRetentionSettings(
        event_data_retention=DataRetentionSettings.RetentionDuration.TWO_MONTHS
    )
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **_: client)
    assert ga4_admin.get_data_retention_settings("123")["event_data_retention"] == "TWO_MONTHS"
    ga4_admin.get_data_retention_settings("123")
    client.get_data_retention_settings.assert_called_once_with(
        name="properties/123/dataRetentionSettings"
    )


def test_platform_links_never_probe_nonexistent_methods(monkeypatch):
    beta, alpha = MagicMock(spec=BetaClient), MagicMock(spec=AlphaClient)
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **_: beta)
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda **_: alpha)
    out = ga4_admin.list_platform_links("123")
    assert out["search_console_links"][0]["status"] == "unsupported"
    assert out["bigquery_links"] == []
    alpha.list_search_ads360_links.assert_called_once()


@pytest.mark.parametrize(
    "duration,short",
    [
        ("TWO_MONTHS", True),
        ("FOURTEEN_MONTHS", False),
        ("TWENTY_SIX_MONTHS", False),
        ("THIRTY_EIGHT_MONTHS", False),
        ("FIFTY_MONTHS", False),
    ],
)
def test_property_audit_uses_actual_retention_and_marks_manual_checks(monkeypatch, duration, short):
    monkeypatch.setattr(ga4_admin, "get_property_details", lambda _: {"display_name": "Property"})
    monkeypatch.setattr(
        ga4_admin, "get_data_retention_settings", lambda _: {"event_data_retention": duration}
    )
    monkeypatch.setattr(ga4_admin, "list_data_streams", lambda _: [{"name": "stream"}])
    monkeypatch.setattr(ga4_admin, "list_custom_defs", lambda _: {})
    out = ga4_audit.run_property("123")
    titles = [f["title"] for f in out["findings"]]
    assert ("Data retention shorter than 14 months" in titles) is short
    assert "Data filters require manual inspection" in titles


def test_property_audit_surfaces_retention_failure(monkeypatch):
    monkeypatch.setattr(ga4_admin, "get_property_details", lambda _: {})
    monkeypatch.setattr(
        ga4_admin, "get_data_retention_settings", MagicMock(side_effect=RuntimeError("denied"))
    )
    monkeypatch.setattr(ga4_admin, "list_data_streams", lambda _: [])
    monkeypatch.setattr(ga4_admin, "list_custom_defs", lambda _: {})
    out = ga4_audit.run_property("123")
    assert any(f["title"] == "Could not fetch data retention settings" for f in out["findings"])
