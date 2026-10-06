"""Bridge-side backend client: verified against a fake HTTP client, not a
live network call."""
import httpx
import pytest

from synker_bridge.api_client import ApiError, fetch_pending, report_sync_result
from synker_bridge.sync import SyncOutcome


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def get(self, url, *, headers):
        self.calls.append(("GET", url, None, headers))
        return self._response

    async def post(self, url, *, json, headers):
        self.calls.append(("POST", url, json, headers))
        return self._response


class _RaisingClient:
    """Stands in for httpx.AsyncClient when the backend is temporarily
    unreachable (connection refused, timeout, DNS failure) rather than
    reachable-but-erroring."""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def get(self, url, *, headers):
        raise self._exc

    async def post(self, url, *, json, headers):
        raise self._exc


@pytest.mark.asyncio
async def test_fetch_pending_returns_parsed_files():
    client = _FakeClient(_FakeResponse(200, [
        {"path": "a.md", "content": "A", "frontmatter": {}, "lastModified": None},
        {"path": "b.md", "content": "B", "frontmatter": {}, "lastModified": None},
    ]))

    files = await fetch_pending("https://api.example.com", "token123", http_client=client)

    assert [f.path for f in files] == ["a.md", "b.md"]
    method, url, _, headers = client.calls[0]
    assert method == "GET"
    assert url == "https://api.example.com/api/vault/pending-sync"
    assert headers["Authorization"] == "Bearer token123"


@pytest.mark.asyncio
async def test_fetch_pending_sends_updated_since_cursor_when_given():
    from urllib.parse import parse_qs, urlsplit

    client = _FakeClient(_FakeResponse(200, []))

    await fetch_pending("https://api.example.com", "token123",
                         updated_since="2026-01-01T00:00:00+00:00", http_client=client)

    _, url, _, _ = client.calls[0]
    query = urlsplit(url).query
    assert parse_qs(query)["updatedSince"][0] == "2026-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_fetch_pending_url_encodes_updated_since_plus_offset():
    """Regression test: a raw '+' in an ISO timestamp's UTC offset (e.g.
    '+00:00') is a reserved query-string character that decodes as a space
    server-side unless percent-encoded. This was only caught by a real
    round-trip against the live backend, not by _FakeClient — parse the
    query string the same way a real HTTP server would (urllib.parse.parse_qs)
    and confirm it comes back byte-for-byte identical to what was passed in."""
    from urllib.parse import parse_qs, urlsplit

    client = _FakeClient(_FakeResponse(200, []))
    original = "2026-09-13T20:01:27.040127+00:00"

    await fetch_pending("https://api.example.com", "token123",
                         updated_since=original, http_client=client)

    _, url, _, _ = client.calls[0]
    query = urlsplit(url).query
    assert parse_qs(query)["updatedSince"][0] == original


@pytest.mark.asyncio
async def test_fetch_pending_raises_on_401():
    client = _FakeClient(_FakeResponse(401))

    with pytest.raises(ApiError, match="Not authenticated"):
        await fetch_pending("https://api.example.com", "expired-token", http_client=client)


@pytest.mark.asyncio
async def test_report_sync_result_posts_expected_shape():
    client = _FakeClient(_FakeResponse(200, {"path": "a.md", "status": "written", "logged": True}))
    outcome = SyncOutcome(path="a.md", status="written", detail="ok")

    await report_sync_result("https://api.example.com", "token123", outcome, http_client=client)

    method, url, body, headers = client.calls[0]
    assert method == "POST"
    assert url == "https://api.example.com/api/vault/sync-result"
    assert body == {"path": "a.md", "status": "written", "detail": "ok"}
    assert headers["Authorization"] == "Bearer token123"


@pytest.mark.asyncio
async def test_report_sync_result_raises_on_failure():
    client = _FakeClient(_FakeResponse(500, text="internal error"))
    outcome = SyncOutcome(path="a.md", status="error", detail="disk full")

    with pytest.raises(ApiError, match="sync-result failed"):
        await report_sync_result("https://api.example.com", "token123", outcome, http_client=client)


@pytest.mark.asyncio
async def test_fetch_pending_raises_api_error_when_backend_unreachable():
    """Backend temporarily unavailable during sync must surface as a clean
    ApiError, not a raw httpx exception — the CLI's error handling only
    catches ApiError, and local sync state must not be touched on this path."""
    client = _RaisingClient(httpx.ConnectError("Connection refused"))

    with pytest.raises(ApiError, match="[Cc]ould not reach"):
        await fetch_pending("https://api.example.com", "token123", http_client=client)


@pytest.mark.asyncio
async def test_report_sync_result_raises_api_error_when_backend_unreachable():
    """A dropped connection while acknowledging a written file must not crash
    the bridge — the file is already safely on disk (see test_sync.py); only
    the acknowledgement failed, and that must be a clean, catchable error."""
    client = _RaisingClient(httpx.TimeoutException("timed out"))
    outcome = SyncOutcome(path="a.md", status="written", detail="ok")

    with pytest.raises(ApiError, match="[Cc]ould not reach"):
        await report_sync_result("https://api.example.com", "token123", outcome, http_client=client)
