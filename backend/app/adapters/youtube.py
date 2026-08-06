"""YouTube source adapter.

Fetches a video transcript via youtube-transcript-api and metadata via the
YouTube oEmbed endpoint (no API key required).
"""
from __future__ import annotations

import re

import httpx

from app.adapters.base import ExtractedContent, SourceAdapter

_OEMBED = "https://www.youtube.com/oembed?url={url}&format=json"
_YT_ID = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"
)


def _extract_video_id(url: str) -> str | None:
    m = _YT_ID.search(url)
    return m.group(1) if m else None


async def extract(url: str) -> ExtractedContent:
    """Fetch transcript and metadata from a YouTube video URL."""
    video_id = _extract_video_id(url)
    if not video_id:
        return ExtractedContent(
            text="",
            title="",
            source_url=url,
            source_type="youtube",
            error=f"Cannot extract video ID from URL: {url}",
        )

    try:
        from youtube_transcript_api import (
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
    except ImportError:
        return ExtractedContent(
            text="",
            title="",
            source_url=url,
            source_type="youtube",
            error="youtube-transcript-api is not installed",
        )

    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id)  # type: ignore[attr-defined]
    except (NoTranscriptFound, TranscriptsDisabled):
        return ExtractedContent(
            text="",
            title="",
            source_url=url,
            source_type="youtube",
            error=f"No transcript available for {video_id}",
        )
    except Exception as exc:
        return ExtractedContent(
            text="",
            title="",
            source_url=url,
            source_type="youtube",
            error=f"Error fetching transcript: {exc}",
        )

    text = " ".join(e["text"] for e in entries)
    timestamps = [
        {"seconds": int(e["start"]), "text": e["text"]} for e in entries
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(_OEMBED.format(url=url))
            resp.raise_for_status()
            meta = resp.json()
        except httpx.HTTPError:
            meta = {}

    title = meta.get("title") or f"YouTube video {video_id}"
    author = meta.get("author_name")

    return ExtractedContent(
        source_url=url,
        text=text,
        title=title,
        source_type="youtube",
        word_count=len(text.split()),
        author=author,
        timestamps=timestamps,
    )


class YoutubeAdapter(SourceAdapter):
    """Extract transcript and metadata from a YouTube video URL."""

    async def extract(self, url: str) -> ExtractedContent:
        """Fetch transcript and metadata from a YouTube video."""
        return await extract(url)
