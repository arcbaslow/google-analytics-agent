"""Schema discovery/preflight contracts using real messages and mocked clients."""

import json
from unittest.mock import MagicMock

import ga4_admin
import ga4_data
import ga4_mcp
import ga4_utils
import pytest
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import CustomDimension, CustomMetric, KeyEvent
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    CheckCompatibilityRequest,
    CheckCompatibilityResponse,
    GetMetadataRequest,
    Metadata,
    RunReportResponse,
)
from google.api_core.exceptions import InvalidArgument, ResourceExhausted


@pytest.fixture
def client(monkeypatch):
    client = MagicMock(spec=BetaAnalyticsDataClient)
    client.get_metadata.return_value = Metadata(
        name="properties/123/metadata",
        dimensions=[
            {
                "api_name": "customEvent:plan",
                "custom_definition": True,
                "description": "a@example.com",
            }
        ],
        metrics=[{"api_name": "sessions", "type_": "TYPE_INTEGER"}],
    )
    client.check_compatibility.return_value = CheckCompatibilityResponse(
        dimension_compatibilities=[
            {
                "dimension_metadata": {"api_name": "date", "description": "a@example.com"},
                "compatibility": "COMPATIBLE",
            }
        ],
        metric_compatibilities=[
            {"metric_metadata": {"api_name": "itemRevenue"}, "compatibility": "INCOMPATIBLE"}
        ],
    )
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    return client


def test_metadata_real_contract_scrubbing_and_cache(client):
    first = ga4_data.get_metadata("123")
    assert first == ga4_mcp.report_metadata("123")
    assert first["dimensions"][0]["api_name"] == "customEvent:plan"
    assert first["dimensions"][0]["custom_definition"] is True
    assert first["metrics"][0]["type_"] == "TYPE_INTEGER"
    assert "a@example.com" not in json.dumps(first)
    client.get_metadata.assert_called_once_with(
        GetMetadataRequest(name="properties/123/metadata"), retry=None, timeout=30
    )
    cached = next(ga4_utils.CACHE_DIR.glob("*.json")).read_text()
    assert "a@example.com" not in cached
    assert len(client.method_calls) == 1


def test_metadata_empty_result_bypass_and_property_isolation(client):
    client.get_metadata.return_value = Metadata()
    assert ga4_data.get_metadata("0") == {"dimensions": [], "metrics": []}
    ga4_data.get_metadata("0")
    assert client.get_metadata.call_count == 1
    ga4_data.get_metadata("0", use_cache=False)
    ga4_data.get_metadata("456")
    assert client.get_metadata.call_count == 3
    assert client.get_metadata.call_args.args[0].name == "properties/456/metadata"


@pytest.mark.parametrize("raw", [False, True])
def test_preflight_uses_report_filters_without_running_report_or_caching(client, raw):
    kwargs = {"filter_expr": "eventName = purchase"}
    if raw:
        kwargs["filter_dict"] = {
            "filter": {"field_name": "customEvent:plan", "string_filter": {"value": "paid"}}
        }
    first = ga4_mcp.check_compatibility("123", ["sessions"], ["date"], **kwargs)
    assert first == ga4_data.check_compatibility("123", ["sessions"], ["date"], **kwargs)
    request = client.check_compatibility.call_args.args[0]
    assert isinstance(request, CheckCompatibilityRequest)
    assert request.property == "properties/123"
    assert [metric.name for metric in request.metrics] == ["sessions"]
    assert [dimension.name for dimension in request.dimensions] == ["date"]
    assert request.dimension_filter.filter.field_name == (
        "customEvent:plan" if raw else "eventName"
    )
    assert request.dimension_filter.filter.string_filter.value == ("paid" if raw else "purchase")
    assert first["metric_compatibilities"][0]["compatibility"] == "INCOMPATIBLE"
    assert first["dimension_compatibilities"][0]["compatibility"] == "COMPATIBLE"
    assert "a@example.com" not in json.dumps(first)
    assert client.check_compatibility.call_count == 2
    assert len(client.method_calls) == 2


def test_preflight_empty_lists_and_invalid_filter(client):
    client.check_compatibility.return_value = CheckCompatibilityResponse()
    assert ga4_data.check_compatibility("123", [], []) == {
        "dimension_compatibilities": [],
        "metric_compatibilities": [],
    }
    with pytest.raises(ValueError, match="Unparseable"):
        ga4_data.check_compatibility("123", [], [], filter_expr="invalid")
    assert client.check_compatibility.call_count == 1


