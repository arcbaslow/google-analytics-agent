"""
GA4 audit report generator.

Merges agent JSON outputs into a unified HTML report (off-white bg, near-black text, Manrope).
PDF via WeasyPrint. Findings are sorted by severity for the final action plan.

Agent output schema:
  {"agent": "...", "summary": "...", "findings": [{"severity": "...", "title": "...", "detail": "..."}], "data": {...}}
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>GA4 Audit - __PROPERTY_ID__</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');
  html, body { background: #F5F4EF; color: #252525; font-family: 'Manrope', -apple-system, sans-serif; margin: 0; padding: 0; }
  .wrap { max-width: 880px; margin: 0 auto; padding: 56px 32px 80px; }
  h1 { font-weight: 700; font-size: 32px; margin: 0 0 8px; letter-spacing: -0.02em; }
  h2 { font-weight: 600; font-size: 22px; margin: 48px 0 12px; letter-spacing: -0.01em; }
  h3 { font-weight: 600; font-size: 16px; margin: 24px 0 8px; }
  .meta { color: #6b6b6b; font-size: 14px; margin-bottom: 32px; }
  .summary-block { background: #ffffff; border: 1px solid #e5e2d8; padding: 20px 24px; margin: 16px 0; }
  .conf { display: inline-block; padding: 4px 10px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; border: 1px solid #252525; }
  .conf.high { background: #d6f0d6; }
  .conf.medium { background: #fff3cc; }
  .conf.low { background: #ffe0cc; }
  .conf.very_low { background: #ffcccc; }
  .findings { list-style: none; padding: 0; margin: 0; }
  .findings li { border-left: 4px solid #252525; padding: 12px 16px; margin: 8px 0; background: #ffffff; }
  .findings li.crit { border-left-color: #c0392b; }
  .findings li.high { border-left-color: #d68910; }
  .findings li.med { border-left-color: #2874a6; }
  .findings li.low { border-left-color: #7d7d7d; }
  .sev { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; margin-right: 8px; }
  .sev.crit { color: #c0392b; }
  .sev.high { color: #d68910; }
  .sev.med { color: #2874a6; }
  .sev.low { color: #7d7d7d; }
  pre { background: #ffffff; border: 1px solid #e5e2d8; padding: 12px; overflow-x: auto; font-size: 12px; }
  .footer { margin-top: 64px; padding-top: 16px; border-top: 1px solid #d8d4c8; color: #6b6b6b; font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>GA4 E-commerce Funnel Audit</h1>
  <div class="meta">
    Property __PROPERTY_ID__ - generated __GENERATED_AT__
    <br />Confidence: <span class="conf __CONFIDENCE_CLASS__">__CONFIDENCE__</span>
  </div>

  <h2>Executive Summary</h2>
  <div class="summary-block">__EXEC_SUMMARY__</div>

  <h2>Action Plan</h2>
  <ul class="findings">__FINDINGS_HTML__</ul>

  <h2>Per-Agent Output</h2>
  __PER_AGENT_HTML__

  <div class="footer">
    claude-ga4-agents v0.1.0 - __GENERATED_AT__
  </div>
</div>
</body>
</html>"""


def _severity_class(s):
    return {"Critical": "crit", "High": "high", "Medium": "med", "Low": "low"}.get(s, "low")


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_findings(findings):
    if not findings:
        return "<li><em>No findings.</em></li>"
    sorted_f = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "Low"), 4))
    parts = []
    for f in sorted_f:
        sev = f.get("severity", "Low")
        cls = _severity_class(sev)
        title = _esc(f.get("title", "(no title)"))
        detail = _esc(f.get("detail", ""))
        source = _esc(f.get("source", ""))
        source_html = (
            f' <span style="color:#888;font-size:12px;">[{source}]</span>' if source else ""
        )
        parts.append(
            f'<li class="{cls}"><span class="sev {cls}">{sev}</span><strong>{title}</strong>{source_html}'
            f'<div style="margin-top:6px;font-size:14px;color:#404040;">{detail}</div></li>'
        )
    return "".join(parts)


def _render_per_agent(agents_output):
    parts = []
    for ao in agents_output:
        name = _esc(ao.get("agent", "unknown"))
        summary = _esc(ao.get("summary", ""))
        data = ao.get("data", {})
        data_pretty = _esc(json.dumps(data, indent=2, default=str))
        parts.append(
            f'<h3>{name}</h3><div class="summary-block">{summary}</div>'
            f"<details><summary>raw output</summary><pre>{data_pretty}</pre></details>"
        )
    return "".join(parts)


