"""Website-specific API endpoints for search and intent parsing."""
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai.intent_parser import parse_website_intent
from app.api.deps import get_current_user, get_db

router = APIRouter()


class ParseIntentRequest(BaseModel):
    message: str


class ParseIntentResponse(BaseModel):
    search_query: str
    limit: int
    confidence: float
    fallback_used: bool = False
    error: str | None = None


@router.post("/parse-intent")
async def parse_intent_endpoint(
    body: ParseIntentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> ParseIntentResponse:
    """Parse a user's natural language message into website search parameters.

    Uses Claude Haiku to extract search query and desired result count.
    """
    user_id = current_user["sub"]

    # Fetch user's AI settings
    settings_row = await db.fetchrow(
        "SELECT ai_providers FROM user_settings WHERE user_id=$1", uuid.UUID(user_id)
    )
    ai_settings = settings_row["ai_providers"] if settings_row else {}

    # Parse intent
    intent = await parse_website_intent(body.message, ai_settings)

    return ParseIntentResponse(
        search_query=intent.search_query,
        limit=intent.limit,
        confidence=intent.confidence,
        fallback_used=intent.fallback_used,
        error=intent.error,
    )
