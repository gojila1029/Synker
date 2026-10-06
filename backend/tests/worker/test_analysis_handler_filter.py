"""Unit tests for analysis handler source filtering and Note Gen source_id.

Tests verify behaviour through actual function calls and mock inspection,
NOT by reading source files as text.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes.candidates import approve_candidates
from app.worker.handlers import _analysis_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _AsyncCtxMgr:
    """Minimal async context manager that yields a pre-created mock conn."""

    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *_: object) -> None:
        pass


def _make_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value = _AsyncCtxMgr(conn)
    return pool


def _user(sub: str) -> dict:
    return {"sub": sub}


# ---------------------------------------------------------------------------
# AC-001 / AC-008: Analysis handler queries only status='queued' sources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analysis_handler_fetches_only_queued_sources():
    """GIVEN an Analysis job for user U
    WHEN _analysis_handler executes
    THEN conn.fetch is called with SQL containing AND status='queued'
    AND the bound parameter is the correct user_id.

    Covers AC-001 and AC-008.
    """
    user_id = str(uuid.uuid4())
    job = {"user_id": user_id}

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])  # no queued sources → early exit
    pool = _make_pool(conn)

    await _analysis_handler(job, AsyncMock(), pool)

    conn.fetch.assert_called_once()
    sql = conn.fetch.call_args.args[0]
    bound_user_id = conn.fetch.call_args.args[1]

    assert "AND status='queued'" in sql, (
        f"SQL must filter to queued sources only; got:\n{sql}"
    )
    assert bound_user_id == user_id, (
        f"SQL must be bound to the job's user_id; got {bound_user_id!r}"
    )


@pytest.mark.asyncio
async def test_analysis_handler_returns_early_when_no_queued_sources():
    """GIVEN no queued sources exist for the user
    WHEN _analysis_handler executes
    THEN it returns immediately with a 0-candidate message
    AND no further acquire calls are made for extraction.

    Covers AC-002: only queued sources are processed.
    """
    job = {"user_id": str(uuid.uuid4())}

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    pool = _make_pool(conn)
    progress = AsyncMock()

    result = await _analysis_handler(job, progress, pool)

    assert "0 candidates" in result
    assert pool.acquire.call_count == 1


# ---------------------------------------------------------------------------
# AC-003 / AC-007: Note Gen job INSERT includes source_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_candidates_inserts_source_id_in_note_gen_job():
    """GIVEN a user approves candidate C
    WHEN approve_candidates runs
    THEN db.execute is called with an INSERT INTO jobs statement
    AND that statement includes the source_id column and a SELECT clause.

    Covers AC-003 and AC-007.
    """
    user_id = str(uuid.uuid4())
    candidate_id = str(uuid.uuid4())

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=["UPDATE 1", None])

    from app.schemas.candidates import BulkIds

    body = BulkIds(ids=[candidate_id])
    await approve_candidates(body=body, current_user=_user(user_id), db=db)

    assert db.execute.call_count == 2, (
        "Expected two db.execute calls: UPDATE candidates + INSERT INTO jobs"
    )

    insert_sql = db.execute.call_args_list[1].args[0]
    assert "INSERT INTO jobs" in insert_sql
    assert "source_id" in insert_sql, (
        f"INSERT INTO jobs must include source_id column; got:\n{insert_sql}"
    )
    assert "SELECT" in insert_sql, (
        "INSERT must use SELECT to fetch source_id from candidates"
    )
