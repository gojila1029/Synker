"""YouTube-specific API endpoints for search, intent parsing, and batch note creation.

Provides endpoints for:
- /search: Search YouTube for videos (does not create DB records)
- /parse-intent: Parse NL messages into search parameters
- /notes/batch: Create notes from multiple video URLs (Track B workflow)
"""
import json
import uuid
from typing import Any
from urllib.parse import urlparse

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.adapters.base import ExtractedContent
from app.adapters.youtube import _extract_video_id
from app.adapters.youtube_search import search_youtube
from app.ai.intent_parser import parse_youtube_intent
from app.api.deps import get_current_user, get_db
from app.db.client import get_pool
from app.worker.handlers import _candidate_fields, _compute_candidate_similarity

router = APIRouter()


class YouTubeSearchItem(BaseModel):
    video_id: str
    title: str
    url: str
    channel: str | None = None


class YouTubeSearchResponse(BaseModel):
    results: list[YouTubeSearchItem] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None


class ParseIntentRequest(BaseModel):
    message: str


class ParsedIntentResponse(BaseModel):
    search_query: str
    limit: int
    confidence: float
    fallback_used: bool = False
    error: str | None = None


class BatchNoteRequest(BaseModel):
    model_config = {"populate_by_name": True}
    # Accept both snake_case (video_urls) and camelCase (videoUrls) from clients
    video_urls: list[str] = Field(alias="videoUrls", default_factory=list)


class BatchNoteItem(BaseModel):
    url: str
    video_id: str | None = None
    status: str  # SUCCESS, ALREADY_EXISTS, FAILED
    error: str | None = None
    candidate_id: str | None = None


class BatchNoteResponse(BaseModel):
    results: list[BatchNoteItem] = Field(default_factory=list)


