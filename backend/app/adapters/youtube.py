"""YouTube source adapter.

Transcript extraction strategy (in order):
1. youtube-transcript-api  — fastest, no download, uses official captions
2. yt-dlp auto-subs        — fallback when no official transcript; downloads
                             auto-generated VTT subtitles to a temp dir
3. Error                   — both methods failed; caller sees the reason

Metadata always comes from the YouTube oEmbed endpoint (no API key required).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile

import httpx

from app.adapters.base import ExtractedContent, SourceAdapter

_log = logging.getLogger("synker.youtube")

_OEMBED = "https://www.youtube.com/oembed?url={url}&format=json"
_YT_ID = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"
)
_VTT_TIMESTAMP = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}.*")
_VTT_TAG = re.compile(r"<[^>]+>")
_VTT_CUE_ID = re.compile(r"^\d+$")


def _extract_video_id(url: str) -> str | None:
    m = _YT_ID.search(url)
    return m.group(1) if m else None


def _vtt_to_text(vtt: str) -> str:
    """Convert VTT subtitle content to clean plain text, deduplicating
    rolling-window lines that yt-dlp auto-subs commonly repeat."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if _VTT_TIMESTAMP.match(line) or _VTT_CUE_ID.match(line):
            continue
        clean = _VTT_TAG.sub("", line).strip()
        if clean:
            lines.append(clean)

    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return " ".join(deduped)


def _run_yt_dlp_subs(video_id: str) -> str | None:
    """Download auto-generated subtitles via yt-dlp and return plain text.

    Returns None when yt-dlp is not installed, no auto-subs are available,
    or any other error occurs."""
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError:
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt",
            "subtitleslangs": ["en", "en-US", "ko"],
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            _log.warning("yt-dlp auto-subs download failed for %s: %s", video_id, exc)
            return None

        for fname in os.listdir(tmpdir):
            if fname.endswith(".vtt"):
                try:
                    with open(os.path.join(tmpdir, fname), encoding="utf-8") as f:
                        return _vtt_to_text(f.read())
                except Exception as exc:
                    _log.warning("yt-dlp VTT read/parse failed for %s: %s", video_id, exc)
                    return None
    return None


def _run_pytubefix_audio_stt(video_id: str, groq_api_key: str) -> str | None:
    """Download audio via pytubefix (YouTube InnerTube API) and transcribe with Groq Whisper.

    pytubefix uses YouTube's InnerTube API which is less aggressively blocked on
    datacenter IPs compared to yt-dlp. Returns transcript text, or None on any
    failure (missing deps, network error, Groq error). Never raises."""
    if not groq_api_key:
        _log.debug("Strategy 3 (Groq STT) skipped: GROQ_API_KEY not configured")
        return None
    try:
        from pytubefix import YouTube  # type: ignore[import-untyped]
    except ImportError:
        _log.debug("Strategy 3 skipped: pytubefix not installed")
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            yt = YouTube(url)
            audio_stream = yt.streams.filter(only_audio=True).order_by("abr").last()
            if not audio_stream:
                _log.warning("No audio stream found for %s (Strategy 3)", video_id)
                return None
            audio_stream.download(output_path=tmpdir, filename=f"{video_id}.mp4")
        except Exception as exc:
            _log.warning("pytubefix audio download failed for %s (Strategy 3): %s: %s",
                         video_id, type(exc).__name__, exc)
            return None

        audio_files = [f for f in os.listdir(tmpdir) if not f.startswith(".")]
        if not audio_files:
            _log.warning("No audio files extracted for %s (Strategy 3)", video_id)
            return None
        audio_path = os.path.join(tmpdir, audio_files[0])

        try:
            from groq import Groq  # type: ignore[import-untyped]

            client = Groq(api_key=groq_api_key)
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3-turbo",
                    response_format="text",
                )
            return str(result) if result else None
        except Exception as exc:
            _log.warning("Groq transcription failed for %s (Strategy 3): %s: %s",
                         video_id, type(exc).__name__, exc)
            return None


async def _fetch_meta(url: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(_OEMBED.format(url=url))
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return {}


async def extract(url: str) -> ExtractedContent:
    """Fetch transcript and metadata from a YouTube video URL.

    Tries youtube-transcript-api first; falls back to yt-dlp auto-subs
    when no official transcript is available."""
    video_id = _extract_video_id(url)
    if not video_id:
        return ExtractedContent(
            text="",
            title="",
            source_url=url,
            source_type="youtube",
            error=f"Cannot extract video ID from URL: {url}",
        )

    text: str = ""
    timestamps: list[dict] = []
    transcript_error: str = ""

    # ── Strategy 1: youtube-transcript-api (v1.0+) ──────────────────────────
    try:
        from youtube_transcript_api import (  # type: ignore[import-untyped]
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
        # First try explicit language list to find manual transcripts
        try:
            fetched = YouTubeTranscriptApi().fetch(
                video_id, languages=["en", "en-US", "ko"]
            )
            entries = fetched.to_raw_data()
            text = " ".join(e["text"] for e in entries)
            timestamps = [
                {"seconds": int(e["start"]), "text": e["text"]} for e in entries
            ]
            _log.debug(
                "Strategy 1: Found transcript for %s using explicit language fetch",
                video_id,
            )
        except NoTranscriptFound:
            # No manual transcript; try to find auto-generated transcript
            try:
                transcript_list = YouTubeTranscriptApi().list(video_id)
                _log.debug(
                    "Strategy 1: Available transcripts for %s: %s",
                    video_id,
                    [t.language for t in transcript_list],
                )
                for transcript in transcript_list:
                    if transcript.is_generated:
                        _log.debug(
                            "Strategy 1: Found auto-generated transcript in %s for %s",
                            transcript.language,
                            video_id,
                        )
                        fetched = transcript.fetch()
                        entries = fetched.to_raw_data()
                        text = " ".join(e["text"] for e in entries)
                        timestamps = [
                            {"seconds": int(e["start"]), "text": e["text"]}
                            for e in entries
                        ]
                        break
            except Exception as list_exc:
                _log.warning(
                    "Strategy 1: Failed to list/fetch auto-generated transcripts for %s: %s",
                    video_id,
                    list_exc,
                )

            if not text:
                transcript_error = f"No transcript available for {video_id}"
    except ImportError:
        transcript_error = "youtube-transcript-api is not installed"
    except TranscriptsDisabled:
        transcript_error = f"Transcripts disabled for {video_id}"
    except Exception as exc:
        transcript_error = f"Transcript fetch error: {exc}"

    # ── Strategy 2: yt-dlp auto-generated subtitles ─────────────────────────
    if not text and transcript_error:
        auto_text = await asyncio.to_thread(_run_yt_dlp_subs, video_id)
        if auto_text:
            text = auto_text
            transcript_error = ""

    # ── Strategy 3: Groq Whisper STT (audio download + transcription) ────────
    if not text:
        from app.core.config import settings

        stt_text = await asyncio.to_thread(
            _run_pytubefix_audio_stt, video_id, settings.groq_api_key
        )
        if stt_text:
            text = stt_text
            transcript_error = ""

    meta = await _fetch_meta(url)
    title = meta.get("title") or f"YouTube video {video_id}"
    author = meta.get("author_name")

    if not text:
        final_error = transcript_error or f"No transcript available for {video_id}"
        _log.warning("All extraction strategies failed for %s: %s", video_id, final_error)
        return ExtractedContent(
            text="",
            title=title,
            source_url=url,
            source_type="youtube",
            author=author,
            error=final_error,
        )

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
        return await extract(url)
