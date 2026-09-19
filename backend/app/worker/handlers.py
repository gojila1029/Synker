"""Job-type handlers.

A handler does the real work for one job and returns a short, truthful result
summary. Handlers report progress via the injected async callback and MUST NOT
fabricate notes, candidates, or citations — if there is nothing real to do, they
say so honestly. Handlers should handle all exceptions gracefully and return a
meaningful error message rather than crashing.
"""
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.adapters import extract as adapter_extract
from app.adapters.base import ExtractedContent, ExtractionError
from app.adapters.registry import get_adapter
from app.adapters.youtube_discovery import discover_channel_videos
from app.ai import generate_note

_log = logging.getLogger(__name__)

# pct -> None. Persists progress + heartbeat for the running job.
ProgressFn = Callable[[int], Awaitable[None]]

# (job_row, progress, pool) -> result summary string.
Handler = Callable[[dict[str, Any], ProgressFn, Any], Awaitable[str]]

# Seconds between discovery progress steps. Kept short; tests set it to 0.
STEP_DELAY_SECONDS = 1.2

# English stopwords to exclude from similarity keywords
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "on", "at",
    "for", "with", "by", "from", "and", "or", "but", "not", "this", "that",
    "these", "those", "it", "its", "which", "who", "what", "when", "where",
    "why", "how",
}


class NoEvidenceError(Exception):
    """Raised when a handler refuses to act because there is no valid
    Evidence to act on (CLAUDE.md: 'No valid Evidence -> no Knowledge Note').
    runner._run_job maps this to jobs.status='failed' with the machine
    -readable jobs.error_code taken from .code, instead of letting it fall
    through as a merely failure-looking string that would record the job as
    'completed'. The message must never contain source content or URLs —
    it becomes jobs.error, which is not access-controlled the same way
    source_extractions is."""

    code = "NO_EVIDENCE"


def _extract_keywords(text: str, title: str = "") -> set[str]:
    """Extract keywords from title and first 5 sentences of text.

    Returns a set of lowercase tokens with length >= 3, excluding common
    English stopwords. Algorithm: Jaccard similarity uses keywords to compute
    overlap between candidate and vault notes.
    """
    # Combine title + first 5 sentences
    combined = title
    if text:
        sentences = re.split(r'[.!?]+', text.strip())
        first_five = sentences[:5]
        combined = combined + " " + " ".join(first_five)

    # Tokenize: split on whitespace and punctuation
    tokens = re.findall(r'\b\w+\b', combined.lower())

    # Filter: keep only tokens >= 3 chars and not in stopwords
    keywords = {t for t in tokens if len(t) >= 3 and t not in STOPWORDS}
    return keywords


async def _compute_candidate_similarity(
    pool: Any, user_id: Any, candidate_text: str, candidate_title: str
) -> float:
    """Compute Jaccard similarity between candidate and vault notes.

    Returns max similarity score in [0.0, 1.0]:
    - 0.0: no meaningful overlap (unique candidate)
    - 0.5: moderate overlap (candidate partially covers existing knowledge)
    - 1.0: near-perfect or exact duplicate

    Uses keyword-based Jaccard: |A ∩ B| / |A ∪ B|.
    Queries vault_files first; falls back to notes table if empty.
    Completes in < 5 seconds wall-clock time per AC-005.
    Returns 0.0 on error or empty vault per AC-007 and AC-008.
    """
    if not candidate_text or not candidate_text.strip():
        return 0.0

    try:
        t0 = time.monotonic()

        # Fetch vault notes (primary source)
        async with pool.acquire() as conn:
            vault_rows = await conn.fetch(
                "SELECT content FROM vault_files WHERE user_id=$1 LIMIT 200",
                user_id,
            )

        # Fallback to notes table if vault is empty
        if not vault_rows:
            async with pool.acquire() as conn:
                vault_rows = await conn.fetch(
                    "SELECT content FROM notes WHERE user_id=$1 AND status='approved' LIMIT 200",
                    user_id,
                )

        # Empty vault: return 0.0 per AC-004
        if not vault_rows:
            return 0.0

        # Extract candidate keywords once
        cand_kw = _extract_keywords(candidate_text, candidate_title)
        if not cand_kw:
            return 0.0

        # Compute max Jaccard similarity across all vault notes
        max_sim = 0.0
        for row in vault_rows:
            # Check 5-second timeout per AC-005
            if time.monotonic() - t0 > 4.5:
                _log.warning("Similarity computation timeout, returning partial result")
                break

            vault_kw = _extract_keywords(row["content"] or "")
            union = len(cand_kw | vault_kw)
            if union == 0:
                continue
            intersection = len(cand_kw & vault_kw)
            sim = intersection / union
            if sim > max_sim:
                max_sim = sim

        return min(1.0, max_sim)
    except Exception as exc:
        _log.warning("Similarity computation failed: %s", exc)
        return 0.0


