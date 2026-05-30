"""
Full GA4 audit, end-to-end, from a single command. Works on any runtime.

Inside Claude Code the audit is normally driven by the markdown skills
(LLM-powered specialist subagents). This driver runs the deterministic
equivalent — a mechanical baseline audit — so Codex, Gemini, or a plain
shell user gets the same shape of output without orchestrating eight
scripts by hand.

What it does:

  1. verify auth
  2. profile the live site (ga4_context.build_property_context)
  3. fetch property summary (ga4_admin.get_property_details)
  4. run the analysis "agents" — each is a Python function that calls
     the existing adapters, computes findings against the documented
     thresholds, stamps benchmarkable metrics, and returns the standard
     `{agent, summary, findings, data}` dict
  5. render a markdown / HTML / PDF report with benchmark verdicts and
     the property-context section attached

Parallel-eligible agents run concurrently via ThreadPoolExecutor.

CLI:
  python scripts/ga4_audit.py --property <id>                  # markdown to stdout
  python scripts/ga4_audit.py --property <id> --output audit.md
  python scripts/ga4_audit.py --property <id> --format html --output audit.html
  python scripts/ga4_audit.py --property <id> --vertical saas  # override benchmark vertical
  python scripts/ga4_audit.py --property <id> --funnel-steps view_item,add_to_cart,purchase
  python scripts/ga4_audit.py --property <id> --refresh-context
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import ga4_admin
import ga4_auth
import ga4_context
import ga4_data
import ga4_events
import ga4_funnel
import ga4_report
import ga4_utils


# ---------- Helpers ----------


def _ok(agent, summary, findings=None, data=None):
    return {
        "agent": agent,
        "summary": summary,
        "findings": findings or [],
        "data": data or {},
    }


def _safe_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------- Quality ----------


def run_quality(property_id, days=28):
    findings = []
    data = {}
    summary_bits = []

    sampling_pct = 0.0
    not_set_share = 0.0
    direct_share = 0.0

    try:
        sessions_report = ga4_data.run_report(
            property_id=property_id,
            metrics=["sessions"],
            dimensions=["date"],
            days=days,
            include_metadata=True,
        )
        meta = sessions_report.get("metadata", {})
        sm = (meta.get("sampling") or [{}])[0]
        sampling_pct = 1.0 - (sm.get("sample_rate") or 1.0) if sm else 0.0
        sampling_pct = max(0.0, sampling_pct)
        data["sampling_pct"] = sampling_pct
        data["currency_code"] = meta.get("currency_code")
        data["time_zone"] = meta.get("time_zone")
    except Exception as e:
        findings.append(
            {
                "severity": "High",
                "title": "Could not query Data API for sampling check",
                "detail": f"{type(e).__name__}: {e}",
            }
        )

    try:
        src_report = ga4_data.run_report(
            property_id=property_id,
            metrics=["sessions"],
            dimensions=["sessionSource"],
            days=days,
        )
        total = 0
        not_set = 0
        direct = 0
        for row in src_report["rows"]:
            count = _safe_int(row.get("sessions"))
            total += count
            src = (row.get("sessionSource") or "").lower()
            if src in {"(not set)", "(not_set)", ""}:
                not_set += count
            if src in {"(direct)", "direct"}:
                direct += count
        if total:
            not_set_share = not_set / total
            direct_share = direct / total
            data["sessions_total"] = total
            data["direct_share"] = direct_share
            data["not_set_share"] = not_set_share
    except Exception as e:
        findings.append(
            {
                "severity": "Medium",
                "title": "Could not query sessionSource breakdown",
                "detail": f"{type(e).__name__}: {e}",
            }
        )

    if sampling_pct > 0.10:
        findings.append(
            {
                "severity": "High",
                "title": "Sampling rate above 10% on 28-day session report",
                "detail": "Long-window queries are being sampled. Findings on this window are directional only.",
                "metric": "sampling_pct",
                "metric_value": round(sampling_pct, 4),
            }
        )
    elif sampling_pct > 0.01:
        findings.append(
            {
                "severity": "Medium",
                "title": "Visible sampling on 28-day session report",
                "detail": f"Sampling rate {sampling_pct:.1%}. Verify high-stakes findings on a shorter window.",
                "metric": "sampling_pct",
                "metric_value": round(sampling_pct, 4),
            }
        )

    if direct_share > 0.30:
        sev = "Critical" if direct_share > 0.50 else "High"
        findings.append(
            {
                "severity": sev,
                "title": "High (direct)/(none) share",
                "detail": f"{direct_share:.1%} of sessions attributed to direct. UTM tagging gaps, lost referrers on payment-gateway redirect-back, or missing GTM container on some pages are likely.",
                "metric": "direct_share",
                "metric_value": round(direct_share, 4),
            }
        )

    if not_set_share > 0.05:
        sev = "High" if not_set_share > 0.10 else "Medium"
        findings.append(
            {
                "severity": sev,
                "title": "High (not set) share on sessionSource",
                "detail": f"{not_set_share:.1%} of sessions have (not set) source. Server-side tag misconfiguration or cross-domain handoff dropping referrers.",
                "metric": "not_set_share",
                "metric_value": round(not_set_share, 4),
            }
        )

    confidence = ga4_utils.format_confidence(sampling_pct * 100, not_set_share * 100)
    data["confidence_label"] = confidence
    summary_bits.append(f"data confidence {confidence}")
    if direct_share:
        summary_bits.append(f"direct share {direct_share:.1%}")
    if sampling_pct:
        summary_bits.append(f"sampling {sampling_pct:.1%}")

    return _ok(
        "ga4-quality", "; ".join(summary_bits) or "data quality scan complete", findings, data
    )


# ---------- Events ----------


def run_events(property_id, days=7):
    findings = []
    data = {}

    try:
        listed = ga4_events.list_events(property_id, days=days)
        present = {row["eventName"]: _safe_int(row.get("eventCount")) for row in listed["rows"]}
        data["distinct_event_count"] = len(present)
        data["top_events"] = dict(sorted(present.items(), key=lambda kv: -kv[1])[:20])
    except Exception as e:
        return _ok(
            "ga4-events",
            f"events fetch failed: {e}",
            [
                {
                    "severity": "High",
                    "title": "Could not list events from Data API",
                    "detail": str(e),
                }
            ],
        )

    ecomm_events = ["view_item", "add_to_cart", "begin_checkout", "add_payment_info", "purchase"]
    fires_count = sum(1 for e in ecomm_events if present.get(e, 0) > 0)
    data["ecomm_events_present"] = [e for e in ecomm_events if present.get(e, 0) > 0]
    data["ecomm_events_missing"] = [e for e in ecomm_events if present.get(e, 0) == 0]

    if fires_count == len(ecomm_events):
        # Full ecomm taxonomy — validate parameter coverage on the critical events.
        for ev in ("purchase", "add_to_cart"):
            try:
                coverage = ga4_events.event_params_coverage(property_id, ev, days=days)
                data.setdefault("param_coverage", {})[ev] = coverage
                for param, info in coverage.get("coverage", {}).items():
                    pct = info.get("coverage_pct")
                    if pct is None or pct >= 95:
                        continue
                    sev = "Critical" if pct < 60 else "High"
                    findings.append(
                        {
                            "severity": sev,
                            "title": f"{ev}.{param} coverage below 95%",
                            "detail": f"{ev} fires with {param} on only {pct}% of events in the {days}-day window.",
                        }
                    )
            except Exception as e:
                findings.append(
                    {
                        "severity": "Low",
                        "title": f"Could not check parameter coverage for {ev}",
                        "detail": str(e),
                    }
                )

    elif fires_count == 0:
        findings.append(
            {
                "severity": "Medium",
                "title": "No recommended e-commerce events fire on this property",
                "detail": "If this is an e-commerce property, instrument the GA4 recommended events. If not, ignore — this audit's funnel preset is e-commerce; pass --funnel-steps for a custom funnel.",
            }
        )

    else:
        missing = data["ecomm_events_missing"]
        findings.append(
            {
                "severity": "High",
                "title": "Partial e-commerce taxonomy",
                "detail": f"{fires_count} of 5 recommended events fire. Missing: {', '.join(missing)}.",
            }
        )

    return _ok(
        "ga4-events",
        f"{len(present)} distinct events, {fires_count}/{len(ecomm_events)} ecomm-preset events present",
        findings,
        data,
    )


# ---------- Funnel ----------


def run_funnel(property_id, steps=None, days=28, check_postpayment=False):
    if not steps:
        return _ok(
            "ga4-funnel",
            "skipped — no funnel steps provided and no preset auto-selected",
            [],
            {"steps": []},
        )
    try:
        result = ga4_funnel.build_funnel(
            property_id=property_id,
            steps=steps,
            days=days,
            check_postpayment=check_postpayment,
        )
    except Exception as e:
        return _ok(
            "ga4-funnel",
            f"funnel failed: {e}",
            [{"severity": "High", "title": "Funnel report failed", "detail": str(e)}],
        )

    if "error" in result:
        return _ok(
            "ga4-funnel",
            result["error"],
            [
                {
                    "severity": "Critical",
                    "title": "Funnel could not be built",
                    "detail": result["error"],
                },
            ],
            result,
        )

    findings = []
    agg = (result.get("rates") or {}).get("aggregate") or {}
    overall_cr = agg.get("overall_conversion_pct", 0) / 100.0
    if overall_cr:
        findings.append(
            {
                "severity": "Low",
                "title": "Overall funnel conversion rate",
                "detail": f"View-to-conversion: {overall_cr:.2%} across the {result.get('window_days')}-day window.",
                "metric": "conversion_rate",
                "metric_value": round(overall_cr, 5),
            }
        )

    leakiest = agg.get("leakiest_step")
    if leakiest and leakiest.get("users_dropped"):
        findings.append(
            {
                "severity": "High",
                "title": f"Leakiest step: {leakiest['from']} → {leakiest['to']}",
                "detail": (
                    f"{leakiest['users_dropped']:,} users lost at this step "
                    f"({leakiest.get('share_of_total_loss_pct', 0)}% of total funnel loss). "
                    "Focus instrumentation and UX investigation here first."
                ),
            }
        )

    for w in result.get("warnings", []):
        findings.append(
            {
                "severity": "Critical" if "post-payment" in w.lower() else "Medium",
                "title": "Funnel warning",
                "detail": w,
            }
        )

    return _ok(
        "ga4-funnel",
        f"funnel steps {' → '.join(result['steps'])}, overall CR {overall_cr:.2%}",
        findings,
        result,
    )


# ---------- Conversions ----------


def run_conversions(property_id):
    findings = []
    try:
        key_events = ga4_admin.list_key_events(property_id)
    except Exception as e:
        return _ok(
            "ga4-conversions",
            f"key events fetch failed: {e}",
            [{"severity": "High", "title": "Could not list key events", "detail": str(e)}],
        )

    names = [k.get("eventName") or k.get("event_name") for k in key_events]
    count = len(key_events)
    data = {"key_event_count": count, "key_event_names": names}

    if count == 0:
        findings.append(
            {
                "severity": "Critical",
                "title": "No key events configured",
                "detail": "Without at least one key event, attribution and standard conversion reports are empty. Mark the property's primary conversion event as a key event.",
            }
        )
    elif count < 2:
        findings.append(
            {
                "severity": "Medium",
                "title": "Only one key event configured",
                "detail": "Add a funnel-shaping event (begin_checkout, add_to_cart, generate_lead) so default GA4 conversion reports cover more of the funnel.",
            }
        )
    elif count > 30:
        findings.append(
            {
                "severity": "High",
                "title": "Too many key events configured",
                "detail": f"{count} key events on this property (limit 30). Ads import will reject the overflow; thinning the list improves bid-signal quality.",
            }
        )

    return _ok("ga4-conversions", f"{count} key event(s) configured", findings, data)


# ---------- Attribution ----------


def run_attribution(property_id, days=28, primary_event="purchase"):
    findings = []
    data: dict[str, Any] = {}

    try:
        settings = ga4_admin.get_attribution_settings(property_id)
        data["attribution_settings"] = settings
        if not isinstance(settings, dict) or settings.get("error"):
            findings.append(
                {
                    "severity": "Low",
                    "title": "Could not read attribution settings",
                    "detail": str(
                        settings.get("error") if isinstance(settings, dict) else settings
                    ),
                }
            )
    except Exception as e:
        findings.append(
            {
                "severity": "Medium",
                "title": "Attribution settings request failed",
                "detail": str(e),
            }
        )

    try:
        channel_report = ga4_data.run_report(
            property_id=property_id,
            metrics=["eventCount"],
            dimensions=["sessionDefaultChannelGroup"],
            filter_expr=f"eventName = '{primary_event}'",
            days=days,
        )
        rows = channel_report["rows"]
        data["channel_breakdown"] = rows
        total = sum(_safe_int(r.get("eventCount")) for r in rows)
        if total > 0:
            direct = sum(
                _safe_int(r.get("eventCount"))
                for r in rows
                if (r.get("sessionDefaultChannelGroup") or "").lower() in {"direct", "(direct)"}
            )
            share = direct / total
            data["primary_event_direct_share"] = share
            if share > 0.30:
                findings.append(
                    {
                        "severity": "High" if share <= 0.50 else "Critical",
                        "title": "Direct share on primary conversion above 30%",
                        "detail": f"{share:.1%} of `{primary_event}` events attribute to direct. UTM tagging gaps or lost referrers on payment-gateway redirect-back are the usual cause.",
                        "metric": "direct_share",
                        "metric_value": round(share, 4),
                    }
                )
    except Exception as e:
        findings.append(
            {
                "severity": "Medium",
                "title": "Channel breakdown for primary event failed",
                "detail": str(e),
            }
        )

    return _ok(
        "ga4-attribution",
        f"attribution scan against `{primary_event}`",
        findings,
        data,
    )


# ---------- Property ----------


def run_property(property_id):
    findings = []
    data: dict[str, Any] = {}

    try:
        details = ga4_admin.get_property_details(property_id)
        data["property"] = details
        retention = details.get("dataRetentionSettings", {}).get(
            "eventDataRetention"
        ) or details.get("data_retention_settings", {}).get("event_data_retention")
        if retention and retention not in {"FOURTEEN_MONTHS", "FIFTY_MONTHS"}:
            findings.append(
                {
                    "severity": "High",
                    "title": "Data retention shorter than 14 months",
                    "detail": f"Event-data retention is {retention}. For multi-month cohort analysis set to FOURTEEN_MONTHS in Admin → Data Settings → Data Retention.",
                }
            )
    except Exception as e:
        findings.append(
            {"severity": "High", "title": "Could not fetch property details", "detail": str(e)}
        )

    try:
        streams = ga4_admin.list_data_streams(property_id)
        data["streams"] = streams
        if not streams:
            findings.append(
                {
                    "severity": "Critical",
                    "title": "No data streams configured",
                    "detail": "Property has no streams; nothing is being collected.",
                }
            )
    except Exception as e:
        findings.append(
            {"severity": "Medium", "title": "Could not list data streams", "detail": str(e)}
        )

    try:
        filters = ga4_admin.list_data_filters(property_id)
        data["data_filters"] = filters
        for f in filters:
            if isinstance(f, dict) and f.get("filterState") == "TEST":
                findings.append(
                    {
                        "severity": "Medium",
                        "title": f"Data filter `{f.get('displayName') or f.get('name')}` is in Testing mode",
                        "detail": "Testing-mode filters do not actually exclude traffic. Activate or delete.",
                    }
                )
    except Exception as e:
        findings.append(
            {"severity": "Low", "title": "Could not list data filters", "detail": str(e)}
        )

    try:
        defs_ = ga4_admin.list_custom_defs(property_id)
        data["custom_defs"] = {
            "dimension_count": len(defs_.get("custom_dimensions") or []),
            "metric_count": len(defs_.get("custom_metrics") or []),
        }
    except Exception as e:
        findings.append(
            {"severity": "Low", "title": "Could not list custom defs", "detail": str(e)}
        )

    return _ok("ga4-property", "property configuration scan complete", findings, data)


# ---------- Segments stub ----------


def run_segments_stub():
    return _ok(
        "ga4-segments",
        "stub — run `/ga4 segments <property-id>` (or the Claude Code skill) for cohort breakdowns",
        [],
        {"hint": "cohort analysis is LLM-driven in the full Claude skill; this driver omits it"},
    )


SEGMENT_COHORT_DIMENSIONS = ["deviceCategory", "newVsReturning", "sessionDefaultChannelGroup"]
SEGMENT_MIN_SHARE = 0.10
SEGMENT_UNDERPERF_FACTOR = 0.5
SEGMENT_HIGH_FACTOR = 0.4
SEGMENT_HIGH_SHARE = 0.25


def _cohort_rate(row, mode):
    sessions = _safe_int(row.get("sessions"))
    if mode == "conversion":
        return (_safe_int(row.get("keyEvents")) / sessions) if sessions else 0.0, sessions
    return _safe_float(row.get("engagementRate")), sessions


def _cohort_rows(report, mode):
    dim = report["dimensions"][0]
    rows = []
    for r in report["rows"]:
        rate, sessions = _cohort_rate(r, mode)
        rows.append({"cohort": r.get(dim), "sessions": sessions, "rate": rate})
    return rows


def _weighted_avg(rows):
    total = sum(c["sessions"] for c in rows)
    if not total:
        return 0.0, 0
    return sum(c["sessions"] * c["rate"] for c in rows) / total, total


def _underperf_finding(label, name, rate, avg, share, metric_label):
    """Return a finding dict if `rate` is materially below `avg`, else None."""
    if avg <= 0 or rate > SEGMENT_UNDERPERF_FACTOR * avg:
        return None
    high = rate <= SEGMENT_HIGH_FACTOR * avg and share >= SEGMENT_HIGH_SHARE
    return {
        "severity": "High" if high else "Medium",
        "title": f"Underperforming {label}: {name}",
        "detail": (
            f"{name} sits at {rate:.2%} vs the property average {avg:.2%} "
            f"({share:.0%} of sessions on this breakdown). Investigate for "
            "tracking gaps or UX friction."
        ),
        "metric": metric_label,
        "metric_value": round(rate, 5),
    }


def run_segments(property_id, days=28):
    findings = []
    data = {"cohorts": {}}

    mode = "conversion"
    metrics = ["sessions", "keyEvents"]
    probe = None
    try:
        probe = ga4_data.run_report(
            property_id=property_id,
            metrics=metrics,
            dimensions=[SEGMENT_COHORT_DIMENSIONS[0]],
            days=days,
        )
        if sum(_safe_int(r.get("keyEvents")) for r in probe["rows"]) == 0:
            mode = "engagement"
    except Exception:
        mode = "engagement"

    if mode == "engagement":
        metrics = ["sessions", "engagementRate"]
        probe = None
    metric_label = "conversion_rate" if mode == "conversion" else "engagement_rate"
    data["mode"] = mode
    baseline = None

    for i, dim in enumerate(SEGMENT_COHORT_DIMENSIONS):
        report = (
            probe
            if (i == 0 and probe is not None)
            else ga4_data.run_report(
                property_id=property_id, metrics=metrics, dimensions=[dim], days=days
            )
        )
        rows = _cohort_rows(report, mode)
        avg, total = _weighted_avg(rows)
        data["cohorts"][dim] = {"property_avg": round(avg, 5), "rows": rows}
        if dim == "deviceCategory":
            baseline = avg if total else None
        if not total or avg <= 0:
            continue
        material = [c for c in rows if c["sessions"] / total >= SEGMENT_MIN_SHARE]
        if not material:
            continue
        worst = min(material, key=lambda c: c["rate"])
        f = _underperf_finding(
            dim,
            f"{dim} = {worst['cohort']}",
            worst["rate"],
            avg,
            worst["sessions"] / total,
            metric_label,
        )
        if f:
            findings.append(f)

    data["property_baseline"] = round(baseline, 5) if baseline is not None else None
    data["saved_segments"] = []
    return _ok(
        "ga4-segments",
        f"cohort scan ({mode} mode): {len(findings)} finding(s)",
        findings,
        data,
    )


# ---------- Orchestrator ----------

PARALLEL_GATE_AGENTS = ("context", "quality", "property")


def _resolve_funnel_steps(args, events_output):
    if args.funnel_steps:
        return [s.strip() for s in args.funnel_steps.split(",") if s.strip()]
    present = (events_output.get("data") or {}).get("ecomm_events_present") or []
    if len(present) >= 4:
        return present  # auto-select what fires from the ecomm preset
    return []


def orchestrate(
    property_id,
    days=28,
    funnel_steps_arg=None,
    vertical_override=None,
    check_postpayment=False,
    refresh_context=False,
    primary_event="purchase",
):
    """Run the full audit. Returns (agents_output, context, vertical, confidence)."""
    # gate
    context_payload = ga4_context.build_property_context(property_id, force=refresh_context)
    context = context_payload.get("context") if isinstance(context_payload, dict) else None
    inferred_vertical = None
    if context and isinstance(context.get("site"), dict):
        inferred_vertical = (context["site"].get("inferred") or {}).get("vertical")
    vertical = vertical_override or inferred_vertical or "other"

    agents_output: list[dict[str, Any]] = []

    # ga4-context "agent" — wrap the analyzer output in the agent envelope so
    # the report has a context summary line in its executive section.
    site = (context or {}).get("site") or {}
    summary = site.get("summary") or "context profile complete"
    agents_output.append(_ok("ga4-context", summary, [], {"context": context}))

    # parallel: quality + property
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_quality = ex.submit(run_quality, property_id, days)
        f_property = ex.submit(run_property, property_id)
        quality_out = f_quality.result()
        property_out = f_property.result()

    # events gate (depends on Data API up)
    events_out = run_events(property_id, days=min(days, 7))

    # parallel fan-out
    funnel_steps = _resolve_funnel_steps(_Namespace(funnel_steps=funnel_steps_arg), events_out)
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_funnel = ex.submit(run_funnel, property_id, funnel_steps, days, check_postpayment)
        f_conv = ex.submit(run_conversions, property_id)
        f_seg = ex.submit(run_segments_stub)
        funnel_out = f_funnel.result()
        conv_out = f_conv.result()
        seg_out = f_seg.result()

    # conditional attribution
    key_count = (conv_out.get("data") or {}).get("key_event_count", 0)
    attribution_out = (
        run_attribution(property_id, days=days, primary_event=primary_event)
        if key_count > 0
        else _ok(
            "ga4-attribution", "skipped — no key events configured", [], {"reason": "no_key_events"}
        )
    )

    agents_output.extend(
        [
            quality_out,
            events_out,
            funnel_out,
            seg_out,
            conv_out,
            attribution_out,
            property_out,
        ]
    )

    confidence = (quality_out.get("data") or {}).get("confidence_label", "medium")
    return agents_output, context, vertical, confidence


class _Namespace:
    """Tiny stand-in for argparse.Namespace so _resolve_funnel_steps can be reused."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------- CLI ----------


