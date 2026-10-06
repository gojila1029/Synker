"""In-process job worker (SYN-V5-002).

Claims queued jobs atomically (FOR UPDATE SKIP LOCKED so multiple replicas never
double-process), drives each to a terminal state with progress + heartbeat, and
recovers jobs abandoned by a stalled worker.

Started from the FastAPI lifespan when WORKER_ENABLED=true. Requires migration
002 (heartbeat_at / claimed_by).
"""
import asyncio
import logging
import os
import socket
from typing import Any

from app.core.config import settings
from app.db.client import get_pool
from app.worker.handlers import get_handler

_log = logging.getLogger("synker.worker")

# Identifies which worker claimed a job — useful for debugging multi-replica runs.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


async def _claim_one(conn: Any, worker_id: str) -> dict[str, Any] | None:
    """Atomically take the oldest queued job and flip it to running. Returns the
    claimed row, or None when the queue is empty."""
    row = await conn.fetchrow(
        """
        UPDATE jobs
           SET status='running', started_at=now(), heartbeat_at=now(),
               claimed_by=$1, progress=0, error=NULL, finished_at=NULL
         WHERE id = (
             SELECT id FROM jobs
              WHERE status='queued'
              ORDER BY started_at ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
         )
        RETURNING id, user_id, type, source_title, source_id, candidate_id
        """,
        worker_id,
    )
    return dict(row) if row else None


