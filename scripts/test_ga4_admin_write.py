"""Tests for ga4_admin write surfaces.

The Admin client itself is mocked. These tests assert that we call the
right method on the right client variant and that the validation layer
rejects bad input before hitting the network.
"""

from unittest.mock import MagicMock, patch

import ga4_admin
import pytest

# ---------- parameter name validation ----------


def test_validate_param_name_accepts_simple():
    ga4_admin._validate_parameter_name("brand", "EVENT")


def test_validate_param_name_rejects_leading_digit():
    with pytest.raises(ValueError, match="must start with a letter"):
        ga4_admin._validate_parameter_name("1brand", "EVENT")


def test_validate_param_name_rejects_invalid_chars():
    with pytest.raises(ValueError, match="must start with a letter"):
        ga4_admin._validate_parameter_name("brand-x", "EVENT")


def test_validate_param_name_rejects_too_long_event():
    with pytest.raises(ValueError, match="exceeds 40"):
        ga4_admin._validate_parameter_name("a" * 41, "EVENT")


def test_validate_param_name_user_scope_limit_is_24():
    ga4_admin._validate_parameter_name("a" * 24, "USER")
    with pytest.raises(ValueError, match="exceeds 24"):
        ga4_admin._validate_parameter_name("a" * 25, "USER")


def test_validate_param_name_rejects_unknown_scope():
    with pytest.raises(ValueError, match="unknown scope"):
        ga4_admin._validate_parameter_name("brand", "SESSION")


# ---------- audience duration validation ----------


def test_create_audience_rejects_over_540_days(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: mock_client)
    with pytest.raises(ValueError, match="membership_duration_days"):
        ga4_admin.create_audience("123", {"display_name": "x", "membership_duration_days": 600})
    mock_client.create_audience.assert_not_called()


# ---------- key event limit ----------


def test_create_key_event_blocks_at_limit(monkeypatch):
    monkeypatch.setattr(
        ga4_admin, "list_key_events", lambda pid: [{"name": f"ke-{i}"} for i in range(30)]
    )
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: mock_client)
    with pytest.raises(ValueError, match="limit 30"):
        ga4_admin.create_key_event("123", "purchase")
    mock_client.create_key_event.assert_not_called()


def test_create_key_event_under_limit_calls_api(monkeypatch):
    monkeypatch.setattr(ga4_admin, "list_key_events", lambda pid: [])
    mock_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp._pb = {"name": "properties/123/keyEvents/abc", "eventName": "purchase"}
    mock_client.create_key_event.return_value = fake_resp

    fake_types = MagicMock()
    fake_types.KeyEvent.CountingMethod = {"ONCE_PER_EVENT": 1}

    with patch.dict(
        "sys.modules",
        {
            "google.analytics.admin_v1beta": MagicMock(),
            "google.analytics.admin_v1beta.types": fake_types,
        },
    ):
        monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: mock_client)
        with patch.object(ga4_admin, "_proto_to_dict", return_value={"event_name": "purchase"}):
            out = ga4_admin.create_key_event("123", "purchase")
    assert mock_client.create_key_event.called
    assert out["event_name"] == "purchase"


# ---------- event rule deletes pass through ----------


def test_delete_event_edit_rule_calls_alpha(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: mock_client)
    out = ga4_admin.delete_event_edit_rule("properties/123/dataStreams/9/eventEditRules/55")
    assert out["status"] == "deleted"
    mock_client.delete_event_edit_rule.assert_called_once_with(
        name="properties/123/dataStreams/9/eventEditRules/55"
    )


