import uuid
from datetime import timedelta
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_db

router = APIRouter()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


@router.post("/trigger")
async def trigger_discovery(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    uid = uuid.UUID(user_id) if _is_uuid(user_id) else uuid.UUID(int=0)
    count = await db.fetchval("SELECT COUNT(*) FROM sources WHERE user_id=$1", uid)
    if not count:
        raise HTTPException(status_code=400, detail="No sources found — add some first")
    row = await db.fetchrow(
        "INSERT INTO jobs (user_id, source_title, type) "
        "VALUES ($1, 'Discovery Run', 'Analysis') RETURNING id",
        uid,
    )
    if row is not None:
        await db.execute(
            "INSERT INTO processing_log (user_id, entity_type, entity_id, action, details) "
            "VALUES ($1, 'job', $2, 'created', $3::jsonb)",
            uid,
            row["id"],
            '{"message": "Discovery run triggered"}',
        )
    return {"triggered": True, "jobId": str(row["id"]) if row else None}


@router.get("/status")
async def get_scheduler_status(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"last_run_at": None, "next_run_at": None, "is_running": False}

    last = await db.fetchrow(
        """SELECT finished_at FROM jobs
           WHERE user_id=$1 AND type='Analysis' AND status='completed'
           ORDER BY finished_at DESC LIMIT 1""",
        uid,
    )
    running = await db.fetchval(
        "SELECT 1 FROM jobs WHERE user_id=$1 AND type='Analysis' AND status='running' LIMIT 1",
        uid,
    )
    last_run_at = last["finished_at"].isoformat() if last else None
    next_run_at = None
    if last and last["finished_at"]:
        next_run_at = (last["finished_at"] + timedelta(minutes=10)).isoformat()

    return {"last_run_at": last_run_at, "next_run_at": next_run_at, "is_running": bool(running)}