def _json_str(value: str) -> str:
    """Minimal JSON string escaping for the details payload."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


async def _log_event(conn: Any, job: dict[str, Any], action: str, message: str) -> None:
    await conn.execute(
        "INSERT INTO processing_log (user_id, entity_type, entity_id, action, details) "
        "VALUES ($1, 'job', $2, $3, $4::jsonb)",
        job["user_id"],
        job["id"],
        action,
        '{"message": ' + _json_str(message) + "}",
    )


def _affected(command_tag: Any) -> bool:
    """asyncpg execute() returns a tag like 'UPDATE 1'. True when >0 rows changed.
    A mock connection returning None is treated as changed (test convenience)."""
    if command_tag is None:
        return True
    if isinstance(command_tag, str):
        parts = command_tag.split()
        return bool(parts) and parts[-1].isdigit() and int(parts[-1]) > 0
    return True


async def _run_job(pool: Any, job: dict[str, Any]) -> None:
    """Execute a claimed job and persist its terminal state. All writes are
    guarded by `status='running'` so a concurrent cancel (which sets the job to
    failed) is never clobbered by a late success."""
    job_id = job["id"]

    async def progress(pct: int) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET progress=$1, heartbeat_at=now() "
                "WHERE id=$2 AND status='running'",
                pct,
                job_id,
            )

    handler = get_handler(job["type"])
    try:
        if handler is None:
            raise RuntimeError(f"No handler registered for job type {job['type']!r}")
        result = await handler(job, progress, pool)
        async with pool.acquire() as conn:
            done = await conn.execute(
                """UPDATE jobs
                      SET status='completed', progress=100, finished_at=now(),
                          heartbeat_at=now(),
                          duration_seconds=EXTRACT(EPOCH FROM now()-started_at)::int
                    WHERE id=$1 AND status='running'""",
                job_id,
            )
            if _affected(done):
                await _log_event(conn, job, "created", result)
        _log.info("Job %s completed: %s", job_id, result)
    except Exception as exc:  # noqa: BLE001 — any handler failure is a job failure
        _log.exception("Job %s failed", job_id)
        # Handlers that need a machine-readable failure reason (e.g.
        # NoEvidenceError) set a .code attribute; anything else leaves it
        # NULL rather than guessing a code from the message text.
        error_code = getattr(exc, "code", None)
        async with pool.acquire() as conn:
            failed = await conn.execute(
                """UPDATE jobs
                      SET status='failed', error=$2, error_code=$3, finished_at=now(),
                          heartbeat_at=now(),
                          duration_seconds=EXTRACT(EPOCH FROM now()-started_at)::int
                    WHERE id=$1 AND status='running'""",
                job_id,
                str(exc)[:500],
                error_code,
            )
            if _affected(failed):
                await _log_event(conn, job, "failed", str(exc)[:200])


async def _reap_stale(conn: Any) -> None:
    """Fail running jobs whose heartbeat is older than the stale timeout — their
    worker died mid-run. They stay retriable/cancellable via the existing routes."""
    await conn.execute(
        """UPDATE jobs
              SET status='failed', error='Worker stalled — no heartbeat',
                  finished_at=now()
            WHERE status='running'
              AND heartbeat_at IS NOT NULL
              AND heartbeat_at < now() - make_interval(secs => $1)""",
        settings.job_stale_seconds,
    )


async def worker_loop(stop: asyncio.Event, pool: Any | None = None) -> None:
    """Fill up to worker_concurrency running jobs, then wait poll_seconds (or until
    stopped) and repeat. Drains in-flight jobs on shutdown."""
    pool = pool or await get_pool()
    running: set[asyncio.Task[None]] = set()
    _log.info("Worker %s started (concurrency=%s)", WORKER_ID, settings.worker_concurrency)
    while not stop.is_set():
        while len(running) < settings.worker_concurrency:
            try:
                async with pool.acquire() as conn:
                    job = await _claim_one(conn, WORKER_ID)
            except Exception:  # noqa: BLE001 — never let a claim error kill the loop
                _log.exception("Claim query failed")
                break
            if job is None:
                break
            task = asyncio.create_task(_run_job(pool, job))
            running.add(task)
            task.add_done_callback(running.discard)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
        except TimeoutError:
            pass
    if running:
        await asyncio.gather(*running, return_exceptions=True)
    _log.info("Worker %s stopped", WORKER_ID)


async def reaper_loop(stop: asyncio.Event, pool: Any | None = None) -> None:
    """Periodically recover jobs abandoned by a stalled worker."""
    pool = pool or await get_pool()
    while not stop.is_set():
        try:
            async with pool.acquire() as conn:
                await _reap_stale(conn)
        except Exception:  # noqa: BLE001
            _log.exception("Reaper sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.job_stale_seconds)
        except TimeoutError:
            pass


async def scheduler_loop(stop: asyncio.Event, pool: Any | None = None) -> None:
    """Auto-create Analysis jobs for users who have queued sources but no
    pending or running Analysis job. Runs every worker_poll_seconds * 10
    seconds so the default 10-minute cadence is approximated without a
    separate config setting."""
    pool = pool or await get_pool()
    interval = settings.worker_poll_seconds * 10
    _log.info("Scheduler loop started (interval=%.0fs)", interval)
    while not stop.is_set():
        try:
            async with pool.acquire() as conn:
                users = await conn.fetch(
                    "SELECT DISTINCT user_id FROM sources WHERE status = 'queued'"
                )
                for row in users:
                    uid = row["user_id"]
                    already = await conn.fetchval(
                        """SELECT 1 FROM jobs
                           WHERE user_id = $1
                             AND type = 'Analysis'
                             AND status IN ('queued', 'running')
                           LIMIT 1""",
                        uid,
                    )
                    if already:
                        continue
                    job_row = await conn.fetchrow(
                        """INSERT INTO jobs (user_id, source_title, type)
                           VALUES ($1, 'Discovery Run', 'Analysis')
                           RETURNING id""",
                        uid,
                    )
                    if job_row:
                        await conn.execute(
                            """INSERT INTO processing_log
                               (user_id, entity_type, entity_id, action, details)
                               VALUES ($1, 'job', $2, 'created', $3::jsonb)""",
                            uid,
                            job_row["id"],
                            '{"message": "Auto-scheduled Analysis run"}',
                        )
                        _log.info(
                            "Scheduler: created Analysis job %s for user %s",
                            job_row["id"],
                            uid,
                        )
        except Exception:  # noqa: BLE001
            _log.exception("Scheduler sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    _log.info("Scheduler loop stopped")
