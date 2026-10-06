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
import time

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
        t0 = time.monotonic()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            elapsed = time.monotonic() - t0
            _log.info(
                "Strategy 2 (yt-dlp auto-subs) failed for %s after %.2fs: %s",
                video_id,
                elapsed,
                exc,
            )
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


async def _run_supadata(video_id: str, supadata_api_key: str) -> str | None:
    """Call Supadata API to transcribe a YouTube video.

    For videos ≤20 min: returns transcript immediately.
    For videos >20 min: returns a jobId; poll status endpoint every 5s,
    up to 12 times (60s timeout).

    Returns transcript text, or None on any error except SUPADATA_CREDIT_EXHAUSTED (which raises).
    """
    if not supadata_api_key:
        return None

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    params = {"url": video_url, "lang": "en", "text": "true"}

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Initial request — Supadata API uses GET + query params
            resp = await client.get(
                "https://api.supadata.ai/v1/youtube/transcript",
                params=params,
                headers={"x-api-key": supadata_api_key},
            )

            if resp.status_code == 402:
                raise Exception("SUPADATA_CREDIT_EXHAUSTED")

            if resp.status_code >= 400:
                elapsed = time.monotonic() - t0
                _log.info(
                    "Strategy 1.5 (Supadata) failed for %s after %.2fs (HTTP %d)",
                    video_id,
                    elapsed,
                    resp.status_code,
                )
                return None

            data = resp.json()

            # Check for direct transcript
            if "content" in data and data.get("content"):
                lang = data.get("lang", "unknown")
                _log.debug(
                    "Strategy 1.5 (Supadata) returned transcript immediately for %s (lang=%s)",
                    video_id,
                    lang,
                )
                return str(data["content"])

            # Check for jobId (polling required)
            job_id = data.get("jobId")
            if not job_id:
                # Empty content or no jobId
                if data.get("content") == "":
                    _log.debug("Strategy 1.5 (Supadata) returned empty content for %s", video_id)
                return None

            # Poll status endpoint
            _log.debug("Strategy 1.5 (Supadata) polling jobId %s for %s", job_id, video_id)
            for poll_round in range(1, 13):
                await asyncio.sleep(5)
                poll_resp = await client.get(
                    "https://api.supadata.ai/v1/youtube/transcript",
                    params={"jobId": job_id},
                    headers={"x-api-key": supadata_api_key},
                )

                if poll_resp.status_code >= 400:
                    elapsed = time.monotonic() - t0
                    _log.info(
                        "Strategy 1.5 (Supadata) polling failed for %s (job %s) "
                        "at round %d after %.2fs: HTTP %d",
                        video_id,
                        job_id,
                        poll_round,
                        elapsed,
                        poll_resp.status_code,
                    )
                    return None

                poll_data = poll_resp.json()
                status = poll_data.get("status", "unknown")

                elapsed = time.monotonic() - t0
                _log.debug(
                    "Strategy 1.5 (Supadata) poll round %d of 12 for %s (job %s): "
                    "status=%s, elapsed=%.2fs",
                    poll_round,
                    video_id,
                    job_id,
                    status,
                    elapsed,
                )

                if status == "completed":
                    content = poll_data.get("content")
                    if content:
                        lang = poll_data.get("lang", "unknown")
                        _log.info(
                            "Strategy 1.5 (Supadata) completed for %s (job %s) "
                            "at round %d: lang=%s",
                            video_id,
                            job_id,
                            poll_round,
                            lang,
                        )
                        return str(content)
                    else:
                        _log.warning(
                            "Strategy 1.5 (Supadata) completed but no content for %s (job %s)",
                            video_id,
                            job_id,
                        )
                        return None

                if status == "failed":
                    _log.warning(
                        "Strategy 1.5 (Supadata) failed for %s (job %s) at round %d",
                        video_id,
                        job_id,
                        poll_round,
                    )
                    return None

            # Timeout after 12 polls
            elapsed = time.monotonic() - t0
            _log.warning(
                "Strategy 1.5 (Supadata) polling timeout for %s (job %s) after %.2fs (12 polls)",
                video_id,
                job_id,
                elapsed,
            )
            return None

    except Exception as exc:
        exc_str = str(exc)
        if "SUPADATA_CREDIT_EXHAUSTED" in exc_str:
            raise
        elapsed = time.monotonic() - t0
        _log.info(
            "Strategy 1.5 (Supadata) exception for %s after %.2fs: %s",
            video_id,
            elapsed,
            exc,
        )
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
            _log.info("Strategy 3 (pytubefix audio_download) failed for %s: %s: %s",
                         video_id, type(exc).__name__, exc)
            return None

        audio_files = [f for f in os.listdir(tmpdir) if not f.startswith(".")]
        if not audio_files:
            _log.warning("No audio files extracted for %s (Strategy 3)", video_id)
            return None
        audio_path = os.path.join(tmpdir, audio_files[0])

        try:
            from groq import Groq  # type: ignore[import-untyped, unused-ignore]

            client = Groq(api_key=groq_api_key)
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3-turbo",
                    response_format="text",
                )
            return str(result) if result else None
        except Exception as exc:
            _log.info("Strategy 3 (transcription) failed for %s: %s: %s",
                         video_id, type(exc).__name__, exc)
            return None


async def _fetch_meta(url: str) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(_OEMBED.format(url=url))
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data
            return {}
        except httpx.HTTPError as exc:
            video_id = _extract_video_id(url) or "unknown"
            _log.warning("oEmbed metadata fetch failed for %s: %s", video_id, exc)
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
    timestamps: list[dict[str, object]] = []
    transcript_error: str = ""
    ip_blocked = False

    # ── Strategy 1: youtube-transcript-api (v1.0+) ──────────────────────────
    try:
        from youtube_transcript_api import (  # type: ignore[import-untyped, unused-ignore]
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
        exc_str = str(exc)
        if (
            "IP belonging to a cloud provider" in exc_str
            or "blocking requests from your IP" in exc_str
        ):
            ip_blocked = True
            transcript_error = exc_str
        else:
            transcript_error = f"Transcript fetch error: {exc}"

    # ── Strategy 1.5: Supadata API ────────────────────────────────────────
    if not text and transcript_error:
        from app.core.config import settings

        if settings.supadata_api_key:
            try:
                supadata_text = await _run_supadata(video_id, settings.supadata_api_key)
                if supadata_text:
                    text = supadata_text
                    transcript_error = ""
            except Exception as exc:
                exc_str = str(exc)
                if "SUPADATA_CREDIT_EXHAUSTED" in exc_str:
                    transcript_error = f"Supadata credits exhausted; {transcript_error}"
                    _log.warning("Strategy 1.5 (Supadata) credit exhausted for %s", video_id)
                else:
                    raise

    # ── Strategy 2: yt-dlp auto-generated subtitles ─────────────────────────
    if not text and transcript_error:
        if ip_blocked:
            _log.info("Strategy 1 IP-blocked for %s; attempting Strategy 2 (yt-dlp)", video_id)
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
    title = str(meta.get("title") or "")
    if not title:
        _log.warning("oEmbed returned no title for %s; using fallback", video_id)
        title = f"YouTube video {video_id}"
    author = str(meta.get("author_name") or "")

    if not text:
        if ip_blocked:
            final_error = (
                "YouTube content cannot be extracted on this deployment "
                "(IP-blocked by CDN). Transcript unavailable."
            )
        else:
            final_error = transcript_error or f"No transcript available for {video_id}"
        _log.warning(
            "All extraction strategies failed for %s (ip_blocked=%s): %s",
            video_id,
            ip_blocked,
            final_error,
        )
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