def render_html(property_id, agents_output, confidence="medium"):
    """Build the HTML report from per-agent outputs."""
    all_findings = []
    summaries = []
    for ao in agents_output:
        for f in ao.get("findings", []):
            ff = dict(f)
            ff["source"] = ao.get("agent", "")
            all_findings.append(ff)
        if ao.get("summary"):
            summaries.append(
                f"<strong>{_esc(ao.get('agent', ''))}:</strong> {_esc(ao.get('summary'))}"
            )

    exec_html = "<br />".join(summaries) if summaries else "(no agent summaries)"

    return (
        HTML_TEMPLATE.replace("__PROPERTY_ID__", _esc(property_id))
        .replace("__GENERATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__CONFIDENCE_CLASS__", _esc(confidence))
        .replace("__CONFIDENCE__", _esc(confidence))
        .replace("__EXEC_SUMMARY__", exec_html)
        .replace("__FINDINGS_HTML__", _render_findings(all_findings))
        .replace("__PER_AGENT_HTML__", _render_per_agent(agents_output))
    )


def render_pdf(html, output_path):
    """Render HTML to PDF via WeasyPrint."""
    from weasyprint import HTML

    HTML(string=html).write_pdf(output_path)


def render_pdf_bytes(html) -> bytes:
    """Render HTML to PDF and return the bytes (no filesystem write)."""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


