import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.adapters.classify import classify_source_scope
from app.api.deps import get_current_user, get_db
from app.schemas.sources import SourceCreate

router = APIRouter()

# TS counterpart: src/types/index.ts — Source


@router.get("")
async def list_sources(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        """SELECT id, type, source_scope, title, url, topic_id, status, schedule, added_at
           FROM sources WHERE user_id=$1 ORDER BY added_at DESC""",
        uuid.UUID(user_id),
    )
    return [
        {
            "id": str(r["id"]),
            "type": r["type"],
            "sourceScope": r["source_scope"],
            "title": r["title"],
            "url": r["url"],
            "topicId": str(r["topic_id"]) if r["topic_id"] else None,
            "status": r["status"],
            "addedAt": r["added_at"].isoformat() if r["added_at"] else None,
            "schedule": r["schedule"],
        }
        for r in rows
    ]


@router.post("")
async def add_source(
    body: SourceCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    topic_id = body.topic_id
    # The client never sends a meaningful source_scope (no UI field for it),
    # so SourceCreate's "direct_resource" default is wrong for a bare
    # platform homepage. Classify it server-side instead of trusting body.
    source_scope = classify_source_scope(body.type, body.url)
    row = await db.fetchrow(
        """INSERT INTO sources (user_id, topic_id, type, source_scope, title, url, schedule)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id, type, source_scope, title, url, topic_id, status, schedule, added_at""",
        uuid.UUID(user_id),
        uuid.UUID(topic_id) if topic_id else None,
        body.type,
        source_scope,
        body.title,
        body.url,
        None,
    )
    if row is None:
        return {"id": "", "type": body.type, "sourceScope": source_scope,
                "title": body.title, "url": body.url, "topicId": topic_id,
                "status": "queued", "addedAt": None, "schedule": None}
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "sourceScope": row["source_scope"],
        "title": row["title"],
        "url": row["url"],
        "topicId": str(row["topic_id"]) if row["topic_id"] else None,
        "status": row["status"],
        "addedAt": row["added_at"].isoformat() if row["added_at"] else None,
        "schedule": row["schedule"],
    }


@router.patch("/{source_id}/reset")
async def reset_source(
    source_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    try:
        sid, uid = uuid.UUID(source_id), uuid.UUID(user_id)
    except ValueError:
        return {"reset": source_id}
    row = await db.fetchrow(
        "UPDATE sources SET status='queued', updated_at=now() WHERE id=$1 AND user_id=$2 RETURNING id, status",
        sid, uid,
    )
    return {"reset": source_id, "status": row["status"] if row else "not_found"}


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> Response:
    user_id = current_user["sub"]
    try:
        await db.execute(
            "DELETE FROM sources WHERE id=$1 AND user_id=$2",
            uuid.UUID(source_id),
            uuid.UUID(user_id),
        )
    except ValueError:
        pass
    return Response(status_code=204)

