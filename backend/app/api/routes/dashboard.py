import json
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db

router = APIRouter()

# TS counterpart: src/types/index.ts — DashboardStats, ActivityEvent


@router.get("/stats")
async def get_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    uid = uuid.UUID(user_id)

    pending = await db.fetchval(
        "SELECT COUNT(*) FROM candidates WHERE user_id=$1 AND status='pending'", uid
    ) or 0
    running_jobs = await db.fetchval(
        "SELECT COUNT(*) FROM jobs WHERE user_id=$1 AND status='running'", uid
    ) or 0
    queued_jobs = await db.fetchval(
        "SELECT COUNT(*) FROM jobs WHERE user_id=$1 AND status='queued'", uid
    ) or 0
    notes_today = await db.fetchval(
        "SELECT COUNT(*) FROM notes WHERE user_id=$1 AND generated_at >= CURRENT_DATE", uid
    ) or 0
    sources_indexed = await db.fetchval(
        "SELECT COUNT(*) FROM sources WHERE user_id=$1 AND status='done'", uid
    ) or 0

    pipeline_counts: dict[str, int] = {}
    for stage in ("discover", "analyze", "approve", "extract", "transcribe",
                  "generate", "verify", "graphify", "cleanup"):
        pipeline_counts[stage] = int(
            await db.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE user_id=$1 AND lower(type) LIKE $2",
                uid,
                f"%{stage[:4]}%",
            ) or 0
        )

    return {
        "pendingApprovals": int(pending),
        "runningJobs": int(running_jobs),
        "queuedJobs": int(queued_jobs),
        "notesToday": int(notes_today),
        "sourcesIndexed": int(sources_indexed),
        "pipelineCounts": pipeline_counts,
    }


@router.get("/activity")
async def get_activity(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        """SELECT id, entity_type, entity_id, action, details, created_at
           FROM processing_log WHERE user_id=$1
           ORDER BY created_at DESC LIMIT 50""",
        uuid.UUID(user_id),
    )
    events: list[dict[str, Any]] = []
    for r in rows:
        details = r["details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (ValueError, TypeError):
                details = {}
        message = details.get("message") if isinstance(details, dict) else None
        events.append(
            {
                "id": str(r["id"]),
                "type": r["action"],
                "message": message or f"{r['action']} {r['entity_type']}",
                "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )
    return events
