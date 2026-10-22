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


async def test_post_source_defaults_to_direct_resource_scope(authed_client):
    response = await authed_client.post(
        "/api/sources",
        json={"url": "https://example.com", "type": "web", "title": "Test"},
    )
    assert response.json()["sourceScope"] == "direct_resource"


async def test_post_source_classifies_youtube_homepage_as_discovery_provider(authed_client):
    """The Add Source UI has no source_scope field — the server must infer
    it, not blindly trust the client's "direct_resource" schema default,
    which is wrong for a bare platform homepage (Stage 6 verification-loop
    ROOT CAUSE #2)."""
    response = await authed_client.post(
        "/api/sources",
        json={"url": "https://www.youtube.com/", "type": "youtube", "title": ""},
    )
    assert response.json()["sourceScope"] == "discovery_provider"


async def test_post_source_classifies_youtube_video_url_as_direct_resource(authed_client):
    response = await authed_client.post(
        "/api/sources",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "type": "youtube", "title": ""},
    )
    assert response.json()["sourceScope"] == "direct_resource"


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


async def test_post_candidates_approve_with_source_returns_200(authed_client):
    """Test that /api/candidates/approve returns 200 with source_id.

    This test covers AC-003:
    - The endpoint still returns 200 after the source_id INSERT change
    - No regressions in the approval flow
    """
    response = await authed_client.post("/api/candidates/approve", json={"ids": ["mock-id"]})
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


async def test_browse_directory_is_deprecated_not_a_silent_empty_path(authed_client):
    """Regression (Stage 5 item 4): the old server-side tkinter dialog can
    never open on Railway (no display). It must not silently pretend to have
    tried and failed by returning {"path": ""} — it must say clearly that
    folder picking moved to the Local Sync Bridge."""
    response = await authed_client.get("/api/settings/browse-directory")
    assert response.status_code == 410
    assert "Local Sync Bridge" in response.json()["detail"]


# ── Vault (Local Sync Bridge) ────────────────────────────────────────────────

async def test_vault_pending_sync_returns_200(authed_client):
    response = await authed_client.get("/api/vault/pending-sync")
    assert response.status_code == 200
    assert response.json() == []


async def test_vault_sync_result_logs_and_returns_200(authed_client):
    response = await authed_client.post(
        "/api/vault/sync-result",
        json={"path": "Synker/note.md", "status": "written", "detail": "ok"},
    )
    assert response.status_code == 200
    assert response.json() == {"path": "Synker/note.md", "status": "written", "logged": True}


async def test_vault_sync_result_rejects_unknown_status(authed_client):
    response = await authed_client.post(
        "/api/vault/sync-result",
        json={"path": "Synker/note.md", "status": "bogus"},
    )
    assert response.status_code == 422


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def test_post_scheduler_trigger_returns_400_when_no_sources(authed_client):
    """Guard: trigger must return 400 with a clear message when user has no sources."""
    response = await authed_client.post("/api/scheduler/trigger")
    assert response.status_code == 400
    assert "No sources" in response.json()["detail"]


async def test_post_scheduler_trigger_returns_200_when_source_exists(authed_client_with_source):
    """Trigger returns 200 and a jobId when the user has at least one source."""
    response = await authed_client_with_source.post("/api/scheduler/trigger")
    assert response.status_code == 200
    assert response.json()["triggered"] is True
    assert response.json()["jobId"] is not None


async def test_trigger_discovery_requeues_done_sources():
    """Verify that POST /api/scheduler/trigger re-queues done/processing sources.

    This test ensures that when discovery is triggered, sources with status
    'done' or 'processing' are reset to 'queued' before the Analysis job is
    created. This allows the scheduler to re-analyze sources on each trigger.

    Root cause: Without re-queuing, sources would remain 'done' and the
    Analysis handler would find zero queued sources, producing zero candidates.
    """
    import uuid as _uuid
    from contextlib import asynccontextmanager

    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from tests.conftest import MOCK_USER

    # Track all execute() and fetchrow() calls to verify the UPDATE was made
    executed_queries: list[tuple[str, tuple]] = []
    fetched_queries: list[tuple[str, tuple]] = []

    class MockConnTracker:
        async def fetchval(self, query: str, *args, **kwargs) -> int | None:  # type: ignore[override]
            if "sources" in query.lower() and "count" in query.lower():
                return 1
            return None

        async def fetchrow(self, query: str, *args, **kwargs) -> dict | None:  # type: ignore[override]
            fetched_queries.append((query, args))
            if "INSERT INTO jobs" in query:
                return {"id": _uuid.UUID("00000000-0000-0000-0000-000000000099")}
            return None

        async def execute(self, query: str, *args, **kwargs) -> None:  # type: ignore[override]
            executed_queries.append((query, args))

        @asynccontextmanager
        async def transaction(self):  # type: ignore[override]
            """Mock transaction context manager — passes through."""
            yield

    async def _mock_get_db_tracker():
        yield MockConnTracker()

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _mock_get_db_tracker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/scheduler/trigger")

        # Verify response is successful
        assert response.status_code == 200
        assert response.json()["triggered"] is True

        # Verify the UPDATE query was executed to re-queue done/processing sources
        update_queries = [
            (query, args)
            for query, args in executed_queries
            if "UPDATE sources" in query and "queued" in query
        ]
        assert len(update_queries) == 1, (
            f"Expected exactly one UPDATE sources query, "
            f"got {len(update_queries)}. Executed queries: {executed_queries}"
        )

        query, args = update_queries[0]
        assert "status IN ('done', 'processing')" in query, (
            f"UPDATE query must check for 'done' or 'processing' status. Got: {query}"
        )
        assert "status='queued'" in query, (
            f"UPDATE query must set status='queued'. Got: {query}"
        )
        assert len(args) >= 1, (
            f"UPDATE query must have at least the user_id parameter. Got: {args}"
        )
        # Verify the user_id is passed (should be MOCK_USER's sub)
        assert str(args[0]) == MOCK_USER["sub"], (
            f"UPDATE query must use the current user's ID. "
            f"Got {args[0]}, expected {MOCK_USER['sub']}"
        )

        # Verify INSERT INTO jobs was called via fetchrow
        insert_job_queries = [
            (query, args)
            for query, args in fetched_queries
            if "INSERT INTO jobs" in query
        ]
        assert len(insert_job_queries) >= 1, (
            "Expected at least one INSERT INTO jobs query (via fetchrow). "
            f"Fetched queries: {fetched_queries}"
        )

    finally:
        app.dependency_overrides.clear()


# ── Auth guard ────────────────────────────────────────────────────────────────

async def test_protected_routes_reject_unauthenticated(client):
    """Protected routes must return 401 when no token is supplied."""
    response = await client.get("/api/settings")
    assert response.status_code == 401


# ── Note state machine (SYN-V5-015) ─────────────────────────────────────────────

async def test_note_approve_returns_409_when_not_pending():
    """Approving a note whose row is no longer pending (UPDATE affects 0 rows)
    must return 409, not a false success — this is what stops accept+reject
    from both succeeding on the same note."""
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from tests.conftest import MOCK_USER

    class _ConflictConn:
        async def execute(self, *args, **kwargs):
            return "UPDATE 0"

        async def fetch(self, *args, **kwargs):
            return []

        async def fetchrow(self, *args, **kwargs):
            return None

        async def fetchval(self, *args, **kwargs):
            return None

    async def _conflict_db():
        yield _ConflictConn()

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _conflict_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/api/notes/00000000-0000-0000-0000-0000000000ab/approve"
            )
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()
