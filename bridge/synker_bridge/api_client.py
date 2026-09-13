"""Bridge-side client for the two Synker backend endpoints added for it:
GET /api/vault/pending-sync and POST /api/vault/sync-result
(backend/app/api/routes/vault.py). Same JWT auth as the web app — no new
auth path on the backend side.
"""
from __future__ import annotations

from typing import Protocol

import httpx

from synker_bridge.sync import PendingFile, SyncOutcome


class ApiError(Exception):
    """Raised when a backend call fails or returns an unexpected shape."""


class HttpClient(Protocol):
    async def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response: ...
    async def post(
        self, url: str, *, json: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response: ...
    async def aclose(self) -> None: ...


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def fetch_pending(
    api_base: str,
    access_token: str,
    updated_since: str | None = None,
    http_client: HttpClient | None = None,
) -> list[PendingFile]:
    owns_client = http_client is None
    client: HttpClient = http_client or httpx.AsyncClient(timeout=30.0)
    url = f"{api_base}/api/vault/pending-sync"
    if updated_since:
        url += f"?updatedSince={updated_since}"
    try:
        try:
            response = await client.get(url, headers=_auth_headers(access_token))
        except httpx.HTTPError as exc:
            raise ApiError(f"Could not reach the backend: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 401:
        raise ApiError("Not authenticated (401) — the stored session may have expired.")
    if response.status_code != 200:
        raise ApiError(f"pending-sync failed ({response.status_code}): {response.text[:200]}")

    return [
        PendingFile(path=item["path"], content=item["content"],
                    last_modified=item.get("lastModified"))
        for item in response.json()
    ]


async def report_sync_result(
    api_base: str,
    access_token: str,
    outcome: SyncOutcome,
    http_client: HttpClient | None = None,
) -> None:
    owns_client = http_client is None
    client: HttpClient = http_client or httpx.AsyncClient(timeout=30.0)
    try:
        try:
            response = await client.post(
                f"{api_base}/api/vault/sync-result",
                json={"path": outcome.path, "status": outcome.status, "detail": outcome.detail},
                headers=_auth_headers(access_token),
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"Could not reach the backend: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code != 200:
        raise ApiError(f"sync-result failed ({response.status_code}): {response.text[:200]}")
