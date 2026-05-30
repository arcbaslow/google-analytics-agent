"""
Local storage for stored GA4 segment definitions and custom report definitions.

GA4 has no stored "Segment" resource — segments only exist inside Explorations
in the UI. To get reusable cohorts on the public API we persist filter
expressions locally and inject them as `dimensionFilter` on `runReport` calls.

The same module also holds saved custom-report definitions, since both are just
JSON sitting on disk.

Layout:
  ~/.claude/ga4-definitions/
    segments/<slug>.json
    reports/<slug>.json

CLI:
  python scripts/ga4_definitions.py --save-segment <name> --field eventName --op EXACT --value purchase
  python scripts/ga4_definitions.py --save-segment-json <name> path/to/filter.json
  python scripts/ga4_definitions.py --list-segments
  python scripts/ga4_definitions.py --delete-segment <name>

  python scripts/ga4_definitions.py --save-report <name> path/to/definition.json
  python scripts/ga4_definitions.py --list-reports
  python scripts/ga4_definitions.py --run-report <name> --property <id> [--days N] [--format html|pdf|json|csv] [--output path]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFINITIONS_DIR = Path.home() / ".claude" / "ga4-definitions"
SEGMENTS_DIR = DEFINITIONS_DIR / "segments"
REPORTS_DIR = DEFINITIONS_DIR / "reports"

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower().strip())
    return s.strip("-") or "unnamed"


def _ensure_dirs():
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------- segments ----------


def save_segment(name: str, filter_expression: dict[str, Any], description: str = "") -> Path:
    """Persist a segment under SEGMENTS_DIR. Overwrites if the slug collides."""
    _ensure_dirs()
    payload = {
        "name": name,
        "description": description,
        "filter_expression": filter_expression,
    }
    path = SEGMENTS_DIR / f"{_slug(name)}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def list_segments() -> list[dict[str, Any]]:
    _ensure_dirs()
    out = []
    for p in sorted(SEGMENTS_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append(
            {"slug": p.stem, "name": data.get("name"), "description": data.get("description", "")}
        )
    return out


def load_segment(name: str) -> dict[str, Any]:
    path = SEGMENTS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"no segment named {name!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def delete_segment(name: str) -> dict[str, Any]:
    path = SEGMENTS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"no segment named {name!r} at {path}")
    path.unlink()
    return {"status": "deleted", "name": name}


def build_filter_from_definition(filter_expression: dict[str, Any]):
    """Convert a stored filter expression into a Data API FilterExpression proto.

    Two shapes are accepted:
      - shorthand: {"field": "eventName", "op": "EXACT", "value": "purchase"} or
                   {"field": "eventName", "op": "IN_LIST", "values": [...]}
        — same dict shape parse_filter() in ga4_data.py emits.
      - raw: a dict matching the Data API FilterExpression schema (and_group,
        or_group, not_expression, filter); passed through ParseDict.
    """
    from ga4_data import _build_filter_expression

    if {"field", "op"} <= set(filter_expression.keys()):
        return _build_filter_expression(filter_expression)
    from google.analytics.data_v1beta.types import FilterExpression
    from google.protobuf.json_format import ParseDict

    # FilterExpression is a proto-plus wrapper; json_format.ParseDict cannot
    # populate it directly (it probes for a DESCRIPTOR attribute the wrapper
    # does not expose). Parse into the underlying protobuf via .pb() and wrap.
    pb = ParseDict(
        filter_expression, FilterExpression.pb(FilterExpression()), ignore_unknown_fields=True
    )
    return FilterExpression.wrap(pb)


# ---------- custom reports ----------

REPORT_FORMATS = ("json", "csv", "md", "html", "pdf")


def save_report_def(name: str, definition: dict[str, Any]) -> Path:
    """Persist a custom report definition. Validates required keys."""
    if not definition.get("metrics"):
        raise ValueError("report definition needs at least one entry in 'metrics'")
    _ensure_dirs()
    payload = {**definition, "name": name}
    path = REPORTS_DIR / f"{_slug(name)}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def list_report_defs() -> list[dict[str, Any]]:
    _ensure_dirs()
    out = []
    for p in sorted(REPORTS_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "slug": p.stem,
                "name": data.get("name"),
                "description": data.get("description", ""),
                "metrics": data.get("metrics", []),
                "dimensions": data.get("dimensions", []),
            }
        )
    return out


def load_report_def(name: str) -> dict[str, Any]:
    path = REPORTS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"no report named {name!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def delete_report_def(name: str) -> dict[str, Any]:
    path = REPORTS_DIR / f"{_slug(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"no report named {name!r} at {path}")
    path.unlink()
    return {"status": "deleted", "name": name}


def run_report_def(
    name: str,
    property_id: str,
    days_override: int | None = None,
    format: str = "json",
    segment: str | None = None,
) -> Any:
    """Execute a saved report definition. Returns rows for json/csv, rendered
    string for html, file bytes for pdf (caller must write to disk)."""
    if format not in REPORT_FORMATS:
        raise ValueError(f"format must be one of {REPORT_FORMATS}")
    defn = load_report_def(name)
    days = days_override or defn.get("default_days", 28)

    from ga4_data import run_report

    rows = run_report(
        property_id=property_id,
        metrics=defn["metrics"],
        dimensions=defn.get("dimensions", []),
        days=days,
        include_metadata=True,
    )

    if segment:
        # Re-run with the segment's filter applied. We pass the raw filter dict
        # through ga4_data via a small extension instead of duplicating run_report.
        seg_def = load_segment(segment)
        rows = _apply_segment_and_rerun(property_id, defn, days, seg_def["filter_expression"])

    if format == "json":
        return {"definition": defn, "result": rows}
    if format == "csv":
        return _to_csv(rows)
    if format == "md":
        from ga4_report import render_custom_report_markdown

        return render_custom_report_markdown(defn, rows)
    if format == "html":
        from ga4_report import render_custom_report_html

        return render_custom_report_html(defn, rows)
    if format == "pdf":
        from ga4_report import render_custom_report_html, render_pdf_bytes

        html = render_custom_report_html(defn, rows)
        return render_pdf_bytes(html)
    return rows


def _apply_segment_and_rerun(property_id, defn, days, filter_expression):
    """runReport with a segment's filter applied as dimension_filter."""
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Metric,
        RunReportRequest,
    )
    from ga4_data import _get_data_client, _serialize_run_report, date_range

    start, end = date_range(days)
    req = RunReportRequest(
        property=f"properties/{property_id}",
        metrics=[Metric(name=m) for m in defn["metrics"]],
        dimensions=[Dimension(name=d) for d in defn.get("dimensions", [])],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimension_filter=build_filter_from_definition(filter_expression),
        return_property_quota=False,
    )
    client = _get_data_client()
    return _serialize_run_report(client.run_report(req), include_metadata=True)