CUSTOM_REPORT_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>__REPORT_NAME__</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');
  html, body { background: #F5F4EF; color: #252525; font-family: 'Manrope', -apple-system, sans-serif; margin: 0; padding: 0; }
  .wrap { max-width: 1040px; margin: 0 auto; padding: 48px 32px 64px; }
  h1 { font-weight: 700; font-size: 28px; margin: 0 0 8px; letter-spacing: -0.02em; }
  .meta { color: #6b6b6b; font-size: 13px; margin-bottom: 24px; }
  .description { background: #ffffff; border: 1px solid #e5e2d8; padding: 16px 20px; margin: 16px 0 24px; font-size: 14px; }
  table { width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid #e5e2d8; font-size: 13px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #efece4; }
  th { background: #f1eee5; font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase; font-size: 11px; color: #404040; }
  tr:last-child td { border-bottom: none; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #d8d4c8; color: #6b6b6b; font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>__REPORT_NAME__</h1>
  <div class="meta">Generated __GENERATED_AT__ · rows: __ROWS__ · window: __WINDOW__</div>
  __DESCRIPTION_HTML__
  <table>
    <thead><tr>__HEADERS__</tr></thead>
    <tbody>__ROWS_HTML__</tbody>
  </table>
  <div class="footer">claude-ga4-agents · __REPORT_NAME__</div>
</div>
</body>
</html>"""


def render_custom_report_markdown(definition, report_payload):
    """Render a single saved-report run as plain markdown (no emoji)."""
    name = definition.get("name", "untitled")
    desc = definition.get("description", "")
    payload = (
        report_payload.get("result", report_payload) if isinstance(report_payload, dict) else {}
    )
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    metric_names = set(payload.get("metrics") or definition.get("metrics") or [])
    headers = (
        list(rows[0].keys())
        if rows
        else (list(definition.get("dimensions", [])) + list(definition.get("metrics", [])))
    )

    out = []
    out.append(f"# {name}")
    out.append("")
    out.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_  ")
    out.append(f"_Rows: {len(rows)}_")
    out.append("")
    if desc:
        out.append(desc)
        out.append("")

    md = payload.get("metadata") if isinstance(payload, dict) else None
    if md:
        bits = []
        if md.get("time_zone"):
            bits.append(f"Time zone: {md.get('time_zone')}")
        if md.get("currency_code"):
            bits.append(f"Currency: {md.get('currency_code')}")
        sampling = md.get("sampling") or []
        if sampling and sampling[0].get("sample_rate") is not None:
            rate = sampling[0]["sample_rate"]
            bits.append(f"Sample rate: {rate:.2%}")
        if bits:
            out.append("> " + " · ".join(bits))
            out.append("")

    if not rows:
        out.append("_No rows returned._")
        out.append("")
        return "\n".join(out)

    out.append("| " + " | ".join(_md_escape(h) for h in headers) + " |")
    out.append("| " + " | ".join("---:" if h in metric_names else "---" for h in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(_md_escape(row.get(h, "")) for h in headers) + " |")
    out.append("")
    return "\n".join(out)


def render_custom_report_html(definition, report_payload):
    """Render a single saved-report run as standalone HTML."""
    name = _esc(definition.get("name", "untitled"))
    desc = definition.get("description", "")
    desc_html = f'<div class="description">{_esc(desc)}</div>' if desc else ""

    payload = (
        report_payload.get("result", report_payload) if isinstance(report_payload, dict) else {}
    )
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    metric_names = set(payload.get("metrics") or definition.get("metrics") or [])
    headers = (
        list(rows[0].keys())
        if rows
        else (list(definition.get("dimensions", [])) + list(definition.get("metrics", [])))
    )

    header_html = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    row_html = []
    for row in rows:
        cells = []
        for h in headers:
            v = row.get(h, "")
            cls = "num" if h in metric_names else ""
            cells.append(f'<td class="{cls}">{_esc(v)}</td>')
        row_html.append("<tr>" + "".join(cells) + "</tr>")

    window = ""
    md = payload.get("metadata") if isinstance(payload, dict) else None
    if md and md.get("time_zone"):
        window = _esc(md.get("time_zone"))

    return (
        CUSTOM_REPORT_TEMPLATE.replace("__REPORT_NAME__", name)
        .replace("__GENERATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__ROWS__", str(len(rows)))
        .replace("__WINDOW__", window or "—")
        .replace("__DESCRIPTION_HTML__", desc_html)
        .replace("__HEADERS__", header_html)
        .replace("__ROWS_HTML__", "".join(row_html))
    )


def _load_property_context(property_id):
    """Pull the cached property context, if any. Best-effort; returns None
    on any failure so report rendering never depends on context being
    present."""
    try:
        from ga4_context import load_context

        return load_context(str(property_id))
    except Exception:
        return None


def _md_escape(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _md_severity_marker(sev):
    return {
        "Critical": "[CRITICAL]",
        "High": "[HIGH]",
        "Medium": "[MEDIUM]",
        "Low": "[LOW]",
    }.get(sev, f"[{sev}]")


def _format_benchmark_md(b):
    if not b or "error" in b:
        return ""
    return (
        f" (value {b.get('value')}, vertical {b.get('vertical')}, "
        f"p25 {b.get('p25')} / p50 {b.get('p50')} / p75 {b.get('p75')}, "
        f"band {b.get('band')}, interpretation {b.get('interpretation')})"
    )


def render_property_context_md(context):
    """Render the property/site context block as markdown."""
    if not context:
        return "## Property Context\n\n_No context cached. Run `/ga4 context <property-id>` to populate._\n"

    lines = ["## Property Context", ""]
    pc = context
    if "primary_stream" in pc:
        ps = pc["primary_stream"]
        lines.append(
            f"- Primary web stream: `{ps.get('stream_name', '-')}` (`{ps.get('stream_id', '-')}`)"
        )
        lines.append(f"- URL: {ps.get('default_uri', '-')}")
    additional = pc.get("additional_streams") or []
    if additional:
        lines.append(f"- Additional streams: {len(additional)}")
    site = pc.get("site") or {}
    home = site.get("homepage") or {}
    inf = site.get("inferred") or {}
    if home:
        lines.append(f"- Homepage status: {home.get('status', '-')}")
        if home.get("title"):
            lines.append(f"- Title: {home.get('title')}")
        if home.get("lang"):
            lines.append(f"- Language: {home.get('lang')}")
        if home.get("server"):
            lines.append(f"- Server header: `{home.get('server')}`")
    if inf:
        lines.append(f"- Inferred vertical: **{inf.get('vertical', 'other')}**")
        if inf.get("framework"):
            lines.append(f"- Inferred framework: {inf['framework']}")
        if inf.get("platform"):
            lines.append(f"- Inferred platform: {inf['platform']}")
        lines.append(f"- Rendering: {'SPA' if inf.get('is_spa') else 'MPA'}")
    sitemap = site.get("sitemap") or {}
    if sitemap:
        pt = sitemap.get("page_types") or {}
        if pt:
            pt_list = ", ".join(f"{k}: {v}" for k, v in pt.items())
            lines.append(f"- Sitemap page types: {pt_list}")
        if sitemap.get("url_count_total_estimate"):
            lines.append(f"- Sitemap URLs (sampled): {sitemap['url_count_total_estimate']}")
    if site.get("summary"):
        lines.append("")
        lines.append(f"_{site['summary']}_")
    return "\n".join(lines) + "\n"


def render_markdown(property_id, agents_output, confidence="medium", context=None, vertical=None):
    """Build a markdown audit report. Plain markdown, no emoji.

    `context` is the property context dict (homepage / vertical / framework
    inference) — if None, the function tries to load it from the local
    cache via ga4_context.load_context. `vertical` overrides the
    inferred vertical used for benchmark enrichment."""
    if context is None:
        context = _load_property_context(property_id)
    if vertical is None and context:
        vertical = ((context.get("site") or {}).get("inferred") or {}).get("vertical")

    all_findings = []
    summaries = []
    for ao in agents_output:
        agent_name = ao.get("agent", "unknown")
        for f in ao.get("findings", []):
            ff = dict(f)
            ff["source"] = agent_name
            all_findings.append(ff)
        if ao.get("summary"):
            summaries.append((agent_name, ao["summary"]))

    if vertical:
        try:
            from ga4_benchmarks import enrich_findings

            all_findings = enrich_findings(all_findings, vertical)
        except Exception:
            pass

    sorted_findings = sorted(
        all_findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "Low"), 4)
    )

    lines = []
    lines.append(f"# GA4 Audit — property {property_id}")
    lines.append("")
    lines.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_  ")
    lines.append(f"_Data confidence: **{confidence}**_  ")
    if vertical:
        lines.append(f"_Benchmark vertical: **{vertical}**_  ")
    lines.append("")

    lines.append(render_property_context_md(context))

    lines.append("## Executive Summary")
    lines.append("")
    if summaries:
        for agent_name, summary in summaries:
            lines.append(f"- **{agent_name}**: {summary}")
    else:
        lines.append("_No agent summaries provided._")
    lines.append("")

    lines.append("## Action Plan")
    lines.append("")
    for sev in ("Critical", "High", "Medium", "Low"):
        items = [f for f in sorted_findings if f.get("severity") == sev]
        if not items:
            continue
        lines.append(f"### {sev}")
        lines.append("")
        for f in items:
            title = f.get("title", "(untitled)")
            detail = f.get("detail", "")
            source = f.get("source", "")
            bench = _format_benchmark_md(f.get("benchmark"))
            lines.append(f"- **{title}** _(source: {source})_{bench}")
            if detail:
                lines.append(f"  - {detail}")
        lines.append("")

    if not sorted_findings:
        lines.append("_No findings._")
        lines.append("")

    lines.append("## Per-Agent Output")
    lines.append("")
    for ao in agents_output:
        name = ao.get("agent", "unknown")
        summary = ao.get("summary", "")
        data = ao.get("data")
        lines.append(f"### {name}")
        lines.append("")
        if summary:
            lines.append(summary)
            lines.append("")
        if data is not None:
            lines.append("<details>")
            lines.append("<summary>raw output</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(data, indent=2, default=str))
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by google-analytics-agent._")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="GA4 audit report generator")
    parser.add_argument("--property", required=True)
    parser.add_argument(
        "--inputs", required=True, help="Comma-separated paths to agent JSON outputs"
    )
    parser.add_argument("--format", choices=["html", "pdf", "md"], default="html")
    parser.add_argument("--output", required=True)
    parser.add_argument("--confidence", default="medium")
    parser.add_argument(
        "--vertical", help="Override the benchmark vertical (else inferred from context)"
    )
    args = parser.parse_args()

    inputs = []
    for p in args.inputs.split(","):
        p = p.strip()
        if not p:
            continue
        with open(p) as f:
            inputs.append(json.load(f))

    out_path = Path(args.output)
    if args.format == "html":
        body = render_html(args.property, inputs, confidence=args.confidence)
        out_path.write_text(body, encoding="utf-8")
    elif args.format == "md":
        body = render_markdown(
            args.property, inputs, confidence=args.confidence, vertical=args.vertical
        )
        out_path.write_text(body, encoding="utf-8")
    else:
        body = render_html(args.property, inputs, confidence=args.confidence)
        render_pdf(body, str(out_path))

    print(json.dumps({"status": "ok", "output": str(out_path), "format": args.format}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
