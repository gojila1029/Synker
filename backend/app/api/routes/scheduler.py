import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

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
    row = await db.fetchrow(
        "INSERT INTO jobs (user_id, source_title, type) VALUES ($1, 'Discovery Run', 'Analysis') RETURNING id",
        uid,
    )
    return {"triggered": True, "jobId": str(row["id"]) if row else None}
