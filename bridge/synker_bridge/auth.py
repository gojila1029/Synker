"""Supabase Auth login for the bridge — reuses the same Supabase project and
JWT the web app already uses. No new auth system: the resulting access_token
is sent as a normal `Authorization: Bearer` header to the existing FastAPI
backend, validated by the unmodified backend/app/core/security.py.

The request shapes below match Supabase's documented Auth REST endpoints
(password grant and refresh-token grant). Verified against a fake HTTP client
in this package's tests; a live-Staging run is tracked separately (Stage 6
Section 6) and requires a disposable test account.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx


class AuthError(Exception):
    """Raised when Supabase login/refresh fails."""


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    expires_at: float | None = None  # unix timestamp; None if Supabase didn't say


class HttpPoster(Protocol):
    async def post(
        self, url: str, *, json: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response: ...

    async def aclose(self) -> None: ...


def _session_from_token_response(data: dict[str, object]) -> Session:
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise AuthError("Token response missing access_token/refresh_token")

    expires_at_raw = data.get("expires_at")
    expires_in_raw = data.get("expires_in")
    expires_at: float | None = None
    if isinstance(expires_at_raw, (int, float)):
        expires_at = float(expires_at_raw)
    elif isinstance(expires_in_raw, (int, float)):
        expires_at = time.time() + float(expires_in_raw)

    return Session(access_token=access_token, refresh_token=refresh_token, expires_at=expires_at)


async def _post_token_endpoint(
    supabase_url: str,
    anon_key: str,
    grant_type: str,
    body: dict[str, str],
    http_client: HttpPoster | None,
) -> Session:
    owns_client = http_client is None
    client: HttpPoster = http_client or httpx.AsyncClient(timeout=15.0)

    try:
        try:
            response = await client.post(
                f"{supabase_url}/auth/v1/token?grant_type={grant_type}",
                json=body,
                headers={"apikey": anon_key, "Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise AuthError(f"Could not reach the backend: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code != 200:
        raise AuthError(f"Request failed ({response.status_code}): {response.text[:200]}")

    return _session_from_token_response(response.json())


async def login(
    supabase_url: str,
    anon_key: str,
    email: str,
    password: str,
    http_client: HttpPoster | None = None,
) -> Session:
    """POST to Supabase's password-grant token endpoint. Accepts an injected
    HTTP client so this is testable without a live network call."""
    return await _post_token_endpoint(
        supabase_url, anon_key, "password", {"email": email, "password": password}, http_client
    )


async def refresh(
    supabase_url: str,
    anon_key: str,
    refresh_token: str,
    http_client: HttpPoster | None = None,
) -> Session:
    """POST to Supabase's refresh-token grant endpoint to get a new access
    token without prompting the user for a password again."""
    return await _post_token_endpoint(
        supabase_url, anon_key, "refresh_token", {"refresh_token": refresh_token}, http_client
    )
