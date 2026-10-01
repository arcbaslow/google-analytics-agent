import socket
import ssl
import urllib.request
from unittest.mock import Mock

import ga4_context as context
import pytest


def infos(address="93.184.215.14"):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_dns_rebinding_cannot_replace_validated_destination(monkeypatch):
    resolve = Mock(side_effect=[infos(), infos("127.0.0.1")])
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    sock = Mock()
    monkeypatch.setattr(socket, "socket", Mock(return_value=sock))
    assert context._public_connection(("example.com", 443), 12) is sock
    resolve.assert_called_once_with("example.com", 443, type=socket.SOCK_STREAM)
    sock.connect.assert_called_once_with(("93.184.215.14", 443))


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "fd00::1"])
def test_connect_rejects_private_rebinding_before_creating_socket(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos(address))
    factory = Mock()
    monkeypatch.setattr(socket, "socket", factory)
    with pytest.raises(context.UnsafeFetchTarget):
        context._public_connection(("public-name.example", 443), 12)
    factory.assert_not_called()


def test_mixed_dns_answer_rejected_and_failed_sockets_closed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos() + infos("10.0.0.1"))
    with pytest.raises(context.UnsafeFetchTarget):
        context._public_connection(("example.com", 443), 12)
    sock = Mock()
    sock.connect.side_effect = OSError("unavailable")
    monkeypatch.setattr(socket, "socket", Mock(return_value=sock))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos())
    with pytest.raises(OSError, match="unavailable"):
        context._public_connection(("example.com", 443), 12, ("0.0.0.0", 0))
    sock.close.assert_called_once()
    sock.bind.assert_called_once_with(("0.0.0.0", 0))


def test_tls_keeps_original_hostname_and_verification(monkeypatch):
    tls = ssl.create_default_context()
    wrap = Mock()
    monkeypatch.setattr(tls, "wrap_socket", wrap)
    dial = Mock(return_value=Mock())
    monkeypatch.setattr(context, "_public_connection", dial)
    connection = context._PublicHTTPSConnection("example.com", context=tls, timeout=12)
    connection.connect()
    assert tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED
    assert wrap.call_args.kwargs["server_hostname"] == "example.com"
    assert dial.call_args.args[0] == ("example.com", 443)


def test_http_uses_pinned_connector_and_handlers_preserve_host(monkeypatch):
    dial = Mock(return_value=Mock())
    monkeypatch.setattr(context, "_public_connection", dial)
    connection = context._PublicHTTPConnection("example.com", timeout=12)
    connection.connect()
    assert dial.call_args.args[0] == ("example.com", 80)
    req = urllib.request.Request("https://example.com/path")
    for handler, method, cls in [
        (context._PublicHTTPSHandler(), "https_open", context._PublicHTTPSConnection),
        (context._PublicHTTPHandler(), "http_open", context._PublicHTTPConnection),
    ]:
        monkeypatch.setattr(handler, "do_open", Mock(return_value="response"))
        assert getattr(handler, method)(req) == "response"
        assert handler.do_open.call_args.args == (cls, req)
    builder = Mock()
    monkeypatch.setattr(urllib.request, "build_opener", builder)
    context._open_url(req, timeout=12)
    proxy = next(h for h in builder.call_args.args if isinstance(h, urllib.request.ProxyHandler))
    assert proxy.proxies == {}


def test_dns_failure_empty_answer_and_deadline_fail_closed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", Mock(side_effect=socket.gaierror("missing")))
    with pytest.raises(socket.gaierror):
        context._public_connection(("example.com", 443), 12)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(OSError, match="no public address"):
        context._public_connection(("example.com", 443), 12)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos())
    monkeypatch.setattr(context.time, "monotonic", Mock(side_effect=[0, 13]))
    with pytest.raises(TimeoutError):
        context._public_connection(("example.com", 443), 12)


def test_url_credentials_are_rejected():
    with pytest.raises(context.UnsafeFetchTarget):
        context.assert_fetchable("https://username:password@example.com/")