def _to_csv(report_payload) -> str:
    rows = report_payload.get("rows", []) if isinstance(report_payload, dict) else []
    if not rows:
        return ""
    headers = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------- CLI ----------


def main():
    parser = argparse.ArgumentParser(description="Stored GA4 segments and custom reports")

    # segment commands
    parser.add_argument(
        "--save-segment",
        metavar="NAME",
        help="Save a shorthand segment (needs --field --op --value or --values)",
    )
    parser.add_argument("--field")
    parser.add_argument("--op")
    parser.add_argument("--value")
    parser.add_argument("--values", help="Comma-separated list for IN_LIST op")
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--save-segment-json",
        nargs=2,
        metavar=("NAME", "PATH"),
        help="Save a segment from a raw FilterExpression JSON file",
    )
    parser.add_argument("--list-segments", action="store_true")
    parser.add_argument("--delete-segment", metavar="NAME")

    # report commands
    parser.add_argument(
        "--save-report",
        nargs=2,
        metavar=("NAME", "PATH"),
        help="Save a custom report definition from a JSON file",
    )
    parser.add_argument("--list-reports", action="store_true")
    parser.add_argument("--delete-report", metavar="NAME")
    parser.add_argument("--run-report", metavar="NAME")
    parser.add_argument("--property")
    parser.add_argument("--days", type=int)
    parser.add_argument("--format", choices=REPORT_FORMATS, default="json")
    parser.add_argument("--segment", help="Apply a saved segment to the report run")
    parser.add_argument("--output", help="Write output to this path instead of stdout")

    args = parser.parse_args()

    try:
        out = _dispatch(args)
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1
    if out is None:
        parser.print_help()
        return 1
    _write_output(out, args)
    return 0


def _dispatch(args):
    if args.save_segment:
        if args.values:
            fe = {
                "field": args.field,
                "op": "IN_LIST",
                "values": [v.strip() for v in args.values.split(",") if v.strip()],
            }
        elif args.field and args.op and args.value is not None:
            fe = {"field": args.field, "op": args.op.upper(), "value": args.value}
        else:
            raise ValueError("--save-segment needs --field --op and either --value or --values")
        path = save_segment(args.save_segment, fe, args.description)
        return {"status": "saved", "path": str(path), "filter_expression": fe}
    if args.save_segment_json:
        name, path = args.save_segment_json
        fe = json.loads(Path(path).read_text(encoding="utf-8"))
        return {"status": "saved", "path": str(save_segment(name, fe, args.description))}
    if args.list_segments:
        return list_segments()
    if args.delete_segment:
        return delete_segment(args.delete_segment)
    if args.save_report:
        name, path = args.save_report
        defn = json.loads(Path(path).read_text(encoding="utf-8"))
        return {"status": "saved", "path": str(save_report_def(name, defn))}
    if args.list_reports:
        return list_report_defs()
    if args.delete_report:
        return delete_report_def(args.delete_report)
    if args.run_report:
        if not args.property:
            raise ValueError("--run-report requires --property")
        return run_report_def(
            args.run_report,
            args.property,
            days_override=args.days,
            format=args.format,
            segment=args.segment,
        )
    return None


def _write_output(out, args):
    if args.output:
        if isinstance(out, (bytes, bytearray)):
            Path(args.output).write_bytes(out)
        elif isinstance(out, str):
            Path(args.output).write_text(out, encoding="utf-8")
        else:
            Path(args.output).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"status": "ok", "output": args.output}))
    else:
        if isinstance(out, bytes):
            sys.stdout.buffer.write(out)
        elif isinstance(out, str):
            print(out)
        else:
            print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())
