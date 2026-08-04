import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import get_current_user, get_db

router = APIRouter()

# TS counterpart: src/types/index.ts — Topic


@router.get("")
async def list_topics(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        "SELECT id, label, color FROM topics WHERE user_id=$1 ORDER BY created_at",
        uuid.UUID(user_id),
    )
    return [{"id": str(r["id"]), "label": r["label"], "color": r["color"]} for r in rows]


@router.post("")
async def create_topic(
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    color = body.get("color", "#3b82f6")
    label = body.get("label", "")
    row = await db.fetchrow(
        "INSERT INTO topics (user_id, label, color) VALUES ($1, $2, $3) RETURNING id, label, color",
        uuid.UUID(user_id),
        label,
        color,
    )
    if row is None:
        return {"id": "", "label": label, "color": color}
    return {"id": str(row["id"]), "label": row["label"], "color": row["color"]}


@router.delete("/{topic_id}")
async def delete_topic(
    topic_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> Response:
    user_id = current_user["sub"]
    try:
        await db.execute(
            "DELETE FROM topics WHERE id=$1 AND user_id=$2",
            uuid.UUID(topic_id),
            uuid.UUID(user_id),
        )
    except ValueError:
        pass
    return Response(status_code=204)

