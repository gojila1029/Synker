"""Tests for scheduler_loop (SYN-V5-003). Tests auto-creation of Analysis jobs."""
import asyncio
import uuid as _uuid
from contextlib import asynccontextmanager

from app.worker import runner


class FakeConn:
    """Mocks a database connection for hermetic testing."""

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
        # Smart default: return a count (1) when checking queued sources,
        # None when checking for existing jobs (allows tests to pass without
        # explicitly overriding the logic)
        if "COUNT(*)" in sql:
            return 1  # At least one queued source available
        return self._fetchval_result

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"

    @asynccontextmanager
    async def transaction(self):
        """Mock transaction context manager — passes through."""
        yield


class FakePool:
    """Mocks an asyncpg connection pool."""

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


async def test_scheduler_loop_creates_analysis_job_when_user_has_queued_sources():
    """scheduler_loop finds a user with queued sources and no pending/running
    Analysis job, then creates an Analysis job for them."""
    user_id = _uuid.UUID("00000000-0000-0000-0000-000000000099")
    job_id = _uuid.UUID("00000000-0000-0000-0000-000000000088")

    conn = FakeConn(
        fetch_result=[{"user_id": user_id}],  # One user with queued sources
        fetchval_result=None,  # No existing Analysis job for this user
        fetchrow_result={"id": job_id},  # INSERT returns the new job row
    )
    pool = FakePool(conn)
    stop = asyncio.Event()

    # Run the loop in a task and stop it after a short delay
    async def run_then_stop():
        await asyncio.sleep(0.01)
        stop.set()

    # Start both the scheduler loop and the stopper concurrently
    await asyncio.gather(
        runner.scheduler_loop(stop, pool),
        run_then_stop(),
    )

    # Verify we checked for existing Analysis job
    fetchval_sql = [sql for sql, _ in conn.fetchval_calls]
    assert any(
        "Analysis" in sql for sql in fetchval_sql
    ), "Should check for existing pending/running Analysis job"

    # Verify we called fetchrow to insert a new Analysis job
    fetchrow_sql = [sql for sql, _ in conn.fetchrow_calls]
    insert_calls = [sql for sql in fetchrow_sql if "INSERT INTO jobs" in sql]
    assert len(insert_calls) >= 1, "Should insert a new Analysis job"
    assert any("Analysis" in sql for sql in insert_calls), "Job type should be Analysis"

    # Verify we logged the creation
    log_calls = [sql for sql, _ in conn.executed if "processing_log" in sql]
    assert len(log_calls) >= 1, "Should log the job creation"


async def test_scheduler_loop_does_not_create_job_when_analysis_already_pending():
    """scheduler_loop skips a user if they already have a pending or running
    Analysis job."""
    user_id = _uuid.UUID("00000000-0000-0000-0000-000000000077")
    conn = FakeConn(
        fetch_result=[{"user_id": user_id}],  # One user with queued sources
        fetchval_result=1,  # Existing Analysis job (return 1 means "found")
    )
    pool = FakePool(conn)
    stop = asyncio.Event()

    # Run the loop in a task and stop it after a short delay
    async def run_then_stop():
        await asyncio.sleep(0.01)
        stop.set()

    await asyncio.gather(
        runner.scheduler_loop(stop, pool),
        run_then_stop(),
    )

    # Verify we checked for existing Analysis job
    fetchval_sql = [sql for sql, _ in conn.fetchval_calls]
    assert len(fetchval_sql) >= 1, "Should check for existing Analysis job"

    # Verify we did NOT call fetchrow to insert (because one was already pending)
    fetchrow_sql = [sql for sql, _ in conn.fetchrow_calls]
    insert_calls = [sql for sql in fetchrow_sql if "INSERT INTO jobs" in sql]
    assert (
        len(insert_calls) == 0
    ), "Should not insert a new Analysis job when one is already pending"


async def test_scheduler_loop_stops_when_event_is_set():
    """scheduler_loop respects the stop event and exits gracefully."""
    conn = FakeConn(fetch_result=[])  # No users with queued sources
    pool = FakePool(conn)
    stop = asyncio.Event()

    # Set stop immediately so loop exits
    stop.set()
    await runner.scheduler_loop(stop, pool)

    assert stop.is_set()


async def test_scheduler_loop_handles_multiple_users_with_queued_sources():
    """scheduler_loop iterates over all users with queued sources and creates
    a job for each (only when they don't already have one pending)."""
    user_id_1 = _uuid.UUID("00000000-0000-0000-0000-000000000011")
    user_id_2 = _uuid.UUID("00000000-0000-0000-0000-000000000022")
    job_id_1 = _uuid.UUID("00000000-0000-0000-0000-000000000111")

    conn = FakeConn(
        fetch_result=[
            {"user_id": user_id_1},
            {"user_id": user_id_2},
        ],  # Two users with queued sources
        fetchval_result=None,  # No existing Analysis jobs
        fetchrow_result={"id": job_id_1},  # INSERT returns a job row
    )
    pool = FakePool(conn)
    stop = asyncio.Event()

    async def run_then_stop():
        await asyncio.sleep(0.01)
        stop.set()

    await asyncio.gather(
        runner.scheduler_loop(stop, pool),
        run_then_stop(),
    )

    # Verify we checked for existing Analysis jobs for both users
    fetchval_sql = [sql for sql, _ in conn.fetchval_calls]
    assert len(fetchval_sql) >= 2, "Should check for existing Analysis job for each user"

    # Verify we inserted Analysis jobs for both users
    fetchrow_sql = [sql for sql, _ in conn.fetchrow_calls]
    insert_calls = [sql for sql in fetchrow_sql if "INSERT INTO jobs" in sql]
    assert len(insert_calls) >= 2, "Should insert Analysis jobs for multiple users"
