"""Build local audience proposals from public filters. Never creates an audience."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys

from ga4_transport import error_result
from ga4_utils import scrub_pii, scrub_response

TEMPLATES = ("event_participants", "event_parameter_threshold", "event_sequence")
EVENT_SCOPE = "AUDIENCE_FILTER_SCOPE_WITHIN_SAME_EVENT"
SEQUENCE_SCOPE = "AUDIENCE_FILTER_SCOPE_ACROSS_ALL_SESSIONS"


def _event_expression(event_name, parameter=None, threshold=None):
    event = {"event_name": event_name}
    if parameter is not None:
        # Event-parameter expressions have a different grammar: one AND of leaves.
        event["event_parameter_filter_expression"] = {
            "and_group": {
                "filter_expressions": [
                    {
                        "dimension_or_metric_filter": {
                            "field_name": parameter,
                            "numeric_filter": {
                                "operation": "GREATER_THAN",
                                "value": {"double_value": threshold},
                            },
                        }
                    }
                ]
            }
        }
    # Top-level audience expressions require an AND containing OR groups.
    return {
        "and_group": {
            "filter_expressions": [{"or_group": {"filter_expressions": [{"event_filter": event}]}}]
        }
    }


@scrub_response
def audience_template(
    template,
    display_name,
    events,
    membership_days=30,
    parameter=None,
    threshold=None,
    window_seconds=None,
):
    from google.analytics.admin_v1alpha.types import Audience
    from google.protobuf.json_format import ParseDict

    if template not in TEMPLATES:
        raise ValueError("unknown audience template")
    if not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 100:
        raise ValueError("display_name must contain 1–100 characters")
    if type(membership_days) is not int or not 1 <= membership_days <= 540:
        raise ValueError("membership_days must be from 1 to 540")
    if (
        not isinstance(events, list)
        or not events
        or any(
            not isinstance(e, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", e)
            for e in events
        )
    ):
        raise ValueError("events must contain valid event names")
    if len(set(events)) != len(events):
        raise ValueError("event names must be unique")
    if scrub_pii({"display_name": display_name, "events": events, "parameter": parameter}) != {
        "display_name": display_name,
        "events": events,
        "parameter": parameter,
    }:
        raise ValueError("proposal contains values removed by privacy scrubbing")
    if template == "event_sequence":
        if (
            not 2 <= len(events) <= 5
            or type(window_seconds) is not int
            or not 1 <= window_seconds <= 30 * 86400
        ):
            raise ValueError("sequence requires 2–5 events and window_seconds from 1 to 2592000")
        if parameter is not None or threshold is not None:
            raise ValueError("sequence does not accept a numeric parameter threshold")
        clause = {
            "clause_type": "INCLUDE",
            "sequence_filter": {
                "scope": SEQUENCE_SCOPE,
                "sequence_maximum_duration": f"{window_seconds}s",
                "sequence_steps": [
                    {"scope": EVENT_SCOPE, "filter_expression": _event_expression(e)}
                    for e in events
                ],
            },
        }
        description = f"Complete the ordered events {', '.join(events)} within {window_seconds} seconds across sessions. Intervening events are allowed."
    else:
        if len(events) != 1 or window_seconds is not None:
            raise ValueError("simple templates require one event and no sequence window")
        if template == "event_parameter_threshold":
            if not isinstance(parameter, str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_]{0,39}", parameter
            ):
                raise ValueError("a numeric event parameter name is required")
            if parameter == "eventCount":
                raise ValueError(
                    "eventCount has special aggregate semantics; choose an event parameter"
                )
            if type(threshold) not in (float, int) or not math.isfinite(threshold):
                raise ValueError("threshold must be a finite number")
            description = f"An occurrence of {events[0]} with numeric {parameter} strictly greater than {threshold}. Not a lifetime-value or percentile audience."
        else:
            if parameter is not None or threshold is not None:
                raise ValueError("event_participants does not accept a threshold")
            description = (
                f"Users who trigger {events[0]}. No value, recency or disengagement condition."
            )
        clause = {
            "clause_type": "INCLUDE",
            "simple_filter": {
                "scope": EVENT_SCOPE,
                "filter_expression": _event_expression(events[0], parameter, threshold),
            },
        }
    definition = {
        "display_name": display_name,
        "description": description,
        "membership_duration_days": membership_days,
        "filter_clauses": [clause],
    }
    # Validate against the installed public schema without resolving any credentials.
    ParseDict(definition, Audience.pb(Audience()))
    return definition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", choices=TEMPLATES, required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--events", required=True, help="Comma-separated event names")
    parser.add_argument("--membership-days", type=int, default=30)
    parser.add_argument("--parameter")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--window-seconds", type=int)
    args = vars(parser.parse_args())
    args["events"] = args["events"].split(",")
    try:
        out = audience_template(**args)
    except Exception as exc:
        print(json.dumps(error_result(exc)), file=sys.stderr)
        return 1
    print(json.dumps(scrub_pii(out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
