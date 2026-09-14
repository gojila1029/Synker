"""YouTube channel/playlist discovery via yt-dlp.

A source classified as source_scope='discovery_provider' (see
app/adapters/classify.py -- a channel, playlist, or search-result URL
with no resolvable video id) needs to be turned into a list of individual
video URLs before the existing per-video pipeline (app/adapters/youtube.py)
can extract each one. yt-dlp reads public channel/playlist metadata with
no login and no API key, so this stays free and credential-free.

Search-result pages (/results?search_query=) are explicitly unsupported --
enumerating arbitrary search results requires the paid YouTube Data API,
which is out of scope here. Reported as unsupported_reason rather than
returning an indistinguishable empty "channel has no videos" result.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

_SEARCH_URL = re.compile(r"/results\b.*[?&]search_query=")

# Kept small: this discovers new items every scheduled Analysis run, not
# a one-time full backfill. Later runs pick up further videos once earlier
# ones are no longer "pending" (see the broadened dedup check in handlers.py).
DEFAULT_LIMIT = 25


@dataclass
class DiscoveredVideo:
    url: str
    title: str


@dataclass
class DiscoveryResult:
    videos: list[DiscoveredVideo] = field(default_factory=list)
    unsupported_reason: str | None = None
    error: str | None = None


def _is_search_url(url: str) -> bool:
    return bool(_SEARCH_URL.search(url))


def _video_url(entry: dict) -> str:
    url = entry.get("url")
    if url:
        return url
    return f"https://www.youtube.com/watch?v={entry.get('id')}"


def _run_yt_dlp(url: str, limit: int) -> DiscoveryResult:
    try:
        import yt_dlp
    except ImportError:
        return DiscoveryResult(error="yt-dlp is not installed")

    opts = {
        "extract_flat": True,
        "playlistend": limit,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # yt_dlp raises its own DownloadError subclasses
        return DiscoveryResult(error=f"yt-dlp failed for {url}: {exc}")

    entries = (info or {}).get("entries") or []
    videos = [
        DiscoveredVideo(url=_video_url(entry), title=entry.get("title") or "Untitled video")
        for entry in entries
        if entry
    ]
    return DiscoveryResult(videos=videos)


async def discover_channel_videos(url: str, limit: int = DEFAULT_LIMIT) -> DiscoveryResult:
    """Enumerate up to `limit` videos from a YouTube channel or playlist URL.

    yt-dlp is synchronous, so the real work runs in a thread and never blocks
    the event loop -- matching how the rest of this codebase stays async."""
    if _is_search_url(url):
        return DiscoveryResult(
            unsupported_reason=(
                "Search result pages cannot be enumerated without the "
                "YouTube Data API"
            )
        )

    return await asyncio.to_thread(_run_yt_dlp, url, limit)
