"""No BigQuery jobs: SDK contracts and synthetic SQL execution in memory."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
import ga4_bigquery as bq
import ga4_mcp
import pytest
import sqlglot
from google.cloud import bigquery
from sqlglot import exp

BASE = dict(
    billing_project="billing-project",
    source_project="source-project",
    dataset="analytics_123",
    location="US",
    start_date="2026-09-01",
    end_date="2026-09-02",
    template="consent",
)


@pytest.fixture
def client(monkeypatch):
    client = Mock(spec=bigquery.Client)
    client.query.return_value = SimpleNamespace(total_bytes_processed=100)
    monkeypatch.setattr(bq, "_get_client", lambda *args: client)
    return client


def test_default_is_only_dry_run_with_bound_values(client):
    out = bq.aggregate_evidence(**BASE)
    assert out["status"] == "dry_run"
    assert client.query.call_count == 1
    args = client.query.call_args
    config = args.kwargs["job_config"]
    assert config.dry_run and config.maximum_bytes_billed == 1073741824
    assert config.use_legacy_sql is False and config.use_query_cache is False
    assert args.kwargs["retry"] is None and args.kwargs["job_retry"] is None
    assert "@start" in args.args[0]
    assert config.query_parameters[0].value == "20260901"


class Rows(list):
    total_rows = 1


def test_execution_retains_cap_and_only_returns_allowed_scrubbed_aggregates(client):
    job = Mock(spec=bigquery.QueryJob)
    job.job_id = "synthetic-job"
    job.total_bytes_processed = 100
    job.total_bytes_billed = 100
    job.result.return_value = Rows(
        [
            dict(
                analytics_storage="person@example.com",
                ads_storage="No",
                uses_transient_token="Yes",
                events=4,
                user_pseudo_id="secret",
            )
        ]
    )
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), job]
    out = bq.aggregate_evidence(**BASE, execute=True, max_bytes=200)
    assert out["complete"] and "secret" not in str(out) and "person@example.com" not in str(out)
    config = client.query.call_args.kwargs["job_config"]
    assert not config.dry_run and config.maximum_bytes_billed == 200
    assert int(config.job_timeout_ms) == 180000
    assert job.result.call_args.kwargs == dict(
        timeout=60, retry=None, job_retry=None, max_results=1000
    )


@pytest.mark.parametrize("estimate", [None, -1, 201])
def test_over_budget_or_unknown_estimate_never_executes(client, estimate):
    client.query.return_value.total_bytes_processed = estimate
    assert (
        bq.aggregate_evidence(**BASE, execute=True, max_bytes=200)["status"] == "execution_refused"
    )
    assert client.query.call_count == 1


def test_timeout_does_not_replay_job(client):
    job = Mock(spec=bigquery.QueryJob)
    job.job_id = "synthetic-job"
    job.result.side_effect = TimeoutError("person@example.com")
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), job]
    out = bq.aggregate_evidence(**BASE, execute=True)
    assert out["status"] == "outcome_unknown" and out["retryable"] is False
    assert out["job_id"] == client.query.call_args.kwargs["job_id"]
    assert "person@example.com" not in str(out)
    assert client.query.call_count == 2


@pytest.mark.parametrize(
    "update",
    [
        {"dataset": "x`; DELETE FROM y; --"},
        {"source_project": "bad.project"},
        {"billing_project": "bad"},
        {"location": "US;"},
        {"start_date": "yesterday"},
        {"end_date": "2026-10-31"},
        {"end_date": "2026-08-31"},
        {"max_bytes": 0},
        {"execute": "yes"},
        {"template": "arbitrary_sql"},
        {"template": "parameters", "event_name": "purchase", "parameters": []},
        {"template": "parameters", "event_name": "purchase", "parameters": ["value", "value"]},
        {"template": "funnel", "steps": ["start"]},
        {"template": "funnel", "steps": ["start", "end"], "window_seconds": 0},
    ],
)
def test_invalid_input_never_resolves_client(client, update):
    with pytest.raises(ValueError):
        bq.aggregate_evidence(**(BASE | update))
    client.query.assert_not_called()


def evaluate(template, rows, **kwargs):
    """Execute the actual generated SELECT after dialect-only translation."""
    sql, values = bq.build_query(
        "source-project", "analytics_123", "2026-09-01", "2026-09-02", template, **kwargs
    )
    tree = sqlglot.parse_one(sql, read="bigquery")
    assert isinstance(tree, (exp.Select, exp.Union))
    assert not list(tree.find_all(exp.Insert, exp.Delete, exp.Update, exp.Create, exp.Command))
    values = {n: v for n, _, v in values}

    def replace(node):
        if isinstance(node, exp.Parameter):
            return exp.convert(values[node.name])
        if isinstance(node, exp.Table) and node.catalog == "source-project":
            return exp.to_table("fixture")
        return node

    translated = tree.transform(replace).sql(dialect="duckdb")
    with duckdb.connect(":memory:") as conn:
        conn.execute("""CREATE TABLE fixture (_TABLE_SUFFIX VARCHAR, event_date VARCHAR,
          event_name VARCHAR, event_timestamp BIGINT, user_pseudo_id VARCHAR,
          privacy_info STRUCT(analytics_storage VARCHAR, ads_storage VARCHAR, uses_transient_token VARCHAR),
          event_params STRUCT(key VARCHAR, value STRUCT(string_value VARCHAR, int_value BIGINT,
                                                       double_value DOUBLE, float_value DOUBLE))[])""")
        for row in rows:
            conn.execute("INSERT INTO fixture VALUES (?, ?, ?, ?, ?, ?, ?)", row)
        result = conn.execute(translated)
        return [dict(zip([d[0] for d in result.description], row)) for row in result.fetchall()]


def event(name="purchase", time=1, user="synthetic", params=None, suffix="20260901"):
    return (
        suffix,
        "20260901",
        name,
        time,
        user,
        dict(analytics_storage="No", ads_storage="Unset", uses_transient_token="Yes"),
        params or [],
    )


def param(key, value=None):
    return dict(
        key=key, value=dict(string_value=value, int_value=None, double_value=None, float_value=None)
    )


def test_parameter_coverage_counts_events_not_duplicate_keys_and_zero_is_usable():
    zero = param("value")
    zero["value"]["int_value"] = 0
    rows = [
        event(params=[param("value", ""), param("value", "")]),
        event(params=[zero]),
        event(),
        event(params=[param("value", "outside")], suffix="intraday_20260901"),
    ]
    assert evaluate("parameters", rows, event_name="purchase", parameters=["value"]) == [
        dict(parameter="value", events=3, present=2, usable=1)
    ]


def test_consent_and_freshness_daily_only():
    rows = [event(time=10), event(time=20), event(time=30, suffix="intraday_20260901")]
    assert evaluate("consent", rows) == [
        dict(analytics_storage="No", ads_storage="Unset", uses_transient_token="Yes", events=2)
    ]
    assert evaluate("freshness", rows) == [
        dict(
            latest_event_micros=20, latest_event_date="20260901", events=2, observed_daily_tables=1
        )
    ]


def test_funnel_requires_order_and_first_entry_window_without_returning_identifiers():
    rows = [
        event("start", 1, "a"),
        event("end", 2, "a"),
        event("end", 1, "b"),
        event("start", 2, "b"),
        event("start", 1, "c"),
        event("end", 1000002, "c"),
        event("start", 1, None),
        event("end", 2, None),
        event("start", 1, "d"),
        event("end", 1, "d"),
    ]
    assert evaluate("funnel", rows, steps=["start", "end"], window_seconds=1) == [
        dict(step=1, event_name="start", users=4),
        dict(step=2, event_name="end", users=1),
    ]


def test_cli_dry_run_and_error_are_scrubbed(client, monkeypatch, capsys):
    flags = ["bigquery"]
    for key, value in BASE.items():
        flags += ["--" + key.replace("_", "-"), value]
    monkeypatch.setattr("sys.argv", flags)
    assert bq.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    client.query.side_effect = RuntimeError("person@example.com")
    assert bq.main() == 1
    assert "person@example.com" not in capsys.readouterr().err


def test_mcp_cannot_request_execution(client):
    out = ga4_mcp.bigquery_dry_run(**BASE)
    assert out["status"] == "dry_run" and client.query.call_count == 1
    with pytest.raises(TypeError):
        bq.aggregate_evidence(**BASE, arbitrary_sql="SELECT *")


def test_client_uses_bigquery_scope_and_explicit_project(monkeypatch):
    import google.auth
    from google.auth.credentials import AnonymousCredentials

    credentials = AnonymousCredentials()
    resolver = Mock(return_value=(credentials, "ignored-adc-project"))
    factory = Mock()
    monkeypatch.setattr(google.auth, "default", resolver)
    monkeypatch.setattr(bigquery, "Client", factory)
    bq._get_client("billing-project", "EU")
    resolver.assert_called_once_with(scopes=["https://www.googleapis.com/auth/bigquery"])
    factory.assert_called_once_with(
        project="billing-project", credentials=credentials, location="EU"
    )


def test_missing_optional_client_does_not_resolve_credentials(monkeypatch):
    import builtins

    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "google.cloud":
            raise ImportError("optional client absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    factory = Mock()
    monkeypatch.setattr(bq, "_get_client", factory)
    assert bq.aggregate_evidence(**BASE)["status"] == "unsupported"
    factory.assert_not_called()
