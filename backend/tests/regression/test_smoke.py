"""Regression smoke suite — fast critical-path verification.

Run just this suite:
    cd backend && uv run pytest tests/regression/ -v -m smoke

Each test references an Acceptance Criterion (AC-NNN) from
verification/test-manifest.json. Hermetic: no real DB or network needed.
"""
import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Shared fakes ──────────────────────────────────────────────────────────────

class _FakeConn:
    def __init__(self, fetchrow_result=None, fetch_result=None, fetchval_result=None):
        self._fetchrow = fetchrow_result
        self._fetch = fetch_result if fetch_result is not None else []
        self._fetchval = fetchval_result
        self.executed: list[tuple] = []
        self.fetchval_calls: list[tuple] = []

    async def fetch(self, sql, *args):
        return self._fetch

    async def fetchrow(self, sql, *args):
        return self._fetchrow

    async def fetchval(self, sql, *args):
        self.fetchval_calls.append((sql, args))
        return self._fetchval

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *exc):
                return False

        return _Ctx()


async def _noop_progress(pct: int) -> None:
    pass


# ── AC-001: Health endpoint ───────────────────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_health_ok(client):
    """AC-001: /health returns {status:ok, db:ok} when DB responds."""

    class _MockConn:
        async def fetchval(self, *a, **kw):
            return 1

    class _MockPool:
        @asynccontextmanager
        async def acquire(self):
            yield _MockConn()

    async def _healthy_pool():
        return _MockPool()

    with patch("app.api.routes.health.get_pool", new=_healthy_pool):
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["db"] == "ok"


# ── AC-002: Health degrades on DB failure ────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_health_degraded_when_db_down(client):
    """AC-002: /health returns 503 + db:unreachable when pool raises."""

    async def _failing_pool():
        raise Exception("DB unavailable")

    with patch("app.api.routes.health.get_pool", new=_failing_pool):
        resp = await client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["db"] == "unreachable"


# ── AC-003: Protected routes enforce auth ────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_protected_routes_require_auth(client):
    """AC-003: GET protected endpoints return 401 with no token."""
    for path in ["/api/settings", "/api/topics", "/api/sources", "/api/notes"]:
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} should require auth"


