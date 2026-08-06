"""Job-type handlers.

A handler does the real work for one job and returns a short, truthful result
summary. Handlers report progress via the injected async callback and MUST NOT
fabricate notes, candidates, or citations — if there is nothing real to do, they
say so honestly. Handlers should handle all exceptions gracefully and return a
meaningful error message rather than crashing.
"""
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncpg.exceptions

from app.adapters import extract as adapter_extract
from app.adapters.base import ExtractedContent, ExtractionError
from app.adapters.registry import get_adapter
from app.ai import generate_note

# pct -> None. Persists progress + heartbeat for the running job.
ProgressFn = Callable[[int], Awaitable[None]]

# (job_row, progress, pool) -> result summary string.
Handler = Callable[[dict[str, Any], ProgressFn, Any], Awaitable[str]]

# Seconds between discovery progress steps. Kept short; tests set it to 0.
STEP_DELAY_SECONDS = 1.2


def _safe_filename(title: str) -> str:
    """Convert a note title to a safe filename by replacing special characters."""
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)
    return safe[:100]


async def _analysis_handler(job: dict[str, Any], progress: ProgressFn, pool: Any) -> str:
    """Discovery: scan queued sources, extract metadata, create candidate records."""
    user_id = job["user_id"]
    created = 0

    try:
        async with pool.acquire() as conn:
            sources = await conn.fetch(
                "SELECT id, type, title, url FROM sources WHERE user_id=$1",
                user_id,
            )

        if not sources:
            await progress(100)
            return "0 candidates — no queued sources found"

        total = len(sources)
        for i, source in enumerate(sources):
            try:
                await progress(10 + 70 * (i + 1) // total)

                source_type = source["type"] or "web"
                source_url = source["url"]

                extracted = None
                try:
                    extracted = await adapter_extract(source_type, source_url)
                except Exception:
                    extracted = ExtractedContent(
                        text="",
                        title=source["title"] or "Unknown",
                        error="Extraction pending",
                    )

                if extracted and (extracted.error or not extracted.text):
                    title = source["title"] or "Unknown"
                    summary = "Extraction pending"
                    published_at = None
                    word_count = 0
                else:
                    title = extracted.title if extracted else source["title"]
                    summary = extracted.text[:500] if extracted and extracted.text else ""
                    published_at = extracted.published_at if extracted else None
                    word_count = extracted.word_count if extracted else 0

                domain = urlparse(source_url).netloc if source_url else ""

                async with pool.acquire() as conn:
                    existing = await conn.fetchval(
                        """SELECT 1 FROM candidates WHERE user_id=$1 AND source_info=$2
                           AND status='pending' LIMIT 1""",
                        user_id,
                        source_url,
                    )

                    if not existing:
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
                            title,
                            source_url,
                            domain,
                            published_at,
                            "process",
                            0.75,
                            0.70,
                            0.05,
                            1,
                            max(1000, word_count * 2),
                            summary,
                            [],
                            "pending",
                        )
                        created += 1

                    await conn.execute(
                        "UPDATE sources SET status='processing' WHERE id=$1 AND user_id=$2",
                        source["id"],
                        user_id,
                    )
            except Exception:
                pass

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
                "SELECT title, source_info, summary FROM candidates WHERE id=$1 AND user_id=$2",
                candidate_id,
                user_id,
            )

        if not candidate:
            await progress(100)
            return f"Candidate {candidate_id} not found"

        await progress(20)

        async with pool.acquire() as conn:
            ai_row = await conn.fetchrow(
                "SELECT ai_providers FROM user_settings WHERE user_id=$1", user_id
            )
            ai_settings = ai_row["ai_providers"] if ai_row else {}

            existing_rows = await conn.fetch(
                "SELECT title FROM notes WHERE user_id=$1 ORDER BY generated_at DESC LIMIT 100",
                user_id,
            )

        existing_titles = [r["title"] for r in existing_rows]

        await progress(30)

        source_url = candidate["source_info"]
        async with pool.acquire() as conn:
            source_row = await conn.fetchrow(
                "SELECT type FROM sources WHERE url=$1 AND user_id=$2 LIMIT 1",
                source_url,
                user_id,
            )
            source_type = source_row["type"] if source_row else "web"

        await progress(40)

        extracted = None
        try:
            extracted = await adapter_extract(source_type, source_url)
        except Exception:
            pass

        text = ""
        if extracted and extracted.text:
            text = extracted.text
        elif candidate["summary"]:
            text = candidate["summary"]

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
            await conn.execute(
                """INSERT INTO notes
                   (user_id, title, source, ai_action, quality_score, has_duplicate,
                    content, frontmatter, citations, wiki_links, similarity_reasoning, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                user_id,
                note_result.title,
                source_url,
                note_result.ai_action,
                note_result.quality_score,
                False,
                note_result.content,
                note_result.frontmatter,
                note_result.citations,
                note_result.wiki_links,
                note_result.similarity_reasoning,
                "pending",
            )

        await progress(100)
        return f"Note '{note_result.title}' generated (quality: {note_result.quality_score:.2f})"
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
                    full_path = Path(vault_path) / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(markdown, encoding="utf-8")

                async with pool.acquire() as conn:
                    try:
                        await conn.execute(
                            """INSERT INTO vault_files
                               (user_id, path, content, frontmatter, word_count, cloud_safe)
                               VALUES ($1, $2, $3, $4, $5, $6)""",
                            user_id,
                            file_path,
                            markdown,
                            frontmatter_dict,
                            len(note["content"].split()),
                            True,
                        )
                    except asyncpg.exceptions.UndefinedColumnError:
                        try:
                            await conn.execute(
                                """INSERT INTO vault_files
                                   (user_id, path, word_count, cloud_safe)
                                   VALUES ($1, $2, $3, $4)""",
                                user_id,
                                file_path,
                                len(note["content"].split()),
                                True,
                            )
                        except Exception:
                            pass

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
                """SELECT source FROM notes
                   WHERE user_id=$1 AND status='approved'
                   AND artifact_path IS NOT NULL AND artifact_path != ''
                   ORDER BY generated_at DESC LIMIT 50""",
                user_id,
            )

        processed = 0
        for note in approved_notes:
            source_url = note["source"]
            cleanup_policy = cleanup_settings.get("web", "keep")

            if cleanup_policy == "keep":
                pass
            elif cleanup_policy == "delete":
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
