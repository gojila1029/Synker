"""YouTube keyword search via yt-dlp.

Searches YouTube for videos matching a query and returns a list of results.
Uses yt-dlp's ytsearch interface without requiring any API key or authentication.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

_YT_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


@dataclass
class SearchResult:
    """A single YouTube search result."""

    video_id: str
    title: str
    url: str
    channel: str | None = None


@dataclass
class YouTubeSearchResult:
    """Result of a YouTube search query."""

    results: list[SearchResult] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None  # NO_RESULTS, SEARCH_UNAVAILABLE


def _run_yt_dlp_search(query: str, limit: int) -> YouTubeSearchResult:
    """Execute yt-dlp search synchronously."""
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError:
        return YouTubeSearchResult(error="yt-dlp is not installed", error_code="SEARCH_UNAVAILABLE")

    search_query = f"ytsearch{limit}:{query}"
    opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
    except Exception as exc:
        return YouTubeSearchResult(
            error=f"yt-dlp search failed: {exc}",
            error_code="SEARCH_UNAVAILABLE",
        )

    entries = (info or {}).get("entries") or []

    if not entries:
        return YouTubeSearchResult(error="No results found", error_code="NO_RESULTS")

    results: list[SearchResult] = []
    for entry in entries:
        if not entry:
            continue

        video_id = entry.get("id")
        title = entry.get("title") or "Untitled"
        channel = entry.get("uploader")

        if video_id and _YT_VIDEO_ID.match(video_id):
            url = f"https://www.youtube.com/watch?v={video_id}"
            results.append(SearchResult(video_id=video_id, title=title, url=url, channel=channel))

    if not results:
        return YouTubeSearchResult(error="No valid videos found", error_code="NO_RESULTS")

    return YouTubeSearchResult(results=results)


async def search_youtube(query: str, limit: int = 10) -> YouTubeSearchResult:
    """Search YouTube for videos matching a query.

    Args:
        query: Search query string
        limit: Maximum number of results (default 10)

    Returns:
        YouTubeSearchResult with results or error details
    """
    return await asyncio.to_thread(_run_yt_dlp_search, query, limit)