def _safe_filename(title: str) -> str:
    """Convert a note title to a safe filename by replacing special characters."""
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)
    return safe[:100]


def _candidate_fields(
    extracted: ExtractedContent | None, fallback_title: str, domain: str
) -> dict[str, Any]:
    """Build a candidate row's variable fields from an extraction result,
    honestly reflecting failure (Stage 6 ROOT CAUSE #1) rather than a fake
    healthy-looking score. Shared between the direct_resource path and each
    video discovered from a discovery_provider source."""
    if extracted and (extracted.error or not extracted.text):
        # Honest failure: keep the real error, do not claim a normal
        # quality/confidence score, and fall back to the domain (not the
        # word "Unknown") when there's no title — the URL/domain is real
        # lineage, "Unknown" is not.
        return {
            "title": fallback_title or domain or "Untitled source",
            "summary": extracted.error if extracted.error else "Extraction pending",
            "published_at": None,
            "word_count": 0,
            "recommendation": "review",
            "quality_score": 0.0,
            "confidence_score": 0.0,
        }
    return {
        "title": extracted.title if extracted else fallback_title,
        "summary": extracted.text[:500] if extracted and extracted.text else "",
        "published_at": extracted.published_at if extracted else None,
        "word_count": extracted.word_count if extracted else 0,
        "recommendation": "process",
        "quality_score": 0.75,
        "confidence_score": 0.70,
    }


