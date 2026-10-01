import json
from unittest.mock import Mock

import ga4_advertising as advertising
import ga4_data
import ga4_mcp
import pytest
from google.analytics.data_v1alpha import types


@pytest.fixture
def client(monkeypatch):
    if not advertising._supported():
        pytest.skip("optional alpha advertising support")
    client = Mock()
    client.run_report.return_value = types.RunReportResponse(
        row_count=1,
        dimension_headers=[{"name": "defaultChannelGroup"}],
        metric_headers=[{"name": "allConversionsByConversionDate"}],
        rows=[
            {"dimension_values": [{"value": "Paid Search"}], "metric_values": [{"value": "2.5"}]}
        ],
        metadata={"section": "SECTION_ADVERTISING"},
    )
    monkeypatch.setattr(ga4_data, "_get_data_alpha_client", lambda: client)
    return client


def test_alpha_spec_and_section_are_preserved(client):
    out = ga4_mcp.advertising_report(
        "123",
        ["allConversionsByConversionDate"],
        ["defaultChannelGroup"],
        "2026-09-01",
        "2026-09-30",
        ["conversionActions/1234567890"],
        "LAST_CLICK",
    )
    request = client.run_report.call_args.args[0]
    assert isinstance(request, types.RunReportRequest)
    assert (
        request.conversion_spec.attribution_model
        == types.ConversionSpec.AttributionModel.LAST_CLICK
    )
    assert out["section_verified"] and out["complete"]
    assert out["rows"][0]["allConversionsByConversionDate"] == "2.5"
    assert out["conversion_spec"]["conversion_actions"] == ["conversionActions/1234567890"]


def test_metadata_exposes_actions_and_scrubs_names(client):
    client.get_metadata.return_value = types.Metadata(
        conversions=[
            {
                "conversion_action": "conversionActions/1234567890",
                "display_name": "person@example.com",
            }
        ]
    )
    out = advertising.conversion_metadata("123")
    assert out["conversions"][0]["conversion_action"] == "conversionActions/1234567890"
    assert "person@example.com" not in str(out)


def test_missing_section_is_not_silently_verified(client):
    client.run_report.return_value.metadata.section = "SECTION_UNSPECIFIED"
    out = advertising.run_conversion_report(
        "123", ["allConversionsByConversionDate"], [], "2026-09-01", "2026-09-30"
    )
    assert out["section_verified"] is False and "warning" in out


def test_old_clients_return_unsupported_before_auth(monkeypatch):
    monkeypatch.setattr(advertising, "_supported", lambda: False)
    factory = Mock()
    monkeypatch.setattr(ga4_data, "_get_data_alpha_client", factory)
    assert advertising.conversion_metadata("123")["status"] == "unsupported"
    assert (
        advertising.run_conversion_report(
            "123", ["allConversionsByConversionDate"], [], "2026-09-01", "2026-09-30"
        )["status"]
        == "unsupported"
    )
    factory.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_date": None, "end_date": None},
        {"attribution_model": "FIRST_CLICK"},
        {"conversion_actions": ["purchase"]},
    ],
)
def test_invalid_conversion_request_is_rejected(kwargs):
    args = {"start_date": "2026-09-01", "end_date": "2026-09-30", **kwargs}
    with pytest.raises(ValueError):
        advertising.run_conversion_report("123", ["allConversionsByConversionDate"], [], **args)


def test_cli_optional_support_and_validation_without_auth(monkeypatch, capsys):
    monkeypatch.setattr(advertising, "_supported", lambda: False)
    monkeypatch.setattr("sys.argv", ["advertising", "--property", "123", "--metadata"])
    assert advertising.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unsupported"
    monkeypatch.setattr(
        "sys.argv",
        [
            "advertising",
            "--property",
            "123",
            "--start-date",
            "2026-09-01",
            "--end-date",
            "2026-09-02",
            "--dimensions",
            "",
            "--conversion-actions",
            "conversionActions/123",
        ],
    )
    assert advertising.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unsupported"
    monkeypatch.setattr(
        "sys.argv",
        ["advertising", "--property", "123", "--conversion-actions", "person@example.com"],
    )
    assert advertising.main() == 1
    assert "person@example.com" not in capsys.readouterr().err
