"""
Tests for all 17+ stub API routes.

Guarantees:
- Every GET route returns HTTP 200
- Every POST/PATCH mutation route returns HTTP 200
- DELETE routes return HTTP 204
- /api/vault/file accepts a `path` query param
- Protected routes return 401 when no token is supplied
"""
import pytest


GET_ROUTES = [
    "/api/dashboard/stats",
    "/api/dashboard/activity",
    "/api/topics",
    "/api/sources",
    "/api/candidates",
    "/api/jobs",
    "/api/notes",
    "/api/vault/tree",
    "/api/settings",
]


@pytest.mark.parametrize("path", GET_ROUTES)
async def test_get_routes_return_200(authed_client, path):
    response = await authed_client.get(path)
    assert response.status_code == 200


async def test_vault_file_returns_200(authed_client):
    response = await authed_client.get("/api/vault/file?path=test.md")
    assert response.status_code == 200


# ── Topics ────────────────────────────────────────────────────────────────────

async def test_post_topic_returns_200(authed_client):
    response = await authed_client.post("/api/topics", json={"label": "Test Topic"})
    assert response.status_code == 200


async def test_delete_topic_returns_204(authed_client):
    response = await authed_client.delete("/api/topics/mock-id")
    assert response.status_code == 204


# ── Sources ───────────────────────────────────────────────────────────────────

async def test_post_source_returns_200(authed_client):
    response = await authed_client.post(
        "/api/sources",
        json={"url": "https://example.com", "type": "web", "title": "Test"},
    )
    assert response.status_code == 200


async def test_delete_source_returns_204(authed_client):
    response = await authed_client.delete("/api/sources/mock-id")
    assert response.status_code == 204


# ── Candidates ────────────────────────────────────────────────────────────────

async def test_post_candidates_approve_returns_200(authed_client):
    response = await authed_client.post("/api/candidates/approve", json={"ids": ["mock-id"]})
    assert response.status_code == 200


async def test_post_candidates_reject_returns_200(authed_client):
    response = await authed_client.post("/api/candidates/reject", json={"ids": ["mock-id"]})
    assert response.status_code == 200


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def test_post_job_retry_returns_200(authed_client):
    response = await authed_client.post("/api/jobs/mock-id/retry")
    assert response.status_code == 200


# ── Notes ─────────────────────────────────────────────────────────────────────

async def test_post_note_approve_returns_200(authed_client):
    response = await authed_client.post("/api/notes/mock-id/approve")
    assert response.status_code == 200


async def test_post_note_reject_returns_200(authed_client):
    response = await authed_client.post("/api/notes/mock-id/reject")
    assert response.status_code == 200


# ── Settings ──────────────────────────────────────────────────────────────────

async def test_patch_settings_section_returns_200(authed_client):
    response = await authed_client.patch("/api/settings/vault", json={"path": "/my-vault"})
    assert response.status_code == 200


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def test_post_scheduler_trigger_returns_200(authed_client):
    response = await authed_client.post("/api/scheduler/trigger")
    assert response.status_code == 200


# ── Auth guard ────────────────────────────────────────────────────────────────

async def test_protected_routes_reject_unauthenticated(client):
    """Protected routes must return 401 when no token is supplied."""
    response = await client.get("/api/settings")
    assert response.status_code == 401
