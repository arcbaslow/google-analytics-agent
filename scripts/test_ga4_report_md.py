"""Tests for the markdown audit report renderer."""

import ga4_report

AGENT_OUTPUTS = [
    {
        "agent": "ga4-quality",
        "summary": "High direct share suggests UTM tagging gaps.",
        "findings": [
            {
                "severity": "High",
                "title": "Direct share above industry p75",
                "detail": "42% of sessions land as (direct)/(none)",
                "metric": "direct_share",
                "metric_value": 0.42,
            },
            {
                "severity": "Medium",
                "title": "Sampling visible on long-window queries",
                "detail": "1.5% sampling on 28-day report",
            },
        ],
        "data": {"sampling_pct": 0.015},
    },
    {
        "agent": "ga4-funnel",
        "summary": "Funnel converts at 1.8%.",
        "findings": [
            {
                "severity": "Low",
                "title": "Overall conversion rate in line with vertical median",
                "metric": "conversion_rate",
                "metric_value": 0.018,
            },
        ],
        "data": {"overall_cr": 0.018},
    },
]


CONTEXT = {
    "property_id": "123",
    "primary_stream": {
        "stream_id": "9",
        "stream_name": "Web",
        "default_uri": "https://example.com",
    },
    "site": {
        "homepage": {"status": 200, "title": "Acme", "lang": "en", "server": "nginx"},
        "inferred": {
            "vertical": "ecommerce",
            "framework": "nextjs",
            "platform": "shopify",
            "is_spa": True,
        },
        "sitemap": {
            "url_count_total_estimate": 1240,
            "page_types": {"product": 800, "blog_post": 220},
        },
        "summary": "Acme | vertical: ecommerce | platform: shopify | framework: nextjs | SPA",
    },
}


def test_render_markdown_includes_property_context_section():
    md = ga4_report.render_markdown(
        "123", AGENT_OUTPUTS, confidence="medium", context=CONTEXT, vertical="ecommerce"
    )
    assert "## Property Context" in md
    assert "Acme" in md
    assert "Inferred vertical: **ecommerce**" in md
    assert "Inferred framework: nextjs" in md
    assert "SPA" in md
    assert "product: 800" in md


def test_render_markdown_includes_confidence_and_vertical_in_header():
    md = ga4_report.render_markdown(
        "123", AGENT_OUTPUTS, confidence="high", context=CONTEXT, vertical="ecommerce"
    )
    assert "Data confidence: **high**" in md
    assert "Benchmark vertical: **ecommerce**" in md


def test_render_markdown_groups_findings_by_severity():
    md = ga4_report.render_markdown(
        "123", AGENT_OUTPUTS, confidence="medium", context=CONTEXT, vertical="ecommerce"
    )
    assert "### High" in md
    assert "### Medium" in md
    assert "### Low" in md


def test_render_markdown_attaches_benchmark_annotation():
    md = ga4_report.render_markdown(
        "123", AGENT_OUTPUTS, confidence="medium", context=CONTEXT, vertical="ecommerce"
    )
    # The benchmark line shows band + interpretation
    assert "band above_p75" in md
    assert "interpretation critical" in md


def test_render_markdown_no_emoji():
    md = ga4_report.render_markdown(
        "123", AGENT_OUTPUTS, confidence="medium", context=CONTEXT, vertical="ecommerce"
    )
    # quick & robust emoji check: any non-ASCII codepoint above the basic Latin
    # range that lives in the BMP emoji ranges. Easier proxy: assert there are
    # no chars outside printable ASCII + common punctuation.
    for ch in md:
        cp = ord(ch)
        # Allow normal text + tabs/newlines + en/em-dash, curly quotes
        assert cp < 128 or ch in "–—‘’“”", f"non-ASCII char in markdown output: {ch!r} (cp={cp})"


def test_render_markdown_handles_no_context():
    md = ga4_report.render_markdown("123", AGENT_OUTPUTS, confidence="medium", context=None)
    assert "## Property Context" in md
    assert "No context cached" in md


def test_render_markdown_handles_no_findings():
    md = ga4_report.render_markdown("123", [], confidence="medium", context=CONTEXT)
    assert "_No findings._" in md


def test_render_custom_report_markdown_emits_table():
    defn = {
        "name": "test-report",
        "description": "Test",
        "metrics": ["sessions"],
        "dimensions": ["country"],
    }
    payload = {
        "result": {
            "rows": [
                {"country": "United States", "sessions": "1000"},
                {"country": "Germany", "sessions": "300"},
            ],
            "metrics": ["sessions"],
            "metadata": {"time_zone": "UTC", "currency_code": "USD"},
        }
    }
    md = ga4_report.render_custom_report_markdown(defn, payload)
    assert "# test-report" in md
    assert "| country | sessions |" in md
    assert "United States" in md
    assert "Germany" in md
