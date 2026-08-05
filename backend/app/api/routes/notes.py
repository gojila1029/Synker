import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db

router = APIRouter()

# TS counterpart: src/types/index.ts — Note


@router.get("")
async def list_notes(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        """SELECT id, title, source, generated_at, ai_action, quality_score,
                  has_duplicate, content, frontmatter, citations, wiki_links,
                  similarity_reasoning, similar_to, status
           FROM notes WHERE user_id=$1 AND status != 'rejected'
           ORDER BY generated_at DESC""",
        uuid.UUID(user_id),
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "source": r["source"],
            "generatedAt": r["generated_at"].isoformat() if r["generated_at"] else None,
            "aiAction": r["ai_action"],
            "qualityScore": r["quality_score"],
            "hasDuplicate": r["has_duplicate"],
            "content": r["content"],
            "frontmatter": r["frontmatter"] or {},
            "citations": r["citations"] or [],
            "wikiLinks": r["wiki_links"] or [],
            "similarityReasoning": r["similarity_reasoning"],
            "similarTo": str(r["similar_to"]) if r["similar_to"] else None,
        }
        for r in rows
    ]


@router.post("/{note_id}/approve")
async def approve_note(
    note_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    try:
        await db.execute(
            "UPDATE notes SET status='approved', approved_at=now() WHERE id=$1 AND user_id=$2",
            uuid.UUID(note_id),
            uuid.UUID(user_id),
        )
    except ValueError:
        pass
    return {"approved": note_id}


@router.post("/{note_id}/reject")
async def reject_note(
    note_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    try:
        await db.execute(
            "UPDATE notes SET status='rejected' WHERE id=$1 AND user_id=$2",
            uuid.UUID(note_id),
            uuid.UUID(user_id),
        )
    except ValueError:
        pass
    return {"rejected": note_id}

