"""Bounded read execution. Never pass a write method to these helpers."""

from __future__ import annotations

import functools
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar

from ga4_utils import scrub_pii
from google.api_core import exceptions as api_errors
from google.auth.exceptions import RefreshError


class ReadBudgetExceeded(RuntimeError):
    pass


class ReadBudget:
    def __init__(self, max_requests=100):
        if type(max_requests) is not int or not 1 <= max_requests <= 1000:
            raise ValueError("max_requests must be between 1 and 1000")
        self.remaining = max_requests
        self.lock = threading.Lock()

    def consume(self):
        with self.lock:
            if self.remaining <= 0:
                raise ReadBudgetExceeded("read request budget exhausted")
            self.remaining -= 1


_budget: ContextVar[ReadBudget | None] = ContextVar("ga4_read_budget", default=None)


@contextmanager
def read_budget(max_requests=100):
    """Nested operations share the outer budget; audit workers share its lock."""
    token = None
    if _budget.get() is None:
        token = _budget.set(ReadBudget(max_requests))
    try:
        yield _budget.get()
    finally:
        if token is not None:
            _budget.reset(token)


def read_operation(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with read_budget():
            return fn(*args, **kwargs)

    return wrapped


def error_result(exc):
    """Stable error categories across CLI, MCP and partially failed Admin reads."""
    from ga4_auth import AuthRequiredError

    if isinstance(exc, (AuthRequiredError, RefreshError, api_errors.Unauthenticated)):
        category = "auth_required"
    elif isinstance(exc, api_errors.PermissionDenied):
        category = "permission_denied"
    elif isinstance(exc, api_errors.ResourceExhausted):
        category = "quota_exhausted"
    elif isinstance(exc, ReadBudgetExceeded):
        category = "read_budget_exhausted"
    elif isinstance(
        exc,
        (
            api_errors.ServiceUnavailable,
            api_errors.DeadlineExceeded,
            api_errors.InternalServerError,
        ),
    ):
        category = "transient_read_failure"
    elif isinstance(exc, (api_errors.InvalidArgument, ValueError)):
        category = "invalid_request"
    elif isinstance(exc, api_errors.NotFound):
        category = "not_found"
    else:
        category = "unexpected_error"
    return scrub_pii(
        {
            "error": category,
            "type": type(exc).__name__,
            "message": str(exc),
            "retryable": category == "transient_read_failure",
        }
    )


@read_operation
def read_call(method, *args, **kwargs):
    """Disable GAPIC retries; at most three bounded attempts on transient reads."""
    method_name = getattr(method, "__name__", "")
    if method_name and not method_name.startswith(("get_", "list_", "run_", "check_", "search_")):
        raise ValueError("read_call accepts only read methods")
    kwargs.update(retry=None, timeout=30)
    for attempt in range(3):
        budget = _budget.get()
        assert budget is not None
        budget.consume()
        try:
            return method(*args, **kwargs)
        except (
            api_errors.ServiceUnavailable,
            api_errors.DeadlineExceeded,
            api_errors.InternalServerError,
        ):
            if attempt == 2:
                raise
            time.sleep(0.25 * (2**attempt))


def read_list(method, **kwargs):
    """Consume SDK pages within the same request budget, returning no partial list.

    The initial call gets bounded transient retries. Later pager fetches inherit
    retry=None and timeout=30 and are not retried. The pager type specifies the
    repeated result field in its iterator; each page is itself iterable only via
    that field, obtained from the response protobuf descriptor.
    """
    with read_budget():
        pager = read_call(method, **kwargs)
        if not type(pager).__module__.startswith("google.analytics"):
            return list(pager)
        pages = iter(pager.pages)
        result = []
        for index in range(100):
            if index:
                budget = _budget.get()
                assert budget is not None
                budget.consume()
            page = next(pages)
            for field in page._pb.DESCRIPTOR.fields:
                # Use the descriptor label supported by both protobuf versions.
                if field.message_type is not None and field.name != "next_page_token":
                    value = getattr(page, field.name)
                    if hasattr(value, "__iter__"):
                        result.extend(value)
            if not page.next_page_token:
                return result
        raise ReadBudgetExceeded("Admin page limit exhausted")
