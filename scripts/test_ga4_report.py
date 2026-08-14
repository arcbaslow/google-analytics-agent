"""Tests for ga4_report: HTML rendering, severity sort, escaping."""

import json

import ga4_report


def test_severity_order():
    findings = [
        {"severity": "Low", "title": "low thing", "detail": "x"},
        {"severity": "Critical", "title": "critical thing", "detail": "x"},
        {"severity": "Medium", "title": "medium thing", "detail": "x"},
        {"severity": "High", "title": "high thing", "detail": "x"},
    ]
    html = ga4_report._render_findings(findings)
    # Critical should come first, Low last
    i_crit = html.index("critical thing")
    i_high = html.index("high thing")
    i_med = html.index("medium thing")
    i_low = html.index("low thing")
    assert i_crit < i_high < i_med < i_low


def test_html_escaping():
    findings = [{"severity": "Critical", "title": "<script>alert('xss')</script>", "detail": "x"}]
    html = ga4_report._render_findings(findings)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_includes_property_and_confidence():
    agents_output = [
        {
            "agent": "ga4-funnel",
            "summary": "Funnel drops mainly at checkout.",
            "findings": [
                {"severity": "Critical", "title": "add_payment_info post-payment", "detail": "x"},
            ],
            "data": {"steps": 5, "overall_conv_pct": 0.6},
        },
    ]
    html = ga4_report.render_html("123456789", agents_output, confidence="medium")
    assert "123456789" in html
    assert "medium" in html
    assert "add_payment_info post-payment" in html
    assert "Funnel drops mainly at checkout." in html
    assert "Manrope" in html  # brand font present


def test_render_html_empty_findings():
    html = ga4_report.render_html("123", [{"agent": "ga4-funnel", "summary": "", "findings": []}])
    assert "No findings" in html


def test_render_html_no_summary():
    html = ga4_report.render_html("123", [{"agent": "ga4-funnel", "findings": [], "data": {}}])
    assert "ga4-funnel" in html


def test_cli_writes_html_file(tmp_path, monkeypatch):
    """Round-trip: pass JSON inputs through the CLI, check the file lands on disk."""
    input_path = tmp_path / "agent.json"
    input_path.write_text(
        json.dumps(
            {
                "agent": "ga4-funnel",
                "summary": "Test summary",
                "findings": [{"severity": "High", "title": "test", "detail": "test detail"}],
                "data": {},
            }
        )
    )
    output_path = tmp_path / "report.html"

    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ga4_report.py",
            "--property",
            "999",
            "--inputs",
            str(input_path),
            "--format",
            "html",
            "--output",
            str(output_path),
            "--confidence",
            "high",
        ],
    )
    rc = ga4_report.main()
    assert rc == 0
    assert output_path.exists()
    content = output_path.read_text()
    assert "Test summary" in content
    assert "999" in content
