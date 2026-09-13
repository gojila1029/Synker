"""Tests for the YouTube source adapter."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.youtube import _extract_video_id, extract


def test_extract_video_id_watch_url():
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_youtu_be():
    assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_embed():
    assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_shorts():
    assert _extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_invalid():
    assert _extract_video_id("https://example.com/not-youtube") is None


def test_extract_video_id_bare_homepage_returns_none():
    """Regression (Stage 5 item 2): the bare YouTube homepage must not be
    mistaken for a video URL — there is no 11-char video id to extract."""
    assert _extract_video_id("https://www.youtube.com/") is None
    assert _extract_video_id("https://www.youtube.com") is None


@pytest.mark.asyncio
async def test_happy_path():
    transcript = [
        {"start": 0.0, "duration": 2.0, "text": "Hello world"},
        {"start": 2.0, "duration": 2.0, "text": "this is a test"},
    ]
    oembed = {"title": "Test Video", "author_name": "Test Channel"}

    mock_response = MagicMock()
    mock_response.json.return_value = oembed
    mock_response.raise_for_status.return_value = None

    with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls, patch(
        "httpx.AsyncClient"
    ) as mock_client_cls:
        mock_api_cls.get_transcript = MagicMock(return_value=transcript)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.title == "Test Video"
    assert result.author == "Test Channel"
    assert "Hello world" in result.text
    assert result.timestamps[0] == {"seconds": 0, "text": "Hello world"}
    assert result.source_type == "youtube"
    assert result.error is None


@pytest.mark.asyncio
async def test_no_transcript():
    from youtube_transcript_api import NoTranscriptFound

    with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls, patch(
        "httpx.AsyncClient"
    ):
        mock_api_cls.get_transcript.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", [], []
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result.error is not None
        assert "No transcript" in result.error


@pytest.mark.asyncio
async def test_invalid_url():
    result = await extract("https://example.com/not-a-video")
    assert result.error is not None
    assert "Cannot extract video ID" in result.error


@pytest.mark.asyncio
async def test_bare_homepage_returns_error_not_content():
    """Regression (Stage 5 item 2): a homepage URL must produce an explicit
    error, never a fabricated ExtractedContent with real-looking text/word
    count (CLAUDE.md rule 18/21: no valid Evidence -> no Knowledge Note)."""
    result = await extract("https://www.youtube.com/")
    assert result.error is not None
    assert "Cannot extract video ID" in result.error
    assert result.text == ""
    assert result.word_count == 0


@pytest.mark.asyncio
async def test_module_not_installed():
    with patch.dict(sys.modules, {"youtube_transcript_api": None}):
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result.error is not None
        assert "youtube-transcript-api is not installed" in result.error