def test_archive_audience_calls_alpha(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(ga4_admin, "_get_admin_alpha_client", lambda write=False: mock_client)
    out = ga4_admin.archive_audience("properties/123/audiences/55")
    assert out["status"] == "archived"
    # archive_audience has no flattened `name` parameter in the Admin SDK -
    # it only takes `request`. Asserting the flattened form passed against a
    # MagicMock while failing against the real client.
    mock_client.archive_audience.assert_called_once_with(
        request={"name": "properties/123/audiences/55"}
    )


# ---------- writes invalidate the cached reads they change ----------


class _FakeAdminClient:
    """In-memory Admin client: reads return the current state, writes change it.
    Resource IDs are the event/parameter names, so a delete of
    properties/123/keyEvents/sign_up removes "sign_up"."""

    def __init__(self, key_events=(), dims=(), metrics=()):
        self.key_events = list(key_events)
        self.dims = list(dims)
        self.metrics = list(metrics)

    def list_key_events(self, parent):
        return list(self.key_events)

    def create_key_event(self, parent, key_event):
        self.key_events.append(key_event.event_name)
        return key_event

    def delete_key_event(self, name):
        self.key_events.remove(name.rsplit("/", 1)[1])

    def list_custom_dimensions(self, parent):
        return list(self.dims)

    def list_custom_metrics(self, parent):
        return list(self.metrics)

    def create_custom_dimension(self, parent, custom_dimension):
        self.dims.append(custom_dimension.parameter_name)
        return custom_dimension

    def create_custom_metric(self, parent, custom_metric):
        self.metrics.append(custom_metric.parameter_name)
        return custom_metric

    def archive_custom_dimension(self, name):
        self.dims.remove(name.rsplit("/", 1)[1])

    def archive_custom_metric(self, name):
        self.metrics.remove(name.rsplit("/", 1)[1])


def _use_fake_admin(monkeypatch, **state):
    fake = _FakeAdminClient(**state)
    client = MagicMock(wraps=fake)
    monkeypatch.setattr(ga4_admin, "_get_admin_client", lambda write=False: client)
    monkeypatch.setattr(ga4_admin, "_proto_to_dict", lambda m: m)
    return fake, client


def test_key_event_writes_refresh_cached_list(monkeypatch):
    # The sequence run through the MCP connector on 2026-09-11: two deletes and
    # a create, after which the cached read still returned the original list.
    _, client = _use_fake_admin(
        monkeypatch, key_events=["purchase", "close_convert_lead", "qualify_lead"]
    )
    before = ["purchase", "close_convert_lead", "qualify_lead"]
    assert ga4_admin.list_key_events("123") == before
    assert ga4_admin.list_key_events("123") == before
    assert client.list_key_events.call_count == 1  # the cache is live

    ga4_admin.delete_key_event("properties/123/keyEvents/close_convert_lead")
    ga4_admin.delete_key_event("properties/123/keyEvents/qualify_lead")
    assert ga4_admin.list_key_events("123") == ["purchase"]

    ga4_admin.create_key_event("123", "sign_up")
    assert ga4_admin.list_key_events("123") == ["purchase", "sign_up"]


def test_create_key_event_limit_check_ignores_stale_cache(monkeypatch):
    fake, _ = _use_fake_admin(monkeypatch, key_events=[f"ke_{i}" for i in range(30)])
    ga4_admin.list_key_events("123")  # caches 30 key events
    fake.key_events.pop()  # deleted outside this process, e.g. in the GA4 UI

    ga4_admin.create_key_event("123", "sign_up")
    assert fake.key_events[-1] == "sign_up"


@pytest.mark.parametrize(
    "write, expected",
    [
        pytest.param(
            lambda: ga4_admin.create_custom_dimension("123", "plan", "Plan", "EVENT"),
            {"custom_dimensions": ["brand", "plan"], "custom_metrics": ["value"]},
            id="create_custom_dimension",
        ),
        pytest.param(
            lambda: ga4_admin.archive_custom_dimension("properties/123/customDimensions/brand"),
            {"custom_dimensions": [], "custom_metrics": ["value"]},
            id="archive_custom_dimension",
        ),
        pytest.param(
            lambda: ga4_admin.create_custom_metric("123", "margin", "Margin", "STANDARD"),
            {"custom_dimensions": ["brand"], "custom_metrics": ["value", "margin"]},
            id="create_custom_metric",
        ),
        pytest.param(
            lambda: ga4_admin.archive_custom_metric("properties/123/customMetrics/value"),
            {"custom_dimensions": ["brand"], "custom_metrics": []},
            id="archive_custom_metric",
        ),
    ],
)
def test_custom_def_writes_refresh_cached_list(monkeypatch, write, expected):
    _use_fake_admin(monkeypatch, dims=["brand"], metrics=["value"])
    ga4_admin.list_custom_defs("123")  # caches the pre-write state

    write()
    assert ga4_admin.list_custom_defs("123") == expected
