from types import SimpleNamespace
from unittest.mock import MagicMock

import ga4_audit
import ga4_data
import pytest
from google.analytics.data_v1beta.types import RunReportResponse


@pytest.mark.parametrize("failed", ["sampling", "source", "both"])
def test_failed_checks_never_produce_high_confidence(monkeypatch, failed):
    def report(**kw):
        sampling = kw["dimensions"] == ["date"]
        if (
            failed == "both"
            or (sampling and failed == "sampling")
            or (not sampling and failed == "source")
        ):
            raise RuntimeError("quota exceeded")
        return {
            "metadata": {"sampling": []},
            "rows": [{"sessionSource": "google", "sessions": "10"}],
        }

    monkeypatch.setattr(ga4_data, "run_report", report)
    out = ga4_audit.run_quality("123")["data"]
    assert out["confidence_label"] == "low"
    assert out["checks_complete"] is False
    assert out["incomplete_checks"]


def test_zero_sample_rate_is_not_treated_as_unsampled(monkeypatch):
    monkeypatch.setattr(
        ga4_data,
        "run_report",
        lambda **_: {
            "metadata": {"sampling": [{"sample_rate": 0.0}]},
            "rows": [{"sessionSource": "google", "sessions": "10"}],
        },
    )
    out = ga4_audit.run_quality("123")["data"]
    assert out["sampling_pct"] == 1.0
    assert out["confidence_label"] == "very_low"


def test_empty_source_report_is_incomplete(monkeypatch):
    monkeypatch.setattr(
        ga4_data, "run_report", lambda **_: {"metadata": {"sampling": []}, "rows": []}
    )
    out = ga4_audit.run_quality("123")["data"]
    assert out["checks_complete"] is False
    assert out["not_set_share"] is None


def test_metadata_round_trip_preserves_optional_quality_fields(monkeypatch):
    from google.analytics.data_v1beta.types import ResponseMetaData

    metadata = {
        "subject_to_thresholding": True,
        "empty_reason": "No report data",
        "schema_restriction_response": {
            "active_metric_restrictions": [
                {"metric_name": "purchaseRevenue", "restricted_metric_types": ["REVENUE_DATA"]}
            ]
        },
    }
    if "data_truncation_reasons" in ResponseMetaData.meta.fields:
        metadata["data_truncation_reasons"] = [{"data_truncation_message": "Rows truncated"}]
    response = RunReportResponse(metadata=metadata)
    client = MagicMock()
    client.run_report.return_value = response
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    out = ga4_data.run_report("123", ["sessions"], [], include_metadata=True)["metadata"]
    for field, value in metadata.items():
        assert out[field] == value


def test_older_metadata_without_sampling_or_new_fields_is_supported():
    response = SimpleNamespace(
        dimension_headers=[],
        metric_headers=[],
        rows=[],
        row_count=0,
        property_quota=None,
        metadata=SimpleNamespace(
            data_loss_from_other_row=False, currency_code="USD", time_zone="UTC"
        ),
    )
    out = ga4_data._serialize_run_report(response, include_metadata=True)
    assert out["metadata"]["sampling"] == []
    assert "data_truncation_reasons" not in out["metadata"]


def test_thresholding_alone_does_not_claim_removed_rows(monkeypatch):
    monkeypatch.setattr(
        ga4_data,
        "run_report",
        lambda **_: {
            "metadata": {"sampling": [], "subject_to_thresholding": True},
            "rows": [{"sessionSource": "google", "sessions": "10"}],
        },
    )
    out = ga4_audit.run_quality("123")
    assert out["data"]["checks_complete"] is True
    assert "does not prove" in out["findings"][0]["detail"]
