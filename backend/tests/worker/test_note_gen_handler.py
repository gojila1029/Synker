"""Tests for _note_gen_handler: source_id resolution and the Evidence boundary.

Regression coverage for Stage 5 (ECC tdd-workflow) items 1 and 3:
  1. A known Source must not lose identity — the handler must resolve
     source_type from candidates.source_id, not a fragile URL string match.
  3. A failed/missing extraction must not reach generate_note — no Evidence
     means no Note.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.worker import runner
from app.worker.handlers import NoEvidenceError, _note_gen_handler


class AsyncContextManagerMock:
    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *args):
        pass


def _pool_with(conn):
    pool = Mock()
    pool.acquire = Mock(return_value=AsyncContextManagerMock(conn))
    return pool


@pytest.mark.asyncio
async def test_uses_source_id_when_present_not_url_match():
    """The handler must key the source lookup on candidates.source_id, and
    must never issue the fragile url= lookup when source_id is present."""
    job = {"user_id": "user-1", "candidate_id": "cand-1"}
    calls: list[tuple[str, tuple]] = []

    async def fetchrow(query, *args):
        calls.append((query, args))
        if "FROM candidates" in query:
            return {
                "title": "My Candidate",
                "source_info": "https://example.com/article",
                "summary": "blurb",
                "source_id": "source-99",
                "topic_id": None,
            }
        if "FROM sources WHERE id=" in query:
            return {"type": "web"}
        if "FROM sources WHERE url=" in query:
            raise AssertionError("must not fall back to URL-match lookup when source_id is set")
        if "FROM source_extractions" in query:
            return {"text": "Real extracted evidence text."}
        if "FROM user_settings" in query:
            return {"ai_providers": {}}
        if "SELECT id FROM notes WHERE candidate_id" in query:
            return None
        return None

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)

    pool = _pool_with(conn)
    progress = AsyncMock()

    fake_note = Mock(
        error=None, title="Generated", content="body", frontmatter={},
        citations=[], wiki_links=[], quality_score=0.8, ai_action="created",
        similarity_reasoning="",
    )
    with patch("app.worker.handlers.generate_note", AsyncMock(return_value=fake_note)):
        result = await _note_gen_handler(job, progress, pool)

    assert "Generated" in result
    assert any("FROM sources WHERE id=" in q for q, _ in calls)
    assert not any("FROM sources WHERE url=" in q for q, _ in calls)


@pytest.mark.asyncio
async def test_falls_back_to_url_lookup_when_source_id_missing():
    """Legacy candidates created before source_id was wired still resolve."""
    job = {"user_id": "user-1", "candidate_id": "cand-1"}

    async def fetchrow(query, *args):
        if "FROM candidates" in query:
            return {
                "title": "Legacy Candidate", "source_info": "https://example.com/x",
                "summary": "blurb", "source_id": None, "topic_id": None,
            }
        if "FROM sources WHERE url=" in query:
            return {"type": "pdf"}
        if "FROM source_extractions" in query:
            return None  # no source_id -> no evidence lookup attempted
        if "FROM user_settings" in query:
            return {"ai_providers": {}}
        return None

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.fetch = AsyncMock(return_value=[])
    pool = _pool_with(conn)
    progress = AsyncMock()

    with pytest.raises(NoEvidenceError):
        await _note_gen_handler(job, progress, pool)


@pytest.mark.asyncio
async def test_no_evidence_blocks_note_generation():
    """No source_extractions row -> handler must refuse to call generate_note
    and must NOT fall back to the candidate's discovery-time summary blurb.
    It must raise NoEvidenceError (a real failure), not return a
    failure-looking string that the runner would record as 'completed'."""
    job = {"user_id": "user-1", "candidate_id": "cand-1"}

    async def fetchrow(query, *args):
        if "FROM candidates" in query:
            return {
                "title": "My Candidate", "source_info": "https://example.com/article",
                "summary": "a short discovery blurb, not real evidence",
                "source_id": "source-99", "topic_id": None,
            }
        if "FROM sources WHERE id=" in query:
            return {"type": "web"}
        if "FROM source_extractions" in query:
            return None
        if "FROM user_settings" in query:
            return {"ai_providers": {}}
        return None

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.fetch = AsyncMock(return_value=[])
    pool = _pool_with(conn)
    progress = AsyncMock()

    with patch("app.worker.handlers.generate_note", AsyncMock()) as mock_gen:
        with pytest.raises(NoEvidenceError) as exc_info:
            await _note_gen_handler(job, progress, pool)

    mock_gen.assert_not_called()
    assert exc_info.value.code == "NO_EVIDENCE"
    # The message must be safe to surface — no source content, no URLs.
    assert "example.com" not in str(exc_info.value)
    assert "discovery blurb" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_job_records_failed_status_with_no_evidence_error_code():
    """End-to-end through the real runner: a NO_EVIDENCE Note Gen job must
    land as jobs.status='failed' with error_code='NO_EVIDENCE', never
    'completed', and must never reach the notes/vault_files INSERT path."""
    job = {
        "id": "job-1", "user_id": "user-1", "type": "Note Gen",
        "candidate_id": "cand-1", "source_title": "x",
    }

    async def fetchrow(query, *args):
        if "FROM candidates" in query:
            return {
                "title": "My Candidate", "source_info": "https://example.com/article",
                "summary": "blurb", "source_id": "source-99", "topic_id": None,
            }
        if "FROM sources WHERE id=" in query:
            return {"type": "web"}
        if "FROM source_extractions" in query:
            return None
        if "FROM user_settings" in query:
            return {"ai_providers": {}}
        return None

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    pool = _pool_with(conn)

    with patch("app.worker.handlers.generate_note", AsyncMock()) as mock_gen:
        await runner._run_job(pool, job)

    mock_gen.assert_not_called()
    update_calls = [c for c in conn.execute.call_args_list if "status='failed'" in c.args[0]]
    assert len(update_calls) == 1
    sql, args = update_calls[0].args[0], update_calls[0].args
    assert "status='failed'" in sql
    assert "error_code=" in sql
    assert "NO_EVIDENCE" in args
    assert not any("INSERT INTO notes" in c.args[0] for c in conn.execute.call_args_list)
    assert not any("INSERT INTO vault_files" in c.args[0] for c in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_note_insert_carries_topic_and_source_id():
    """A generated Note must persist the candidate's topic_id/source_id so
    provenance survives even if the candidate is later deleted."""
    job = {"user_id": "user-1", "candidate_id": "cand-1"}

    async def fetchrow(query, *args):
        if "FROM candidates" in query:
            return {
                "title": "My Candidate", "source_info": "https://example.com/article",
                "summary": "blurb", "source_id": "source-99", "topic_id": "topic-7",
            }
        if "FROM sources WHERE id=" in query:
            return {"type": "web"}
        if "FROM source_extractions" in query:
            return {"text": "Real extracted evidence text."}
        if "FROM user_settings" in query:
            return {"ai_providers": {}}
        if "SELECT id FROM notes WHERE candidate_id" in query:
            return None
        return None

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)
    pool = _pool_with(conn)
    progress = AsyncMock()

    fake_note = Mock(
        error=None, title="Generated", content="body", frontmatter={},
        citations=[], wiki_links=[], quality_score=0.8, ai_action="created",
        similarity_reasoning="",
    )
    with patch("app.worker.handlers.generate_note", AsyncMock(return_value=fake_note)):
        await _note_gen_handler(job, progress, pool)

    insert_calls = [c for c in conn.execute.call_args_list if "INSERT INTO notes" in c.args[0]]
    assert len(insert_calls) == 1
    args = insert_calls[0].args
    assert "topic-7" in args
    assert "source-99" in args