# ── AC-004/005: Source scope classification ───────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
def test_smoke_youtube_video_is_direct_resource():
    """AC-004: watch?v= URL with a valid 11-char video ID is classified
    as direct_resource."""
    from app.adapters.classify import classify_source_scope

    result = classify_source_scope("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result == "direct_resource"


@pytest.mark.smoke
@pytest.mark.regression
def test_smoke_youtube_homepage_is_discovery_provider():
    """AC-005: bare YouTube homepage classified as discovery_provider."""
    from app.adapters.classify import classify_source_scope
    assert classify_source_scope("youtube", "https://www.youtube.com/") == "discovery_provider"
    assert classify_source_scope("youtube", "https://www.youtube.com") == "discovery_provider"


# ── AC-006: Evidence persisted on successful extraction ───────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_successful_extraction_persists_evidence(monkeypatch):
    """AC-006: _analysis_handler writes source_extractions row so Note Gen can find it."""
    from app.adapters.base import ExtractedContent
    from app.worker import handlers

    async def _fake_extract(source_type, url):
        return ExtractedContent(text="Full transcript.", title="Title", word_count=2)

    monkeypatch.setattr(handlers, "adapter_extract", _fake_extract)

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    source_id = uuid.UUID("00000000-0000-0000-0000-0000000000dd")
    conn = _FakeConn(
        fetch_result=[{"id": source_id, "type": "youtube",
                       "url": "https://www.youtube.com/watch?v=abc12345678",
                       "title": "", "source_scope": "direct_resource"}],
        fetchval_result=None,
    )
    await handlers._analysis_handler({"user_id": user_id}, _noop_progress, _FakePool(conn))

    evidence = [sql for sql, _ in conn.executed if "INSERT INTO source_extractions" in sql]
    assert len(evidence) == 1, "Evidence row required — Note Gen depends on it"


# ── AC-007: Failed extraction skips candidate creation ──────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_failed_extraction_not_fabricated_as_unknown(monkeypatch):
    """AC-007: extraction failure → skip candidate creation; mark source as failed."""
    from app.adapters.base import ExtractedContent
    from app.worker import handlers

    async def _failing_extract(source_type, url):
        return ExtractedContent(text="", title="", error="Cannot extract video ID from URL")

    monkeypatch.setattr(handlers, "adapter_extract", _failing_extract)

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    conn = _FakeConn(
        fetch_result=[
            {
                "id": uuid.UUID("00000000-0000-0000-0000-0000000000bb"),
                "type": "youtube",
                "url": "https://www.youtube.com/",
                "title": "",
                "source_scope": "direct_resource",
            }
        ],
        fetchval_result=None,
    )
    await handlers._analysis_handler(
        {"user_id": user_id}, _noop_progress, _FakePool(conn)
    )

    # Verify: no candidate created
    inserts = [args for sql, args in conn.executed if "INSERT INTO candidates" in sql]
    assert len(inserts) == 0, "No candidate should be created on extraction failure"

    # Verify: source marked as failed
    failed_updates = [
        sql
        for sql, _ in conn.executed
        if "UPDATE sources SET status='failed'" in sql
    ]
    assert len(failed_updates) == 1, "Source should be marked as failed"

    # Verify: error logged
    logs = [args for sql, args in conn.executed if "INSERT INTO processing_log" in sql]
    assert len(logs) == 1, "Extraction failure should be logged"
    assert logs[0][2] is not None, "Error details should be stored in log"


# ── AC-008: Discovery provider enumerates videos ──────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_discovery_creates_one_candidate_per_video(monkeypatch):
    """AC-008: channel source → one candidate per discovered video, not one for the channel."""
    from app.adapters.base import ExtractedContent
    from app.adapters.youtube_discovery import DiscoveredVideo, DiscoveryResult
    from app.worker import handlers

    async def _fake_discover(url, limit=25):
        return DiscoveryResult(videos=[
            DiscoveredVideo(url="https://www.youtube.com/watch?v=v1", title="V1"),
            DiscoveredVideo(url="https://www.youtube.com/watch?v=v2", title="V2"),
        ])

    async def _fake_extract(source_type, url):
        return ExtractedContent(text="transcript", title="T", word_count=1)

    monkeypatch.setattr(handlers, "discover_channel_videos", _fake_discover)
    monkeypatch.setattr(handlers, "adapter_extract", _fake_extract)

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    conn = _FakeConn(
        fetch_result=[{"id": uuid.UUID("00000000-0000-0000-0000-0000000000cc"),
                       "type": "youtube", "title": "Channel",
                       "url": "https://www.youtube.com/@chan",
                       "source_scope": "discovery_provider"}],
        fetchval_result=None,
    )
    await handlers._analysis_handler({"user_id": user_id}, _noop_progress, _FakePool(conn))

    inserts = [a for sql, a in conn.executed if "INSERT INTO candidates" in sql]
    assert len(inserts) == 2, "One candidate per discovered video"


# ── AC-009: Dedup is status-agnostic ──────────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_dedup_does_not_filter_by_pending_status(monkeypatch):
    """AC-009: dedup SQL must not restrict to status='pending'."""
    from app.adapters.base import ExtractedContent
    from app.worker import handlers

    async def _fake_extract(source_type, url):
        return ExtractedContent(text="text", title="T", word_count=1)

    monkeypatch.setattr(handlers, "adapter_extract", _fake_extract)

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    conn = _FakeConn(
        fetch_result=[{"id": uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
                       "type": "web", "title": "", "url": "https://example.com/a",
                       "source_scope": "direct_resource"}],
        fetchval_result=None,
    )
    await handlers._analysis_handler({"user_id": user_id}, _noop_progress, _FakePool(conn))

    dedup = [sql for sql, _ in conn.fetchval_calls if "FROM candidates" in sql]
    assert len(dedup) == 1
    assert "status='pending'" not in dedup[0]


# ── AC-011: Unknown job type fails cleanly ────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_unknown_job_type_fails_cleanly(monkeypatch):
    """AC-011: unrecognised job type → status='failed', no crash."""
    from app.worker import runner

    monkeypatch.setattr(runner, "get_handler", lambda t: None)
    conn = _FakeConn()
    job = {"id": "job-x", "user_id": "u1", "type": "Unknown", "source_title": "x"}
    await runner._run_job(_FakePool(conn), job)

    assert any("status='failed'" in sql for sql, _ in conn.executed)


# ── AC-014: Note state machine — 409 on double-action ────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_note_approve_returns_409_when_already_processed():
    """AC-014: approve note that is no longer pending → 409, not 200."""
    from app.api.deps import get_current_user, get_db
    from app.main import app
    from tests.conftest import MOCK_USER

    class _ConflictConn:
        async def execute(self, *a, **kw):
            return "UPDATE 0"
        async def fetch(self, *a, **kw):
            return []
        async def fetchrow(self, *a, **kw):
            return None
        async def fetchval(self, *a, **kw):
            return None

    async def _conflict_db():
        yield _ConflictConn()

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _conflict_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/notes/00000000-0000-0000-0000-0000000000ab/approve")
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


# ── AC-015: Scheduler trigger guards no-sources case ─────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_scheduler_trigger_400_when_no_sources(authed_client):
    """AC-015: POST /api/scheduler/trigger → 400 when user has no sources."""
    resp = await authed_client.post("/api/scheduler/trigger")
    assert resp.status_code == 400
    assert "No sources" in resp.json()["detail"]


# ── AC-017: Browse-directory deprecated (410) ────────────────────────────────

@pytest.mark.smoke
@pytest.mark.regression
async def test_smoke_browse_directory_returns_410(authed_client):
    """AC-017: browse-directory → 410 with Local Sync Bridge message."""
    resp = await authed_client.get("/api/settings/browse-directory")
    assert resp.status_code == 410
    assert "Local Sync Bridge" in resp.json()["detail"]