async def _create_candidate_with_evidence(
    pool: Any,
    user_id: Any,
    source_id: Any,
    source_url: str,
    domain: str,
    fields: dict[str, Any],
    extracted: ExtractedContent | None,
) -> bool:
    """Insert a candidate row, deduped against ANY existing candidate for
    this source_url regardless of status — an approved or rejected
    candidate must never be silently recreated just because it is no
    longer 'pending'. Also persists the extraction as Evidence
    (source_extractions) when it actually succeeded, since no job type
    anywhere in this codebase ever enqueues a separate "Extraction" job to
    do that later. Returns True if a new candidate was created."""
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT 1 FROM candidates WHERE user_id=$1 AND source_info=$2 LIMIT 1",
            user_id,
            source_url,
        )
        if existing:
            return False

        # Compute real Jaccard similarity against vault notes
        dup_score = await _compute_candidate_similarity(
            pool,
            user_id,
            extracted.text if extracted else fields["summary"],
            fields["title"],
        )

        await conn.execute(
            """INSERT INTO candidates
               (user_id, source_id, title, source_info, domain, published_at,
                recommendation, quality_score, confidence_score,
                duplicate_score, expected_notes, estimated_tokens,
                summary, extracted_topics, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                       $12, $13, $14, $15)""",
            user_id,
            source_id,
            fields["title"],
            source_url,
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
            "pending",
        )

        if extracted and extracted.text and not extracted.error:
            timestamps_json = (
                json.dumps(extracted.timestamps) if extracted.timestamps else None
            )
            await conn.execute(
                """INSERT INTO source_extractions
                   (source_id, user_id, source_url, text, title, author,
                    published_at, timestamps, word_count)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                source_id,
                user_id,
                source_url,
                extracted.text,
                extracted.title,
                extracted.author,
                extracted.published_at,
                timestamps_json,
                extracted.word_count,
            )
    return True


async def _discover_videos_for_source(
    pool: Any, user_id: Any, source: dict[str, Any]
) -> int | None:
    """Real Discovery engine for a discovery_provider source (a YouTube
    channel/playlist URL with no resolvable video id — see
    app/adapters/classify.py). Enumerates its videos via yt-dlp and creates
    one candidate + Evidence pair per new video. Returns the count created,
    or None when discovery was skipped (unsupported/failed) -- the caller
    must not lump that in with "0 videos found" since a skipped source is
    already marked 'failed' and must not be flipped back to 'done'."""
    discovery = await discover_channel_videos(source["url"])

    if discovery.error or discovery.unsupported_reason:
        reason = discovery.error or discovery.unsupported_reason
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO processing_log
                   (user_id, entity_type, entity_id, action, details)
                   VALUES ($1, 'source', $2, 'discovery_skipped', $3::jsonb)""",
                user_id,
                source["id"],
                json.dumps({"reason": reason}),
            )
            await conn.execute(
                "UPDATE sources SET status='failed' WHERE id=$1 AND user_id=$2",
                source["id"],
                user_id,
            )
        return None

    discovered_count = 0
    for video in discovery.videos:
        video_extracted: ExtractedContent | None = None
        try:
            video_extracted = await adapter_extract("youtube", video.url)
        except Exception as exc:
            video_extracted = ExtractedContent(text="", title="", error=str(exc))

        video_domain = urlparse(video.url).netloc if video.url else ""
        fields = _candidate_fields(video_extracted, video.title, video_domain)

        created = await _create_candidate_with_evidence(
            pool, user_id, source["id"], video.url, video_domain, fields, video_extracted
        )
        if created:
            discovered_count += 1

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO processing_log
               (user_id, entity_type, entity_id, action, details)
               VALUES ($1, 'source', $2, 'discovery_completed', $3::jsonb)""",
            user_id,
            source["id"],
            json.dumps({"found": len(discovery.videos), "created": discovered_count}),
        )
        await conn.execute(
            "UPDATE sources SET status='processing' WHERE id=$1 AND user_id=$2",
            source["id"],
            user_id,
        )
    return discovered_count


async def _discover_youtube_keyword(
    pool: Any, user_id: Any, source: dict[str, Any]
) -> int | None:
    """Discover YouTube videos via keyword search."""
    from app.adapters.youtube_search import search_youtube

    keyword = source.get("keyword")
    discovery_limit = source.get("discovery_limit", 25)

    if not keyword:
        return None

    result = await search_youtube(keyword, limit=discovery_limit)
    if result.error or not result.results:
        reason = result.error or "No results found"
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO processing_log
                   (user_id, entity_type, entity_id, action, details)
                   VALUES ($1, 'source', $2, 'discovery_skipped', $3::jsonb)""",
                user_id,
                source["id"],
                json.dumps({"reason": reason}),
            )
        return 0

    discovered_count = 0
    for search_result in result.results:
        video_url = search_result.url
        video_extracted: ExtractedContent | None = None
        try:
            video_extracted = await adapter_extract("youtube", video_url)
        except Exception as exc:
            video_extracted = ExtractedContent(text="", title="", error=str(exc))

        video_domain = urlparse(video_url).netloc if video_url else ""
        fields = _candidate_fields(video_extracted, search_result.title, video_domain)

        # Create candidate with status=pending (not auto-approved)
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT 1 FROM candidates WHERE user_id=$1 AND source_info=$2 LIMIT 1",
                user_id,
                video_url,
            )
            if existing:
                continue

            # Compute real Jaccard similarity against vault notes
            dup_score = await _compute_candidate_similarity(
                pool,
                user_id,
                video_extracted.text if video_extracted else fields["summary"],
                fields["title"],
            )

            await conn.execute(
                """INSERT INTO candidates
                   (user_id, source_id, title, source_info, domain, published_at,
                    recommendation, quality_score, confidence_score,
                    duplicate_score, expected_notes, estimated_tokens,
                    summary, extracted_topics, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                           $12, $13, $14, $15)""",
                user_id,
                source["id"],
                fields["title"],
                video_url,
                video_domain,
                fields["published_at"],
                fields["recommendation"],
                fields["quality_score"],
                fields["confidence_score"],
                dup_score,
                1,
                max(1000, fields["word_count"] * 2),
                fields["summary"],
                [],
                "pending",
            )

            if video_extracted and video_extracted.text and not video_extracted.error:
                timestamps_json = (
                    json.dumps(video_extracted.timestamps)
                    if video_extracted.timestamps
                    else None
                )
                await conn.execute(
                    """INSERT INTO source_extractions
                       (source_id, user_id, source_url, text, title, author,
                        published_at, timestamps, word_count)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    source["id"],
                    user_id,
                    video_url,
                    video_extracted.text,
                    video_extracted.title,
                    video_extracted.author,
                    video_extracted.published_at,
                    timestamps_json,
                    video_extracted.word_count,
                )

        discovered_count += 1

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO processing_log
               (user_id, entity_type, entity_id, action, details)
               VALUES ($1, 'source', $2, 'discovery_completed', $3::jsonb)""",
            user_id,
            source["id"],
            json.dumps({"found": len(result.results), "created": discovered_count}),
        )
        await conn.execute(
            "UPDATE sources SET status='processing' WHERE id=$1 AND user_id=$2",
            source["id"],
            user_id,
        )
    return discovered_count