def main():
    parser = argparse.ArgumentParser(description="Full GA4 audit, one command, any runtime")
    parser.add_argument("--property", required=True)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument(
        "--funnel-steps",
        help="Comma-separated event names; otherwise auto-detected from ecomm preset overlap",
    )
    parser.add_argument(
        "--vertical", help="Override the benchmark vertical (else taken from ga4-context inference)"
    )
    parser.add_argument(
        "--check-postpayment",
        action="store_true",
        help="Run the post-payment heuristic against add_payment_info",
    )
    parser.add_argument(
        "--refresh-context",
        action="store_true",
        help="Re-fetch the live site even if a cached profile exists",
    )
    parser.add_argument(
        "--primary-event",
        default="purchase",
        help="Primary conversion event for attribution checks (default: purchase)",
    )
    parser.add_argument("--format", choices=["md", "html", "pdf", "json"], default="md")
    parser.add_argument("--output", help="Write report to this path instead of stdout")
    args = parser.parse_args()

    # auth gate
    try:
        ga4_auth.get_credentials(write=False)
    except ga4_auth.AuthRequiredError as e:
        print(json.dumps({"error": "no_credentials", "hint": e.hint}), file=sys.stderr)
        return 2

    try:
        agents_output, context, vertical, confidence = orchestrate(
            property_id=args.property,
            days=args.days,
            funnel_steps_arg=args.funnel_steps,
            vertical_override=args.vertical,
            check_postpayment=args.check_postpayment,
            refresh_context=args.refresh_context,
            primary_event=args.primary_event,
        )
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}), file=sys.stderr)
        return 1

    body: str | bytes
    if args.format == "json":
        body = json.dumps(
            {
                "property_id": args.property,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "confidence": confidence,
                "vertical": vertical,
                "context": context,
                "agents": agents_output,
            },
            indent=2,
            default=str,
        )
    elif args.format == "md":
        body = ga4_report.render_markdown(
            args.property,
            agents_output,
            confidence=confidence,
            context=context,
            vertical=vertical,
        )
    elif args.format == "html":
        body = ga4_report.render_html(args.property, agents_output, confidence=confidence)
    else:
        html = ga4_report.render_html(args.property, agents_output, confidence=confidence)
        body = ga4_report.render_pdf_bytes(html)

    if args.output:
        path = Path(args.output)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "output": str(path),
                    "format": args.format,
                    "confidence": confidence,
                    "vertical": vertical,
                }
            )
        )
    else:
        if isinstance(body, bytes):
            sys.stdout.buffer.write(body)
        else:
            print(body)

    return 0


if __name__ == "__main__":
    sys.exit(main())
