"""Worker lifecycle tests (SYN-V5-002). Hermetic: a fake pool/connection records
SQL so no real database is required (mirrors conftest.MockConn)."""
import pytest

from app.worker import handlers, runner


class FakeConn:
    def __init__(self, fetchrow_result=None):
        self._fetchrow_result = fetchrow_result
        self.executed: list[tuple] = []

    async def fetchrow(self, sql, *args):
        return self._fetchrow_result

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


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
    async def _fast_handler(job, progress):
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


async def test_discovery_handler_is_honest(monkeypatch):
    monkeypatch.setattr(handlers, "STEP_DELAY_SECONDS", 0)
    seen: list[int] = []

    async def _progress(pct):
        seen.append(pct)

    result = await handlers._discovery_handler({"type": "Analysis"}, _progress)

    assert seen == [20, 60, 90]
    assert "0 new candidates" in result
    assert "no source adapters" in result


@pytest.mark.parametrize("tag,expected", [("UPDATE 1", True), ("UPDATE 0", False), (None, True)])
def test_affected(tag, expected):
    assert runner._affected(tag) is expected