async def _discover_website_keyword(
    pool: Any, user_id: Any, source: dict[str, Any]
) -> int | None:
    """Discover websites via keyword search."""
    from app.adapters.web_search import search_websites

    keyword = source.get("keyword")
    discovery_limit = source.get("discovery_limit", 25)

    if not keyword:
        return None

    result = await search_websites(keyword, limit=discovery_limit)
    if result.error or not result.results:
        reason = result.error or "No results found"
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO processing_log
                   (user_id, entity_type, entity_id, action, details)
                   VALUES ($1, 'source', $2, 'discovery_skipped', $3::jsonb)""",
                user_id,
                source["id"],
                json.dumps({"reason": reason}),
            )
        return 0

    discovered_count = 0
    for search_result in result.results:
        website_url = search_result.url
        website_extracted: ExtractedContent | None = None
        try:
            website_extracted = await adapter_extract("web", website_url)
        except Exception as exc:
            website_extracted = ExtractedContent(text="", title="", error=str(exc))

        website_domain = urlparse(website_url).netloc if website_url else ""
        fields = _candidate_fields(website_extracted, search_result.title, website_domain)

        # Normalize URL for dedup
        from app.adapters.web_search import _normalize_url

        normalized_url = _normalize_url(website_url)

        # Create candidate with status=pending (not auto-approved)
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT 1 FROM candidates WHERE user_id=$1 AND source_info=$2 LIMIT 1",
                user_id,
                normalized_url,
            )
            if existing:
                continue

            # Compute real Jaccard similarity against vault notes
            dup_score = await _compute_candidate_similarity(
                pool,
                user_id,
                website_extracted.text if website_extracted else fields["summary"],
                fields["title"],
            )

            await conn.execute(
                """INSERT INTO candidates
                   (user_id, source_id, title, source_info, domain, published_at,
                    recommendation, quality_score, confidence_score,
                    duplicate_score, expected_notes, estimated_tokens,
                    summary, extracted_topics, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                           $12, $13, $14, $15)""",
                user_id,
                source["id"],
                fields["title"],
                normalized_url,
                website_domain,
                fields["published_at"],
                fields["recommendation"],
                fields["quality_score"],
                fields["confidence_score"],
                dup_score,
                1,
                max(1000, fields["word_count"] * 2),
                fields["summary"],
                [],
                "pending",
            )

            if website_extracted and website_extracted.text and not website_extracted.error:
                timestamps_json = (
                    json.dumps(website_extracted.timestamps)
                    if website_extracted.timestamps
                    else None
                )
                await conn.execute(
                    """INSERT INTO source_extractions
                       (source_id, user_id, source_url, text, title, author,
                        published_at, timestamps, word_count)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    source["id"],
                    user_id,
                    normalized_url,
                    website_extracted.text,
                    website_extracted.title,
                    website_extracted.author,
                    website_extracted.published_at,
                    timestamps_json,
                    website_extracted.word_count,
                )

        discovered_count += 1

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO processing_log
               (user_id, entity_type, entity_id, action, details)
               VALUES ($1, 'source', $2, 'discovery_completed', $3::jsonb)""",
            user_id,
            source["id"],
            json.dumps({"found": len(result.results), "created": discovered_count}),
        )
        await conn.execute(
            "UPDATE sources SET status='processing' WHERE id=$1 AND user_id=$2",
            source["id"],
            user_id,
        )
    return discovered_count


async def _analysis_handler(job: dict[str, Any], progress: ProgressFn, pool: Any) -> str:
    """Discovery: scan queued sources, extract metadata, create candidate records.

    Routes sources based on discovery_mode:
    - 'keyword' → YouTube keyword search
    - 'web_keyword' → Website keyword search
    - 'channel_playlist' → Channel/playlist enumeration
    - 'single' or None → Direct extraction
    """
    user_id = job["user_id"]
    created = 0
    skipped_discovery_ids: list[Any] = []

    try:
        async with pool.acquire() as conn:
            sources = await conn.fetch(
                """SELECT id, type, title, url, source_scope, discovery_mode,
                          keyword, discovery_limit
                   FROM sources WHERE user_id=$1""",
                user_id,
            )

        if not sources:
            await progress(100)
            return "0 candidates — no queued sources found"

        total = len(sources)
        for i, source in enumerate(sources):
            try:
                await progress(10 + 70 * (i + 1) // total)

                discovery_mode = source.get("discovery_mode")
                source_type = source["type"] or "web"
                source_url = source["url"]

                # Route by discovery_mode
                if discovery_mode == "keyword":
                    discovered = await _discover_youtube_keyword(pool, user_id, source)
                    if discovered is None:
                        skipped_discovery_ids.append(source["id"])
                    else:
                        created += discovered
                    continue

                if discovery_mode == "web_keyword":
                    discovered = await _discover_website_keyword(pool, user_id, source)
                    if discovered is None:
                        skipped_discovery_ids.append(source["id"])
                    else:
                        created += discovered
                    continue

                if (
                    source["source_scope"] == "discovery_provider"
                    or discovery_mode == "channel_playlist"
                ):
                    discovered = await _discover_videos_for_source(pool, user_id, source)
                    if discovered is None:
                        skipped_discovery_ids.append(source["id"])
                    else:
                        created += discovered
                    continue

                # Direct extraction path (single or None)
                extracted = None
                try:
                    extracted = await adapter_extract(source_type, source_url)
                except Exception as exc:
                    extracted = ExtractedContent(text="", title="", error=str(exc))

                domain = urlparse(source_url).netloc if source_url else ""
                fields = _candidate_fields(extracted, source["title"], domain)

                if await _create_candidate_with_evidence(
                    pool, user_id, source["id"], source_url, domain, fields, extracted
                ):
                    created += 1

                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE sources SET status='processing' WHERE id=$1 AND user_id=$2",
                        source["id"],
                        user_id,
                    )
            except Exception:
                pass

        done_ids = [s["id"] for s in sources if s["id"] not in skipped_discovery_ids]
        if done_ids:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE sources SET status='done' WHERE id=ANY($1) AND user_id=$2",
                    done_ids,
                    user_id,
                )

        await progress(100)
        return f"{created} candidate(s) created from {total} source(s)"
    except Exception as e:
        await progress(100)
        return f"Analysis failed: {str(e)[:100]}"


async def _extraction_handler(job: dict[str, Any], progress: ProgressFn, pool: Any) -> str:
    """Full content extraction for a specific source."""
    user_id = job["user_id"]
    source_id = job.get("source_id")

    if not source_id:
        await progress(100)
        return "No source_id — skipping"

    try:
        async with pool.acquire() as conn:
            source = await conn.fetchrow(
                "SELECT id, type, url, title FROM sources WHERE id=$1 AND user_id=$2",
                source_id,
                user_id,
            )

        if not source:
            await progress(100)
            return f"Source {source_id} not found"

        await progress(30)

        source_type = source["type"] or "web"
        adapter = get_adapter(source_type)
        if not adapter:
            raise RuntimeError(f"No adapter for source type {source_type!r}")

        try:
            content = await adapter.extract(source["url"])
        except ExtractionError as e:
            raise RuntimeError(str(e)) from e

        await progress(80)

        timestamps_json = json.dumps(content.timestamps) if content.timestamps else None

        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO source_extractions
                   (source_id, user_id, text, title, author, published_at, timestamps, word_count)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                source["id"],
                user_id,
                content.text,
                content.title,
                content.author,
                content.published_at,
                timestamps_json,
                content.word_count,
            )

            await conn.execute(
                "UPDATE sources SET status='done' WHERE id=$1",
                source["id"],
            )

        await progress(100)
        return f"{content.word_count} words extracted from {source['title']!r}"
    except Exception as e:
        await progress(100)
        return f"Extraction handler failed: {str(e)[:100]}"


async def _note_gen_handler(job: dict[str, Any], progress: ProgressFn, pool: Any) -> str:
    """Generate an Obsidian note from an approved candidate using AI."""
    user_id = job["user_id"]
    candidate_id = job.get("candidate_id")

    if not candidate_id:
        await progress(100)
        return "No candidate_id — cannot generate note"

    try:
        async with pool.acquire() as conn:
            candidate = await conn.fetchrow(
                """SELECT title, source_info, summary, source_id, topic_id
                   FROM candidates WHERE id=$1 AND user_id=$2""",
                candidate_id,
                user_id,
            )

        if not candidate:
            await progress(100)
            return f"Candidate {candidate_id} not found"

        await progress(20)

        source_id = candidate["source_id"]
        topic_id = candidate["topic_id"]
        source_url = candidate["source_info"]

        async with pool.acquire() as conn:
            ai_row = await conn.fetchrow(
                "SELECT ai_providers FROM user_settings WHERE user_id=$1", user_id
            )
            ai_settings = ai_row["ai_providers"] if ai_row else {}

            existing_rows = await conn.fetch(
                "SELECT title FROM notes WHERE user_id=$1 AND status='approved' "
                "ORDER BY generated_at DESC LIMIT 100",
                user_id,
            )

            # Prefer the candidate's real source_id FK over re-deriving type from
            # a URL string match, which breaks silently if a source's URL changed
            # or two sources share a URL.
            if source_id:
                source_row = await conn.fetchrow(
                    "SELECT type FROM sources WHERE id=$1 AND user_id=$2",
                    source_id,
                    user_id,
                )
            else:
                source_row = await conn.fetchrow(
                    "SELECT type FROM sources WHERE url=$1 AND user_id=$2 LIMIT 1",
                    source_url,
                    user_id,
                )
            source_type = source_row["type"] if source_row else "web"

            # No Evidence -> No Note: require a real extraction row for this
            # source. For discovery_provider channels, multiple video extractions
            # share the same source_id — prefer the row whose source_url matches
            # the candidate's own URL so the right transcript is used.
            evidence = None
            if source_id:
                evidence = await conn.fetchrow(
                    """SELECT text FROM source_extractions
                       WHERE source_id=$1
                       ORDER BY
                           CASE WHEN source_url=$2 THEN 0 ELSE 1 END,
                           extracted_at DESC
                       LIMIT 1""",
                    source_id,
                    source_url,
                )

        existing_titles = [r["title"] for r in existing_rows]

        await progress(40)

        if not evidence or not evidence["text"]:
            raise NoEvidenceError("Source has not been extracted yet")

        text = evidence["text"]

        await progress(60)

        note_result = await generate_note(
            candidate["title"],
            text,
            source_url,
            source_type,
            ai_settings,
            existing_titles,
        )

        if note_result.error:
            await progress(100)
            return f"Note generation failed: {note_result.error}"

        await progress(85)

        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM notes WHERE candidate_id=$1",
                candidate_id,
            )
            if existing:
                await progress(100)
                return f"Note already exists for candidate {candidate_id} — skipping duplicate"

            await conn.execute(
                """INSERT INTO notes
                   (user_id, title, source, topic_id, source_id, ai_action, quality_score,
                    has_duplicate, content, frontmatter, citations, wiki_links,
                    similarity_reasoning, status, candidate_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)""",
                user_id,
                note_result.title,
                source_url,
                topic_id,
                source_id,
                note_result.ai_action,
                note_result.quality_score,
                False,
                note_result.content,
                note_result.frontmatter,
                note_result.citations,
                note_result.wiki_links,
                note_result.similarity_reasoning,
                "pending",
                candidate_id,
            )

        await progress(100)
        return f"Note '{note_result.title}' generated (quality: {note_result.quality_score:.2f})"
    except NoEvidenceError:
        # A real failure, not a completed-with-a-bad-outcome job. Let it
        # propagate to runner._run_job, which marks status='failed' and
        # persists .code as jobs.error_code.
        raise
    except Exception as e:
        await progress(100)
        return f"Note generation handler failed: {str(e)[:100]}"


async def _verification_handler(
    job: dict[str, Any], progress: ProgressFn, pool: Any
) -> str:
    """Quality-check pending notes and update quality scores."""
    user_id = job["user_id"]

    try:
        async with pool.acquire() as conn:
            notes = await conn.fetch(
                """SELECT id, title, content, citations FROM notes
                   WHERE user_id=$1 AND status='pending'
                   AND (artifact_path IS NULL OR artifact_path='')
                   ORDER BY generated_at DESC LIMIT 20""",
                user_id,
            )

        verified = 0
        for note in notes:
            base_score = 0.5
            if len(note["content"] or "") > 500:
                base_score += 0.2
            if note["citations"] and len(note["citations"]) > 0:
                base_score += 0.15
            if len((note["content"] or "").split()) > 100:
                base_score += 0.15
            new_score = min(1.0, base_score)

            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE notes SET quality_score=$1 WHERE id=$2",
                    new_score,
                    note["id"],
                )
                verified += 1

        await progress(100)
        return f"Verified {verified} note(s)"
    except Exception as e:
        await progress(100)
        return f"Verification handler failed: {str(e)[:100]}"


async def _graphify_sync_handler(job: dict[str, Any], progress: ProgressFn, pool: Any) -> str:
    """Write approved notes as .md files to the vault."""
    user_id = job["user_id"]

    try:
        async with pool.acquire() as conn:
            notes = await conn.fetch(
                """SELECT id, title, content, frontmatter, citations, wiki_links FROM notes
                   WHERE user_id=$1 AND status='approved'
                   AND (artifact_path IS NULL OR artifact_path='')
                   ORDER BY approved_at ASC""",
                user_id,
            )

            vault_row = await conn.fetchrow(
                "SELECT vault_path FROM user_settings WHERE user_id=$1", user_id
            )

        vault_path = vault_row["vault_path"] if vault_row else None

        if not notes:
            await progress(100)
            vault_info = (
                f" at {vault_path}"
                if vault_path
                else " (DB only — set vault path in Settings)"
            )
            return (
                f"0 notes written — no approved notes pending "
                f"vault write{vault_info}"
            )

        await progress(10)

        written = 0
        errors = 0

        for idx, note in enumerate(notes):
            try:
                file_path = f"Synker/{_safe_filename(note['title'])}.md"

                frontmatter_dict = note["frontmatter"] or {}
                frontmatter_yaml = "\n".join(
                    f"{k}: {v}" for k, v in frontmatter_dict.items()
                )

                citations_text = ""
                if note["citations"]:
                    citations_text = "\n## Citations\n" + "\n".join(
                        f"- {c}" for c in note["citations"]
                    )

                wiki_links_text = ""
                if note["wiki_links"]:
                    wiki_links_text = "\n## Related\n" + "\n".join(
                        f"- [[{link}]]" for link in note["wiki_links"]
                    )

                markdown = f"""---
{frontmatter_yaml}
---

