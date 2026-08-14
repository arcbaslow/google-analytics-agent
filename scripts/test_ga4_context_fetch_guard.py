"""The context extractor follows URLs the audited site controls.

`analyze_website` reads the site's own robots.txt and follows whatever it
names in `Sitemap:`. That value is attacker-controlled input, and the
response gets written into the saved property context, which is read back
into model context on the next audit.

These lock the two guards that matter: scheme pinning (urllib's default
opener also handles file:// and ftp://) and rejecting hosts that resolve to
non-public addresses (169.254.169.254 is the cloud metadata endpoint on
essentially every VPS provider).
"""

import ga4_context
import pytest


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://[fd00::1]/",
        "http://127.0.0.1:8080/admin",
        "http://localhost/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
    ],
)
def test_rejects_non_public_hosts(url):
    with pytest.raises(ga4_context.UnsafeFetchTarget):
        ga4_context.assert_fetchable(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://C:/Windows/win.ini",
        "ftp://example.com/secrets.txt",
        "gopher://example.com/",
        "data:text/plain,hello",
    ],
)
def test_rejects_non_http_schemes(url):
    with pytest.raises(ga4_context.UnsafeFetchTarget):
        ga4_context.assert_fetchable(url)


def test_rejects_url_with_no_host():
    with pytest.raises(ga4_context.UnsafeFetchTarget):
        ga4_context.assert_fetchable("http:///nohost")


def test_allows_ordinary_public_url(monkeypatch):
    monkeypatch.setattr(ga4_context, "_resolves_to_private", lambda host: False)
    ga4_context.assert_fetchable("https://example.com/sitemap.xml")
    ga4_context.assert_fetchable("http://example.com/robots.txt")


def test_fetch_returns_error_tuple_instead_of_raising(monkeypatch):
    """_fetch promises never to raise; the guard must respect that."""
    called = []
    monkeypatch.setattr(ga4_context.urllib.request, "urlopen", lambda *a, **k: called.append(1))
    status, headers, body = ga4_context._fetch("http://169.254.169.254/latest/meta-data/")
    assert status == -1
    assert headers == {}
    assert "refusing to fetch" in body
    assert not called, "urlopen must not be reached for a blocked target"


def test_sitemap_from_robots_cannot_reach_metadata(monkeypatch):
    """End to end: a hostile robots.txt must not drive a metadata fetch."""
    robots = "User-agent: *\nSitemap: http://169.254.169.254/latest/meta-data/\n"
    parsed = ga4_context._parse_robots(robots)
    assert parsed["sitemaps"] == ["http://169.254.169.254/latest/meta-data/"]

    monkeypatch.setattr(
        ga4_context.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("urlopen reached for a link-local address"),
    )
    assert ga4_context._fetch_safely(parsed["sitemaps"][0]) is None


def test_unresolvable_host_is_not_treated_as_private():
    """A DNS failure should fall through to a normal fetch failure."""
    assert ga4_context._resolves_to_private("no-such-host.invalid") is False
