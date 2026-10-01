"""Transport limits use mocked methods, actual exceptions and SDK pagers."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from unittest.mock import Mock

import ga4_transport as transport
import pytest
from google.analytics.admin_v1beta.services.analytics_admin_service.pagers import ListKeyEventsPager
from google.analytics.admin_v1beta.types import ListKeyEventsRequest, ListKeyEventsResponse
from google.api_core import exceptions as errors


def test_transient_reads_have_three_attempts_and_no_gapic_retry(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(transport.time, "sleep", sleep)
    method = Mock(side_effect=errors.ServiceUnavailable("temporary"))
    with pytest.raises(errors.ServiceUnavailable), transport.read_budget(5) as budget:
        transport.read_call(method, name="properties/123")
    assert method.call_count == 3 and budget.remaining == 2
    assert sleep.call_count == 2
    assert method.call_args.kwargs == {"name": "properties/123", "retry": None, "timeout": 30}


@pytest.mark.parametrize(
    "error,category",
    [
        (errors.ResourceExhausted, "quota_exhausted"),
        (errors.PermissionDenied, "permission_denied"),
        (errors.Unauthenticated, "auth_required"),
        (errors.NotFound, "not_found"),
        (errors.InvalidArgument, "invalid_request"),
        (RuntimeError, "unexpected_error"),
    ],
)
def test_permanent_errors_are_not_retried_and_are_scrubbed(error, category):
    method = Mock(side_effect=error("person@example.com"))
    with pytest.raises(error) as exc:
        transport.read_call(method)
    out = transport.error_result(exc.value)
    assert out["error"] == category and "person@example.com" not in str(out)
    method.assert_called_once()


def test_budget_prevents_an_extra_rpc_and_is_shared_by_workers():
    method = Mock(return_value=1)
    with transport.read_budget(1), ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(copy_context().run, transport.read_call, method).result() == 1
        with pytest.raises(transport.ReadBudgetExceeded):
            transport.read_call(method)
    method.assert_called_once()
    assert (
        transport.error_result(transport.ReadBudgetExceeded())["error"] == "read_budget_exhausted"
    )


def test_pager_fetches_are_bounded():
    second = Mock(return_value=ListKeyEventsResponse(key_events=[{"event_name": "b"}]))

    def list_key_events(**kwargs):
        return ListKeyEventsPager(
            method=second,
            request=ListKeyEventsRequest(parent="properties/123"),
            response=ListKeyEventsResponse(
                key_events=[{"event_name": "a"}], next_page_token="next"
            ),
            retry=kwargs["retry"],
            timeout=kwargs["timeout"],
        )

    with transport.read_budget(1), pytest.raises(transport.ReadBudgetExceeded):
        transport.read_list(list_key_events)
    second.assert_not_called()
    with transport.read_budget(2):
        out = transport.read_list(list_key_events)
    assert [event.event_name for event in out] == ["a", "b"]
    assert second.call_args.kwargs["retry"] is None


def test_write_method_rejected_before_execution():
    def create_key_event(**kwargs):
        raise AssertionError("write executed")

    with pytest.raises(ValueError, match="read methods"):
        transport.read_call(create_key_event)


def test_invalid_budget_rejected():
    with pytest.raises(ValueError):
        transport.ReadBudget(0)
