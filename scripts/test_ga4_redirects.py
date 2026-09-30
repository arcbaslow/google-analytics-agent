import io
import urllib.request
from email.message import Message
from unittest.mock import MagicMock

import ga4_context
import pytest


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/",
        "file:///private",
        "ftp://example.com/file",
        "http://[fd00::1]/",
    ],
)
def test_redirect_is_rejected_before_next_request(monkeypatch, target):
    monkeypatch.setattr(ga4_context, "_resolves_to_private", lambda host: host != "example.com")
    handler = ga4_context._PublicRedirectHandler()
    handler.parent = MagicMock()
    headers = Message()
    headers["Location"] = target
    with pytest.raises((ga4_context.UnsafeFetchTarget, ga4_context.urllib.error.HTTPError)):
        handler.http_error_302(
            urllib.request.Request("https://example.com/"), io.BytesIO(), 302, "Found", headers
        )
    handler.parent.open.assert_not_called()


def test_public_redirect_and_next_private_hop_are_checked(monkeypatch):
    checked = []

    def validate(url):
        checked.append(url)
        if "internal" in url:
            raise ga4_context.UnsafeFetchTarget("blocked")

    monkeypatch.setattr(ga4_context, "assert_fetchable", validate)
    handler = ga4_context._PublicRedirectHandler()
    first = handler.redirect_request(
        urllib.request.Request("https://example.com/"),
        None,
        302,
        "Found",
        {},
        "https://public.example/next",
    )
    assert first.full_url == "https://public.example/next"
    with pytest.raises(ga4_context.UnsafeFetchTarget):
        handler.redirect_request(first, None, 302, "Found", {}, "http://internal/")
    assert checked == ["https://public.example/next", "http://internal/"]


def test_fetch_uses_guarded_opener_and_returns_redirect_error(monkeypatch):
    monkeypatch.setattr(ga4_context, "assert_fetchable", lambda _: None)
    opener = MagicMock()
    opener.open.side_effect = ga4_context.UnsafeFetchTarget("private redirect")
    builder = MagicMock(return_value=opener)
    monkeypatch.setattr(ga4_context.urllib.request, "build_opener", builder)
    status, headers, body = ga4_context._fetch("https://example.com/")
    assert isinstance(builder.call_args.args[0], ga4_context._PublicRedirectHandler)
    assert status == -1 and headers == {}
    assert "private redirect" in body


def test_malformed_url_is_a_fetch_failure():
    assert ga4_context._fetch("http://[broken")[0] == -1