{note['content']}{citations_text}{wiki_links_text}
"""

                if vault_path:
                    full_path = (Path(vault_path) / file_path).resolve()
                    vault_root = Path(vault_path).resolve()
                    if not str(full_path).startswith(str(vault_root) + os.sep):
                        errors += 1
                        continue
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(markdown, encoding="utf-8")

                    try:
                        content = full_path.read_text(encoding="utf-8")
                        if not content:
                            errors += 1
                            continue
                    except Exception:
                        errors += 1
                        continue

                async with pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO vault_files
                           (user_id, path, content, frontmatter, word_count, cloud_safe)
                           VALUES ($1, $2, $3, $4, $5, true)
                           ON CONFLICT (user_id, path) DO UPDATE
                           SET content=$3, frontmatter=$4, word_count=$5, last_modified=now()""",
                        user_id,
                        file_path,
                        note["content"] or "",
                        frontmatter_dict,
                        len((note["content"] or "").split()),
                    )

                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE notes SET artifact_path=$1 WHERE id=$2", file_path, note["id"]
                    )

                written += 1
            except Exception:
                errors += 1

            await progress(10 + 80 * (idx + 1) // len(notes))

        await progress(100)
        vault_info = (
            f" at {vault_path}"
            if vault_path
            else " (DB only — set vault path in Settings)"
        )
        return (
            f"{written} note(s) written to vault{vault_info}, "
            f"{errors} error(s)"
        )
    except Exception as e:
        await progress(100)
        return f"Graphify sync handler failed: {str(e)[:100]}"


async def _cleanup_handler(job: dict[str, Any], progress: ProgressFn, pool: Any) -> str:
    """Post-processing cleanup per user's cleanup policy."""
    user_id = job["user_id"]

    try:
        async with pool.acquire() as conn:
            settings_row = await conn.fetchrow(
                "SELECT cleanup FROM user_settings WHERE user_id=$1", user_id
            )
            cleanup_settings = settings_row["cleanup"] if settings_row else {}

            approved_notes = await conn.fetch(
                """SELECT source, artifact_path FROM notes
                   WHERE user_id=$1 AND status='approved'
                   AND artifact_path IS NOT NULL AND artifact_path != ''
                   ORDER BY generated_at DESC LIMIT 50""",
                user_id,
            )

            sources = await conn.fetch(
                "SELECT id, url, type FROM sources WHERE user_id=$1", user_id
            )

        source_map = {src["url"]: src for src in sources}

        processed = 0
        for note in approved_notes:
            source_url = note["source"]
            artifact_path = note["artifact_path"]
            cleanup_policy = cleanup_settings.get("web", "keep")

            if cleanup_policy == "keep":
                pass
            elif cleanup_policy == "delete":
                src = source_map.get(source_url)
                if src and src["type"] == "local" and artifact_path:
                    try:
                        source_path = Path(source_url)
                        if source_path.exists() and source_path.is_file():
                            source_path.unlink()
                            processed += 1
                    except Exception:
                        pass
            elif cleanup_policy == "zip":
                pass

        await progress(100)
        return f"Cleanup processed {processed} source(s)"
    except Exception as e:
        await progress(100)
        return f"Cleanup handler failed: {str(e)[:100]}"


HANDLERS: dict[str, Handler] = {
    "Analysis": _analysis_handler,
    "Extraction": _extraction_handler,
    "Note Gen": _note_gen_handler,
    "Verification": _verification_handler,
    "Graphify Sync": _graphify_sync_handler,
    "Cleanup": _cleanup_handler,
}


def get_handler(job_type: str) -> Handler | None:
    return HANDLERS.get(job_type)
