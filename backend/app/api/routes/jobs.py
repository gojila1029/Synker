import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db

router = APIRouter()

# TS counterpart: src/types/index.ts — Job


def _format_duration(started_at: Any, finished_at: Any) -> str:
    if started_at is None:
        return "0s"
    end = finished_at or started_at
    secs = int((end - started_at).total_seconds())
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"


@router.get("")
async def list_jobs(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return []
    rows = await db.fetch(
        """SELECT id, source_title, type, status, progress, error,
                  artifact_path, started_at, finished_at
           FROM jobs WHERE user_id=$1 ORDER BY started_at DESC LIMIT 100""",
        uid,
    )
    return [
        {
            "id": str(r["id"]),
            "sourceTitle": r["source_title"],
            "type": r["type"],
            "status": r["status"],
            "progress": r["progress"],
            "error": r["error"],
            "artifactPath": r["artifact_path"],
            "startedAt": r["started_at"].isoformat() if r["started_at"] else None,
            "duration": _format_duration(r["started_at"], r["finished_at"]),
        }
        for r in rows
    ]


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    try:
        jid = uuid.UUID(job_id)
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"retried": job_id}
    original = await db.fetchrow(
        "SELECT source_id, candidate_id, source_title, type FROM jobs WHERE id=$1 AND user_id=$2",
        jid,
        uid,
    )
    if original is None:
        return {"retried": job_id}
    row = await db.fetchrow(
        """INSERT INTO jobs (user_id, source_id, candidate_id, source_title, type)
           VALUES ($1, $2, $3, $4, $5) RETURNING id""",
        uid,
        original["source_id"],
        original["candidate_id"],
        original["source_title"],
        original["type"],
    )
    new_id = str(row["id"]) if row else job_id
    return {"retried": job_id, "newJobId": new_id}
