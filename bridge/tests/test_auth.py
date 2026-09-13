"""Auth handshake: request shape is verified; no live Supabase call is made.

The injected fake client stands in for httpx.AsyncClient so this test proves
the request shape and response handling without any real network access.
"""
import time

import httpx
import pytest

from synker_bridge.auth import AuthError, login, refresh


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.calls: list[tuple[str, dict, dict]] = []

    async def post(self, url, *, json, headers):
        self.calls.append((url, json, headers))
        return self._response


class _RaisingClient:
    """Stands in for httpx.AsyncClient when the network call itself fails
    (backend/Supabase unreachable, DNS failure, timeout) — as opposed to a
    reachable server returning an error status code."""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def post(self, url, *, json, headers):
        raise self._exc


@pytest.mark.asyncio
async def test_login_posts_password_grant_with_correct_shape():
    client = _FakeClient(_FakeResponse(200, {"access_token": "at", "refresh_token": "rt"}))

    session = await login(
        "https://example.supabase.co", "anon-key", "user@example.com", "pw",
        http_client=client,
    )

    assert session.access_token == "at"
    assert session.refresh_token == "rt"
    url, body, headers = client.calls[0]
    assert url == "https://example.supabase.co/auth/v1/token?grant_type=password"
    assert body == {"email": "user@example.com", "password": "pw"}
    assert headers["apikey"] == "anon-key"


@pytest.mark.asyncio
async def test_login_raises_auth_error_on_non_200():
    client = _FakeClient(_FakeResponse(400, {"error": "invalid_grant"}))

    with pytest.raises(AuthError, match="Request failed"):
        await login("https://example.supabase.co", "anon-key", "user@example.com", "wrong",
                     http_client=client)


@pytest.mark.asyncio
async def test_login_raises_auth_error_on_missing_tokens():
    client = _FakeClient(_FakeResponse(200, {"unexpected": "shape"}))

    with pytest.raises(AuthError, match="missing access_token"):
        await login("https://example.supabase.co", "anon-key", "user@example.com", "pw",
                     http_client=client)


@pytest.mark.asyncio
async def test_login_parses_expires_in_into_expires_at():
    client = _FakeClient(_FakeResponse(
        200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
    ))
    before = time.time()

    session = await login("https://example.supabase.co", "anon-key", "u@example.com", "pw",
                           http_client=client)

    assert session.expires_at is not None
    assert before + 3600 <= session.expires_at <= before + 3601


@pytest.mark.asyncio
async def test_login_prefers_explicit_expires_at():
    client = _FakeClient(_FakeResponse(
        200, {"access_token": "at", "refresh_token": "rt", "expires_at": 12345, "expires_in": 3600}
    ))

    session = await login("https://example.supabase.co", "anon-key", "u@example.com", "pw",
                           http_client=client)

    assert session.expires_at == 12345


@pytest.mark.asyncio
async def test_refresh_posts_refresh_token_grant_with_correct_shape():
    client = _FakeClient(_FakeResponse(200, {"access_token": "at2", "refresh_token": "rt2"}))

    session = await refresh("https://example.supabase.co", "anon-key", "old-refresh-token",
                             http_client=client)

    assert session.access_token == "at2"
    url, body, _ = client.calls[0]
    assert url == "https://example.supabase.co/auth/v1/token?grant_type=refresh_token"
    assert body == {"refresh_token": "old-refresh-token"}


@pytest.mark.asyncio
async def test_refresh_raises_auth_error_on_revoked_token():
    client = _FakeClient(_FakeResponse(401, {"error": "invalid_grant"}))

    with pytest.raises(AuthError, match="Request failed"):
        await refresh("https://example.supabase.co", "anon-key", "revoked-token",
                       http_client=client)


@pytest.mark.asyncio
async def test_login_raises_auth_error_when_backend_unreachable():
    """A transient network failure (Supabase/backend temporarily unavailable)
    must surface as a clean AuthError, not an unhandled httpx exception that
    would crash the CLI instead of returning a safe non-zero exit."""
    client = _RaisingClient(httpx.ConnectError("Connection refused"))

    with pytest.raises(AuthError, match="[Cc]ould not reach"):
        await login("https://example.supabase.co", "anon-key", "user@example.com", "pw",
                     http_client=client)


@pytest.mark.asyncio
async def test_refresh_raises_auth_error_when_backend_unreachable():
    """Same guarantee for token refresh — a network hiccup mid-sync must not
    crash the bridge with a raw exception."""
    client = _RaisingClient(httpx.TimeoutException("timed out"))

    with pytest.raises(AuthError, match="[Cc]ould not reach"):
        await refresh("https://example.supabase.co", "anon-key", "old-refresh-token",
                       http_client=client)
