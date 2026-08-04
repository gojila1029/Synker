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


# TS counterpart: src/types/index.ts — Candidate


@router.get("")
async def list_candidates(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        """SELECT id, title, source_info, domain, published_at, topic_id,
                  recommendation, quality_score, confidence_score, duplicate_score,
                  expected_notes, estimated_tokens, summary, extracted_topics, status
           FROM candidates WHERE user_id=$1 ORDER BY created_at DESC""",
        uuid.UUID(user_id),
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "sourceInfo": r["source_info"],
            "domain": r["domain"],
            "publishedAt": r["published_at"].isoformat() if r["published_at"] else None,
            "topicId": str(r["topic_id"]) if r["topic_id"] else None,
            "recommendation": r["recommendation"],
            "qualityScore": r["quality_score"],
            "confidenceScore": r["confidence_score"],
            "duplicateScore": r["duplicate_score"],
            "expectedNotes": r["expected_notes"],
            "estimatedTokens": r["estimated_tokens"],
            "summary": r["summary"],
            "extractedTopics": list(r["extracted_topics"]) if r["extracted_topics"] else [],
            "status": r["status"],
        }
        for r in rows
    ]


@router.post("/approve")
async def approve_candidates(
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    raw_ids = body.get("ids", [])
    ids = [uuid.UUID(i) for i in raw_ids if _is_uuid(i)]
    if ids:
        await db.execute(
            "UPDATE candidates SET status='approved', updated_at=now() WHERE id=ANY($1) AND user_id=$2",
            ids,
            uuid.UUID(user_id) if _is_uuid(user_id) else uuid.UUID(int=0),
        )
    return {"approved": raw_ids}


@router.post("/reject")
async def reject_candidates(
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    raw_ids = body.get("ids", [])
    ids = [uuid.UUID(i) for i in raw_ids if _is_uuid(i)]
    if ids:
        await db.execute(
            "UPDATE candidates SET status='rejected', updated_at=now() WHERE id=ANY($1) AND user_id=$2",
            ids,
            uuid.UUID(user_id) if _is_uuid(user_id) else uuid.UUID(int=0),
        )
    return {"rejected": raw_ids}

