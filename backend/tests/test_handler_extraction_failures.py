"""Handler tests for extraction failure scenarios (OQ-001)."""
import json
import pytest
from app.adapters.base import ExtractedContent
from app.worker import handlers


class FakeConn:
    """Fake async connection that records SQL statements."""
    def __init__(self, fetchrow_result=None, fetch_result=None, fetchval_result=None):
        self._fetchrow_result = fetchrow_result
        self._fetch_result = fetch_result if fetch_result is not None else []
        self._fetchval_result = fetchval_result
        self.executed: list[tuple] = []
        self.fetchval_calls: list[tuple] = []
        self.fetchrow_calls: list[tuple] = []

    async def fetch(self, sql, *args):
        return self._fetch_result

    async def fetchrow(self, sql, *args):
        self.fetchrow_calls.append((sql, args))
        return self._fetchrow_result

    async def fetchval(self, sql, *args):
        self.fetchval_calls.append((sql, args))
        return self._fetchval_result

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


class FakePool:
    """Fake async pool."""
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


async def _noop_progress(pct):
    pass


@pytest.mark.asyncio
async def test_analysis_handler_skips_candidate_when_extraction_fails(monkeypatch):
    """When extraction fails (error set, text empty), skip candidate creation
    and mark source as failed."""

    # Mock adapter_extract to return failed extraction
    async def _mock_extract_fail(source_type, source_url):
        return ExtractedContent(text="", title="", error="Network timeout")

    monkeypatch.setattr(handlers, "adapter_extract", _mock_extract_fail)

    # Setup: one source to analyze
    source_row = {
        "id": "src-1",
        "type": "web",
        "url": "https://example.com",
        "title": "Example",
        "source_scope": "direct_resource",
    }

    conn = FakeConn(fetch_result=[source_row])
    pool = FakePool(conn)

    job = {
        "id": "job-1",
        "user_id": "user-1",
        "type": "Analysis",
    }

    result = await handlers._analysis_handler(job, _noop_progress, pool)

    # Verify: no candidates created (0 candidates in result)
    assert "0 candidate(s) created" in result

    # Verify: source was marked as failed
    executed_stmts = [stmt for stmt in conn.executed if "UPDATE sources SET status='failed'" in stmt[0]]
    assert len(executed_stmts) == 1
    assert executed_stmts[0][1] == ("src-1", "user-1")

    # Verify: extraction error was logged
    log_stmts = [stmt for stmt in conn.executed if "INSERT INTO processing_log" in stmt[0]]
    assert len(log_stmts) == 1
    assert "extraction_failed" in log_stmts[0][0]
    # Check that error was stored
    details_json = log_stmts[0][1][2]
    details = json.loads(details_json)
    assert details["error"] == "Network timeout"


@pytest.mark.asyncio
async def test_analysis_handler_creates_candidate_when_extraction_succeeds(monkeypatch):
    """When extraction succeeds (text present, no error), create candidate."""

    async def _mock_extract_success(source_type, source_url):
        return ExtractedContent(
            text="Important content here",
            title="Article Title",
            author="John Doe",
            published_at="2026-10-07",
            word_count=150,
        )

    monkeypatch.setattr(handlers, "adapter_extract", _mock_extract_success)

    # Mock _compute_candidate_similarity to return low score
    async def _mock_similarity(pool, user_id, text, title):
        return 0.1

    monkeypatch.setattr(handlers, "_compute_candidate_similarity", _mock_similarity)

    source_row = {
        "id": "src-2",
        "type": "web",
        "url": "https://example.com",
        "title": "Example",
        "source_scope": "direct_resource",
    }

    conn = FakeConn(fetch_result=[source_row])
    pool = FakePool(conn)

    job = {"id": "job-2", "user_id": "user-2", "type": "Analysis"}

    result = await handlers._analysis_handler(job, _noop_progress, pool)

    # Verify: candidate was created
    assert "1 candidate(s) created" in result

    # Verify: source was marked as processing (not failed)
    update_processing = [
        stmt for stmt in conn.executed
        if "UPDATE sources SET status='processing'" in stmt[0]
    ]
    assert len(update_processing) == 1


@pytest.mark.asyncio
async def test_note_gen_includes_extraction_error_in_message(monkeypatch):
    """When Note Gen fails due to missing evidence, check processing_log
    for extraction error and include it in the error message."""

    candidate_row = {
        "id": "cand-1",
        "title": "Test Candidate",
        "source_info": "https://example.com",
        "summary": "",
        "source_id": "src-3",
        "topic_id": None,
    }

    # First query gets candidate, then settings, then existing notes,
    # then source type, then extraction evidence (returns None),
    # then extraction error log
    ai_settings_row = {"ai_providers": {}}
    source_type_row = {"type": "web"}
    error_log_row = {
        "details": {"error": "Connection refused: 443"}
    }

    # We need to track multiple fetchrow calls
    fetchrow_results = [
        candidate_row,
        ai_settings_row,
        source_type_row,
        None,  # extraction evidence (not found)
        error_log_row,  # extraction error log
    ]

    call_count = [0]

    async def _mock_fetchrow(sql, *args):
        result = fetchrow_results[call_count[0]]
        call_count[0] += 1
        return result

    # Mock conn with sequential responses
    class SequentialFakeConn(FakeConn):
        async def fetchrow(self, sql, *args):
            self.fetchrow_calls.append((sql, args))
            return await _mock_fetchrow(sql, *args)

    conn = SequentialFakeConn(fetch_result=[])
    pool = FakePool(conn)

    job = {
        "id": "job-3",
        "user_id": "user-3",
        "candidate_id": "cand-1",
    }

    with pytest.raises(handlers.NoEvidenceError) as exc_info:
        await handlers._note_gen_handler(job, _noop_progress, pool)

    # Verify: error message includes extraction error
    error_msg = str(exc_info.value)
    assert "Connection refused" in error_msg
    assert "extraction failed" in error_msg.lower() or "Source extraction failed" in error_msg