@router.get("/search")
async def search_youtube_endpoint(
    q: str,
    limit: int = 10,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> YouTubeSearchResponse:
    """Search YouTube for videos matching a query.

    Does NOT create any database records — only returns search results.
    """
    if not q or not q.strip():
        return YouTubeSearchResponse(error="Query cannot be empty", error_code="INVALID_QUERY")

    limit = max(1, min(25, limit))
    result = await search_youtube(q.strip(), limit=limit)

    if result.error:
        return YouTubeSearchResponse(
            error=result.error,
            error_code=result.error_code,
        )

    return YouTubeSearchResponse(
        results=[
            YouTubeSearchItem(
                video_id=r.video_id,
                title=r.title,
                url=r.url,
                channel=r.channel,
            )
            for r in result.results
        ]
    )


@router.post("/parse-intent")
async def parse_intent_endpoint(
    body: ParseIntentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> ParsedIntentResponse:
    """Parse a user's natural language message into search parameters.

    Uses Claude Haiku to extract search query and desired result count.
    """
    user_id = current_user["sub"]

    # Fetch user's AI settings
    settings_row = await db.fetchrow(
        "SELECT ai_providers FROM user_settings WHERE user_id=$1", uuid.UUID(user_id)
    )
    ai_settings = settings_row["ai_providers"] if settings_row else {}

    # Parse intent
    intent = await parse_youtube_intent(body.message, ai_settings)

    return ParsedIntentResponse(
        search_query=intent.search_query,
        limit=intent.limit,
        confidence=intent.confidence,
        fallback_used=intent.fallback_used,
        error=intent.error,
    )


@router.post("/notes/batch")
async def create_notes_batch(
    body: BatchNoteRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> BatchNoteResponse:
    """Create notes from multiple YouTube video URLs (Track B workflow).

    Per video:
    1. Dedup check (skip if already has a candidate)
    2. Extract video ID
    3. Create source (if not exists)
    4. Extract content via adapter
    5. Create candidate with status=approved (auto-approve for Track B only)
    6. Enqueue NoteGen job

    Returns per-item status (200 with partial failures acceptable).
    """
    user_id = current_user["sub"]
    user_uuid = uuid.UUID(user_id)
    results: list[BatchNoteItem] = []

    from app.adapters import extract as adapter_extract

    for url in body.video_urls:
        if not url or not url.strip():
            results.append(BatchNoteItem(url=url or "", status="FAILED", error="Empty URL"))
            continue

        url = url.strip()
        video_id = _extract_video_id(url)

        if not video_id:
            results.append(
                BatchNoteItem(
                    url=url,
                    status="FAILED",
                    error="Invalid YouTube URL or cannot extract video ID",
                )
            )
            continue

        try:
            # Dedup check with canonical URL
            canonical_url = f"https://www.youtube.com/watch?v={video_id}"
            existing = await db.fetchval(
                "SELECT 1 FROM candidates WHERE user_id=$1 AND source_info=$2 LIMIT 1",
                user_uuid,
                canonical_url,
            )
            if existing:
                results.append(
                    BatchNoteItem(
                        url=url,
                        video_id=video_id,
                        status="ALREADY_EXISTS",
                        error="Candidate already exists for this URL",
                    )
                )
                continue

            # Find or create source
            source_row = await db.fetchrow(
                "SELECT id FROM sources WHERE user_id=$1 AND type=$2 AND url=$3 LIMIT 1",
                user_uuid,
                "youtube",
                url,
            )
            source_id = None
            if source_row:
                source_id = source_row["id"]
            else:
                # Create a new source for this video
                new_source_id = uuid.uuid4()
                await db.execute(
                    """INSERT INTO sources
                       (id, user_id, type, source_scope, title, url, status)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    new_source_id,
                    user_uuid,
                    "youtube",
                    "direct_resource",
                    f"YouTube video {video_id}",
                    url,
                    "processing",
                )
                source_id = new_source_id

            # Extract content
            extracted: ExtractedContent | None = None
            try:
                extracted = await adapter_extract("youtube", url)
            except Exception as exc:
                extracted = ExtractedContent(
                    text="",
                    title="",
                    source_url=url,
                    source_type="youtube",
                    error=str(exc),
                )

            domain = urlparse(url).netloc if url else "youtube.com"
            fields = _candidate_fields(extracted, f"YouTube video {video_id}", domain)

            # Create candidate with status=approved (Track B auto-approves)
            # db is already a Connection from get_db; use directly (no acquire)
            pool = await get_pool()
            dup_score = await _compute_candidate_similarity(
                pool,
                user_uuid,
                extracted.text if (extracted and not extracted.error) else fields["summary"],
                fields["title"],
            )
            if True:
                conn = db
                candidate_row = await conn.fetchrow(
                    """INSERT INTO candidates
                       (user_id, source_id, title, source_info, domain, published_at,
                        recommendation, quality_score, confidence_score,
                        duplicate_score, expected_notes, estimated_tokens,
                        summary, extracted_topics, status)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                               $12, $13, $14, $15)
                       RETURNING id""",
                    user_uuid,
                    source_id,
                    fields["title"],
                    canonical_url,
                    domain,
                    fields["published_at"],
                    fields["recommendation"],
                    fields["quality_score"],
                    fields["confidence_score"],
                    dup_score,
                    1,
                    max(1000, fields["word_count"] * 2),
                    fields["summary"],
                    [],
                    "approved",  # Track B auto-approves
                )
                candidate_id = candidate_row["id"] if candidate_row else None

                # Persist extraction as evidence
                if extracted and extracted.text and not extracted.error:
                    timestamps_json = (
                        json.dumps(extracted.timestamps)
                        if extracted.timestamps
                        else None
                    )
                    await conn.execute(
                        """INSERT INTO source_extractions
                           (source_id, user_id, source_url, text, title, author,
                            published_at, timestamps, word_count)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                        source_id,
                        user_uuid,
                        url,
                        extracted.text,
                        extracted.title,
                        extracted.author,
                        extracted.published_at,
                        timestamps_json,
                        extracted.word_count,
                    )

                # Enqueue NoteGen job
                if candidate_id:
                    job_id = uuid.uuid4()
                    await conn.execute(
                        """INSERT INTO jobs
                           (id, user_id, type, source_id, candidate_id, status)
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        job_id,
                        user_uuid,
                        "Note Gen",
                        source_id,
                        candidate_id,
                        "queued",
                    )

            results.append(
                BatchNoteItem(
                    url=url,
                    video_id=video_id,
                    status="SUCCESS",
                    candidate_id=str(candidate_id) if candidate_id else None,
                )
            )
        except Exception as exc:
            results.append(
                BatchNoteItem(
                    url=url,
                    video_id=video_id,
                    status="FAILED",
                    error=str(exc)[:200],
                )
            )

    return BatchNoteResponse(results=results)
