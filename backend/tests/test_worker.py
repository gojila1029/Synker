"""Worker lifecycle tests (SYN-V5-002). Hermetic: a fake pool/connection records
SQL so no real database is required (mirrors conftest.MockConn)."""
import pytest

from app.worker import handlers, runner


class FakeConn:
    def __init__(self, fetchrow_result=None, fetch_result=None, fetchval_result=None):
        self._fetchrow_result = fetchrow_result
        self._fetch_result = fetch_result if fetch_result is not None else []
        self._fetchval_result = fetchval_result
        self.executed: list[tuple] = []

    async def fetch(self, sql, *args):
        return self._fetch_result

    async def fetchrow(self, sql, *args):
        return self._fetchrow_result

    async def fetchval(self, sql, *args):
        return self._fetchval_result

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


async def _noop_progress(pct):
    pass


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


async def test_claim_one_returns_claimed_job():
    job = {
        "id": "00000000-0000-0000-0000-0000000000aa",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "type": "Analysis",
        "source_title": "Discovery Run",
    }
    conn = FakeConn(fetchrow_result=job)
    claimed = await runner._claim_one(conn, "worker-1")
    assert claimed == job


async def test_claim_one_returns_none_when_queue_empty():
    conn = FakeConn(fetchrow_result=None)
    assert await runner._claim_one(conn, "worker-1") is None


async def test_run_job_completes_and_logs(monkeypatch):
    async def _fast_handler(job, progress, pool):
        await progress(50)
        return "done"

    monkeypatch.setattr(runner, "get_handler", lambda t: _fast_handler)
    conn = FakeConn()
    pool = FakePool(conn)
    job = {"id": "job-1", "user_id": "user-1", "type": "Analysis", "source_title": "x"}

    await runner._run_job(pool, job)

    sql_blob = " ".join(sql for sql, _ in conn.executed)
    assert "status='completed'" in sql_blob
    assert "progress=$1" in sql_blob  # progress was written
    assert "processing_log" in sql_blob  # completion event logged


async def test_run_job_unknown_type_fails(monkeypatch):
    monkeypatch.setattr(runner, "get_handler", lambda t: None)
    conn = FakeConn()
    pool = FakePool(conn)
    job = {"id": "job-2", "user_id": "user-1", "type": "Mystery", "source_title": "x"}

    await runner._run_job(pool, job)

    statuses = [sql for sql, _ in conn.executed]
    assert any("status='failed'" in sql for sql in statuses)


async def test_reap_stale_issues_update():
    conn = FakeConn()
    await runner._reap_stale(conn)
    assert len(conn.executed) == 1
    sql, args = conn.executed[0]
    assert "Worker stalled" in sql
    assert "make_interval" in sql


async def test_analysis_handler_with_no_sources():
    seen: list[int] = []

    async def _progress(pct):
        seen.append(pct)

    import uuid as _uuid
    user_id = _uuid.UUID("00000000-0000-0000-0000-000000000001")
    pool = FakePool(FakeConn())  # fetch returns [] — no sources
    result = await handlers._analysis_handler({"user_id": user_id}, _progress, pool)

    assert 100 in seen
    assert "0 candidates" in result


async def test_analysis_handler_preserves_real_error_on_failed_extraction(monkeypatch):
    """Stage 6 verification-loop ROOT CAUSE #1/#3: a source with no title and
    a failed extraction must not surface as a healthy-looking "Unknown"
    candidate with a generic "Extraction pending" summary and a normal
    0.75/0.70 score — that misrepresents a real failure as a good result."""
    import uuid as _uuid

    from app.adapters.base import ExtractedContent

    async def _failing_extract(source_type, url):
        return ExtractedContent(
            text="", title="", error=f"Cannot extract video ID from URL: {url}",
        )

    monkeypatch.setattr(handlers, "adapter_extract", _failing_extract)

    user_id = _uuid.UUID("00000000-0000-0000-0000-000000000001")
    source_id = _uuid.UUID("00000000-0000-0000-0000-0000000000bb")
    source = {
        "id": source_id, "type": "youtube", "title": "", "url": "https://www.youtube.com/",
        "source_scope": "direct_resource",
    }
    conn = FakeConn(fetch_result=[source], fetchval_result=None)
    pool = FakePool(conn)

    await handlers._analysis_handler({"user_id": user_id}, _noop_progress, pool)

    inserts = [args for sql, args in conn.executed if "INSERT INTO candidates" in sql]
    assert len(inserts) == 1
    args = inserts[0]
    title, summary, quality_score, confidence_score, recommendation = (
        args[2], args[12], args[7], args[8], args[6],
    )
    assert title != "Unknown"
    assert "Cannot extract video ID" in summary
    assert quality_score == 0.0
    assert confidence_score == 0.0
    assert recommendation != "process"