def test_reports_do_not_automatically_discover_or_preflight(client):
    client.run_report.return_value = RunReportResponse()
    ga4_data.run_report("123", ["sessions"], [])
    assert len(client.method_calls) == 1
    client.run_report.assert_called_once()


@pytest.mark.parametrize("action", ["metadata", "check-compatibility"])
def test_cli_reads_real_response_and_scrubs_api_errors(monkeypatch, capsys, client, action):
    args = ["ga4_data", "--property", "123", f"--{action}", "--json", "--no-cache"]
    method = client.get_metadata
    if action == "check-compatibility":
        args += [
            "--metrics",
            "sessions",
            "--dimensions",
            "date",
            "--filter",
            "eventName = purchase",
        ]
        method = client.check_compatibility
    monkeypatch.setattr(ga4_data.sys, "argv", args)
    assert ga4_data.main() == 0
    assert "email-redacted" in capsys.readouterr().out
    method.side_effect = InvalidArgument("a@example.com incompatible fields")
    assert ga4_data.main() == 1
    error = capsys.readouterr().err
    assert "a@example.com" not in error
    assert "InvalidArgument" in error


@pytest.mark.parametrize("tool", ["report_metadata", "check_compatibility"])
def test_mcp_quota_error_scrubbed_and_not_cached(client, tool):
    method = client.get_metadata if tool == "report_metadata" else client.check_compatibility
    method.side_effect = ResourceExhausted("a@example.com quota")
    args = ("123",) if tool == "report_metadata" else ("123", ["sessions"], [])
    for _ in range(2):
        out = getattr(ga4_mcp, tool)(*args)
        assert out["error"] == "quota_exhausted"
        assert "email-redacted" in out["message"]
    assert method.call_count == 2


@pytest.mark.parametrize(
    "args",
    [
        ["--metadata", "--report", "sessions"],
        ["--check-compatibility", "--funnel-report"],
        ["--report", "sessions", "--metrics", "sessions"],
    ],
)
def test_cli_rejects_ambiguous_actions(monkeypatch, client, args):
    monkeypatch.setattr(ga4_data.sys, "argv", ["ga4_data", "--property", "123", *args])
    with pytest.raises(SystemExit) as exc:
        ga4_data.main()
    assert exc.value.code == 2
    assert client.method_calls == []


@pytest.mark.parametrize(
    "operation,args,response",
    [
        ("create_custom_dimension", ("123", "plan", "Plan", "EVENT"), CustomDimension()),
        ("create_custom_metric", ("123", "score", "Score", "STANDARD"), CustomMetric()),
        ("archive_custom_dimension", ("properties/123/customDimensions/1",), None),
        ("archive_custom_metric", ("properties/123/customMetrics/1",), None),
        ("create_key_event", ("123", "purchase"), KeyEvent()),
        ("delete_key_event", ("properties/123/keyEvents/1",), None),
    ],
)
@pytest.mark.parametrize("outcome", ["success", "failed", "refused"])
def test_field_configuration_writes_invalidate_metadata_only_after_success(
    monkeypatch, client, operation, args, response, outcome
):
    ga4_data.get_metadata("123")
    ga4_data.get_metadata("456")
    admin = MagicMock(spec=AnalyticsAdminServiceClient)
    method = getattr(admin, operation)
    method.return_value = response
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda **_: admin)
    monkeypatch.setattr(ga4_admin.sys.stdin, "isatty", lambda: True)
    prompt = MagicMock(return_value="n" if outcome == "refused" else "y")
    monkeypatch.setattr("builtins.input", prompt)
    if outcome == "failed":
        method.side_effect = RuntimeError("denied")
    if outcome == "success":
        getattr(ga4_admin, operation)(*args)
    else:
        with pytest.raises(RuntimeError):
            getattr(ga4_admin, operation)(*args)
    prompt.assert_called_once_with()
    assert method.call_count == (0 if outcome == "refused" else 1)
    ga4_data.get_metadata("123")
    ga4_data.get_metadata("456")
    assert client.get_metadata.call_count == (3 if outcome == "success" else 2)
