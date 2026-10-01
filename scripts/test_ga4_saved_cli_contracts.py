"""Exercise saved definition lifecycle and output contracts using synthetic data."""

import json

import ga4_data
import ga4_definitions as definitions
import pytest
from google.analytics.data_v1beta.types import RunReportResponse


@pytest.fixture
def cli(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(definitions, "SEGMENTS_DIR", tmp_path / "segments")
    monkeypatch.setattr(definitions, "REPORTS_DIR", tmp_path / "reports")

    def run(*args):
        monkeypatch.setattr("sys.argv", ["definitions", *map(str, args)])
        code = definitions.main()
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


def test_segment_cli_json_roundtrip_and_invalid_request(cli, tmp_path):
    source = tmp_path / "filter.json"
    source.write_text(json.dumps({"field": "country", "op": "EXACT", "value": "Canada"}))
    assert cli("--save-segment-json", "Canada", source)[0] == 0
    assert json.loads(cli("--list-segments")[1])[0]["slug"] == "canada"
    assert cli("--delete-segment", "Canada")[0] == 0
    assert cli("--delete-segment", "Canada")[0] == 1
    assert cli("--save-segment", "bad")[0] == 1
    assert cli()[0] == 1


def test_report_cli_reaches_real_data_request_and_honors_saved_csv(cli, monkeypatch, tmp_path):
    from unittest.mock import Mock

    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    client = Mock(spec=BetaAnalyticsDataClient)
    client.run_report.return_value = RunReportResponse(
        row_count=1,
        dimension_headers=[{"name": "country"}],
        metric_headers=[{"name": "sessions"}],
        rows=[{"dimension_values": [{"value": "Canada"}], "metric_values": [{"value": "3"}]}],
    )
    monkeypatch.setattr(ga4_data, "_get_data_client", lambda: client)
    source = tmp_path / "report.json"
    source.write_text(
        json.dumps(
            {
                "metrics": ["sessions"],
                "dimensions": ["country"],
                "default_format": "csv",
                "dimension_filter": {"field": "country", "op": "EXACT", "value": "Canada"},
            }
        )
    )
    assert cli("--save-report", "Report", source)[0] == 0
    assert json.loads(cli("--list-reports")[1])[0]["slug"] == "report"
    assert cli("--run-report", "Report")[0] == 1
    path = tmp_path / "report.csv"
    assert cli("--run-report", "Report", "--property", "123", "--output", path)[0] == 0
    assert path.read_text().splitlines() == ["country,sessions", "Canada,3"]
    request = client.run_report.call_args.args[0]
    assert request.dimension_filter.filter.string_filter.value == "Canada"
    assert cli("--delete-report", "Report")[0] == 0
    assert cli("--delete-report", "Report")[0] == 1


def test_invalid_saved_json_skipped_and_render_input_scrubbed(cli, monkeypatch, tmp_path):
    import ga4_report

    definitions.save_segment("valid", {"field": "country", "op": "EXACT", "value": "Canada"})
    (tmp_path / "segments" / "broken.json").write_text("{")
    assert len(json.loads(cli("--list-segments")[1])) == 1
    definitions.save_report_def("PDF", {"metrics": ["sessions"]})
    monkeypatch.setattr(
        ga4_data,
        "run_report",
        lambda **k: {"rows": [{"label": "person@example.com", "sessions": "4"}]},
    )
    rendered = []

    def fake_pdf(html):
        rendered.append(html)
        return b"synthetic PDF bytes"

    monkeypatch.setattr(ga4_report, "render_pdf_bytes", fake_pdf)
    target = tmp_path / "report.pdf"
    assert (
        cli("--run-report", "PDF", "--property", "123", "--format", "pdf", "--output", target)[0]
        == 0
    )
    assert target.read_bytes() == b"synthetic PDF bytes"
    assert "person@example.com" not in rendered[0]