async def test_analysis_handler_skips_extraction_for_discovery_provider_sources(monkeypatch):
    """A source classified as discovery_provider (e.g. a bare platform
    homepage) has no real discovery engine behind it yet — attempting direct
    extraction on it produces the same misleading "Unknown" candidate this
    fix addresses. Skip it honestly instead of pretending to have looked."""
    import uuid as _uuid

    called = False

    async def _should_not_be_called(source_type, url):
        nonlocal called
        called = True
        raise AssertionError("adapter_extract must not be called for discovery_provider sources")

    monkeypatch.setattr(handlers, "adapter_extract", _should_not_be_called)

    user_id = _uuid.UUID("00000000-0000-0000-0000-000000000001")
    source_id = _uuid.UUID("00000000-0000-0000-0000-0000000000cc")
    source = {
        "id": source_id, "type": "youtube", "title": "", "url": "https://www.youtube.com/",
        "source_scope": "discovery_provider",
    }
    conn = FakeConn(fetch_result=[source], fetchval_result=None)
    pool = FakePool(conn)

    result = await handlers._analysis_handler({"user_id": user_id}, _noop_progress, pool)

    assert called is False
    inserts = [args for sql, args in conn.executed if "INSERT INTO candidates" in sql]
    assert len(inserts) == 0
    assert "0 candidate" in result


async def test_analysis_handler_persists_evidence_on_successful_extraction(monkeypatch):
    """No code path anywhere in the backend ever creates a job of type
    'Extraction' (verified by grepping every INSERT INTO jobs call site) —
    _extraction_handler and every adapter exist and work, but nothing
    automatically triggers them. That leaves source_extractions permanently
    empty, so _note_gen_handler's NoEvidenceError check fails every single
    Note Gen job, for every source type, forever. _analysis_handler already
    fetches the full ExtractedContent to build the candidate summary — it
    must persist that same content as Evidence instead of only using a
    500-char truncation for display, or Notes can never be generated."""
    import uuid as _uuid

    from app.adapters.base import ExtractedContent

    async def _fake_extract(source_type, url):
        return ExtractedContent(
            text="Full real transcript text, much longer than 500 chars for the summary.",
            title="Real Title",
            author="Real Author",
            published_at="2026-01-01T00:00:00Z",
            source_type=source_type,
            word_count=11,
            timestamps=[{"seconds": 0, "text": "Full"}],
        )

    monkeypatch.setattr(handlers, "adapter_extract", _fake_extract)

    user_id = _uuid.UUID("00000000-0000-0000-0000-000000000001")
    source_id = _uuid.UUID("00000000-0000-0000-0000-0000000000dd")
    source = {
        "id": source_id,
        "type": "youtube",
        "title": "",
        "url": "https://www.youtube.com/watch?v=abc12345678",
        "source_scope": "direct_resource",
    }
    conn = FakeConn(fetch_result=[source], fetchval_result=None)
    pool = FakePool(conn)

    await handlers._analysis_handler({"user_id": user_id}, _noop_progress, pool)

    inserts = [
        (sql, args) for sql, args in conn.executed if "INSERT INTO source_extractions" in sql
    ]
    assert len(inserts) == 1, (
        "a successful extraction must be persisted as Evidence — otherwise "
        "Note Gen can never find it and every candidate stays stuck forever"
    )
    _, args = inserts[0]
    assert source_id in args
    assert user_id in args
    assert "Full real transcript text" in args


@pytest.mark.parametrize("tag,expected", [("UPDATE 1", True), ("UPDATE 0", False), (None, True)])
def test_affected(tag, expected):
    assert runner._affected(tag) is expected
