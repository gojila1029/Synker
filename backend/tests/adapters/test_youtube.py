"""Tests for the YouTube source adapter."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.youtube import _extract_video_id, _run_pytubefix_audio_stt, extract


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
    """youtube-transcript-api v1.0+: instance method fetch() → to_raw_data()."""
    raw_transcript = [
        {"start": 0.0, "duration": 2.0, "text": "Hello world"},
        {"start": 2.0, "duration": 2.0, "text": "this is a test"},
    ]
    oembed = {"title": "Test Video", "author_name": "Test Channel"}

    mock_response = MagicMock()
    mock_response.json.return_value = oembed
    mock_response.raise_for_status.return_value = None

    mock_fetched = MagicMock()
    mock_fetched.to_raw_data.return_value = raw_transcript

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_api_cls.return_value.fetch = MagicMock(return_value=mock_fetched)

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
    """When all four strategies fail, error is returned."""
    from youtube_transcript_api import NoTranscriptFound

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch(
            "app.adapters.youtube._run_supadata",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test", "author_name": None},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result.error is not None
        assert "No transcript" in result.error


@pytest.mark.asyncio
async def test_no_transcript_yt_dlp_fallback():
    """yt-dlp auto-subs succeed when transcript-api has no transcript."""
    from youtube_transcript_api import NoTranscriptFound

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch(
            "app.adapters.youtube._run_supadata",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.adapters.youtube._run_yt_dlp_subs",
            return_value="Auto-generated subtitle text here",
        ),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test Video", "author_name": "Channel"},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result.error is None
        assert "Auto-generated" in result.text
        assert result.title == "Test Video"


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
    with (
        patch.dict(sys.modules, {"youtube_transcript_api": None}),
        patch(
            "app.adapters.youtube._run_supadata",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test", "author_name": None},
        ),
    ):
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result.error is not None
        assert "youtube-transcript-api is not installed" in result.error


# ── TDD: _run_yt_dlp_audio_stt (Groq Whisper STT — Strategy 3) ───────────────


def _fake_pytubefix(monkeypatch, *, create_file: bool = True, raise_exc=None):
    """Fake pytubefix.YouTube for Strategy 3 tests."""
    class _Stream:
        def download(self, output_path, filename):
            if raise_exc:
                raise raise_exc
            if create_file:
                open(os.path.join(output_path, filename), "w").close()

    class _Streams:
        def filter(self, only_audio):
            return self

        def order_by(self, abr):
            return self

        def last(self):
            if raise_exc and isinstance(raise_exc, type) and raise_exc.__name__ == "NoStream":
                return None
            return _Stream()

    class _YouTube:
        def __init__(self, url):
            self.url = url
            if raise_exc and not isinstance(raise_exc, type):
                raise raise_exc
            self.streams = _Streams()

    monkeypatch.setitem(
        sys.modules,
        "pytubefix",
        type("M", (), {"YouTube": staticmethod(lambda url: _YouTube(url))})(),
    )


def _fake_groq(monkeypatch, *, text: str = "Groq transcript", raise_exc=None):
    class _T:
        def create(self, **kw):
            if raise_exc:
                raise raise_exc
            return text

    class _A:
        transcriptions = _T()

    class _C:
        def __init__(self, api_key=None):
            self.audio = _A()

    monkeypatch.setitem(
        sys.modules,
        "groq",
        type("M", (), {"Groq": staticmethod(lambda api_key=None: _C(api_key))})(),
    )


import os  # noqa: E402 — needed by helpers above

from app.adapters.youtube import (  # noqa: E402
    YoutubeAdapter,
    _fetch_meta,
    _run_yt_dlp_subs,
    _vtt_to_text,
)


def test_stt_returns_transcript_on_success(monkeypatch):
    _fake_pytubefix(monkeypatch, create_file=True)
    _fake_groq(monkeypatch, text="Hello STT world")
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") == "Hello STT world"


def test_stt_returns_none_for_empty_api_key(monkeypatch):
    _fake_pytubefix(monkeypatch, create_file=True)
    _fake_groq(monkeypatch)
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "") is None


def test_stt_returns_none_when_pytubefix_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytubefix", None)
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None


def test_stt_logs_debug_when_pytubefix_missing(monkeypatch, caplog):
    """Strategy 3 logs debug when pytubefix is not installed."""
    import logging
    monkeypatch.setitem(sys.modules, "pytubefix", None)
    caplog.set_level(logging.DEBUG, logger="synker.youtube")
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None
    assert "pytubefix not installed" in caplog.text


def test_stt_returns_none_when_download_raises(monkeypatch):
    _fake_pytubefix(monkeypatch, create_file=False, raise_exc=RuntimeError("net"))
    _fake_groq(monkeypatch)
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None


def test_stt_logs_pytubefix_download_failure(monkeypatch, caplog):
    """Strategy 3 logs when pytubefix download fails."""
    _fake_pytubefix(monkeypatch, create_file=False, raise_exc=RuntimeError("IP blocked"))
    _fake_groq(monkeypatch)
    import logging
    caplog.set_level(logging.INFO, logger="synker.youtube")
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None
    assert "IP blocked" in caplog.text or "audio_download" in caplog.text


def test_stt_returns_none_when_no_file_created(monkeypatch):
    _fake_pytubefix(monkeypatch, create_file=False)
    _fake_groq(monkeypatch)
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None


def test_stt_returns_none_when_groq_missing(monkeypatch):
    _fake_pytubefix(monkeypatch, create_file=True)
    monkeypatch.setitem(sys.modules, "groq", None)
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None


def test_stt_returns_none_when_groq_api_raises(monkeypatch):
    _fake_pytubefix(monkeypatch, create_file=True)
    _fake_groq(monkeypatch, raise_exc=RuntimeError("quota"))
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None


# ── TDD: _vtt_to_text ─────────────────────────────────────────────────────────


def test_vtt_to_text_basic():
    """VTT cues are joined as space-separated plain text."""
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\nHello world\n\n"
        "00:00:02.000 --> 00:00:04.000\nThis is a test\n"
    )
    assert _vtt_to_text(vtt) == "Hello world This is a test"


def test_vtt_to_text_strips_html_tags():
    """HTML-like tags embedded in VTT cues are stripped from output."""
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n<c.colorE5E5E5>Hello</c> world\n"
    result = _vtt_to_text(vtt)
    assert "Hello world" in result
    assert "<" not in result


def test_vtt_to_text_deduplicates_rolling_lines():
    """Consecutive duplicate lines (yt-dlp rolling window) are deduplicated to one."""
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\nHello world\n\n"
        "00:00:01.000 --> 00:00:03.000\nHello world\n\n"
        "00:00:02.000 --> 00:00:04.000\nnew line\n"
    )
    result = _vtt_to_text(vtt)
    assert result.count("Hello world") == 1
    assert "new line" in result


def test_vtt_to_text_empty_input():
    """Empty or header-only VTT returns an empty string."""
    assert _vtt_to_text("") == ""
    assert _vtt_to_text("WEBVTT\n\n") == ""


# ── TDD: _run_yt_dlp_subs ─────────────────────────────────────────────────────


def _fake_yt_dlp_subs(monkeypatch, *, vtt_content: str | None, raise_exc=None):
    """Fake yt_dlp for _run_yt_dlp_subs: optionally writes a .vtt file."""
    _VTT_CONTENT = vtt_content

    class _YDL:
        def __init__(self, opts):
            self._opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            if raise_exc:
                raise raise_exc
            if _VTT_CONTENT is not None:
                tmpdir = os.path.dirname(self._opts["outtmpl"])
                vtt_path = os.path.join(tmpdir, "dQw4w9WgXcQ.en.vtt")
                with open(vtt_path, "w", encoding="utf-8") as f:
                    f.write(_VTT_CONTENT)

    monkeypatch.setitem(
        sys.modules,
        "yt_dlp",
        type("M", (), {"YoutubeDL": staticmethod(lambda opts: _YDL(opts))})(),
    )


def test_run_yt_dlp_subs_returns_text_on_success(monkeypatch):
    _fake_yt_dlp_subs(
        monkeypatch,
        vtt_content="WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nSub text\n",
    )
    result = _run_yt_dlp_subs("dQw4w9WgXcQ")
    assert result == "Sub text"


def test_run_yt_dlp_subs_returns_none_when_yt_dlp_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    assert _run_yt_dlp_subs("dQw4w9WgXcQ") is None


def test_run_yt_dlp_subs_returns_none_when_download_raises(monkeypatch):
    _fake_yt_dlp_subs(monkeypatch, vtt_content=None, raise_exc=RuntimeError("network"))
    assert _run_yt_dlp_subs("dQw4w9WgXcQ") is None


def test_run_yt_dlp_subs_returns_none_when_no_vtt_created(monkeypatch):
    _fake_yt_dlp_subs(monkeypatch, vtt_content=None)
    assert _run_yt_dlp_subs("dQw4w9WgXcQ") is None


def test_run_yt_dlp_subs_logs_download_failure(monkeypatch, caplog):
    """Strategy 2 logs the exception when download fails, rather than silently swallowing it."""
    _fake_yt_dlp_subs(monkeypatch, vtt_content=None, raise_exc=RuntimeError("IP blocked"))
    import logging
    caplog.set_level(logging.INFO, logger="synker.youtube")
    assert _run_yt_dlp_subs("dQw4w9WgXcQ") is None
    assert "IP blocked" in caplog.text or "Strategy 2" in caplog.text


def test_run_pytubefix_audio_stt_logs_missing_api_key(monkeypatch, caplog):
    """Strategy 3 logs when GROQ_API_KEY is missing (debug level)."""
    import logging
    caplog.set_level(logging.DEBUG, logger="synker.youtube")
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "") is None
    assert "GROQ_API_KEY not configured" in caplog.text


def test_run_pytubefix_audio_stt_logs_groq_failure(monkeypatch, caplog):
    """Strategy 3 logs when Groq transcription fails."""
    _fake_pytubefix(monkeypatch, create_file=True)
    _fake_groq(monkeypatch, raise_exc=RuntimeError("quota exceeded"))
    import logging
    caplog.set_level(logging.INFO, logger="synker.youtube")
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None
    assert "quota exceeded" in caplog.text or "transcription" in caplog.text


def test_stt_no_audio_stream_available(monkeypatch, caplog):
    """When pytubefix finds no audio stream, Strategy 3 returns None with a warning log."""
    class _NoStream:
        def filter(self, only_audio):
            return self
        def order_by(self, abr):
            return self
        def last(self):
            return None

    class _YouTube:
        def __init__(self, url):
            self.streams = _NoStream()

    monkeypatch.setitem(
        sys.modules,
        "pytubefix",
        type("M", (), {"YouTube": staticmethod(lambda url: _YouTube(url))})(),
    )
    _fake_groq(monkeypatch)
    import logging
    caplog.set_level(logging.WARNING, logger="synker.youtube")
    assert _run_pytubefix_audio_stt("dQw4w9WgXcQ", "key") is None
    assert "No audio stream found" in caplog.text


# ── TDD: _fetch_meta error path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_meta_http_error_returns_empty_dict():
    """An HTTP error from the oEmbed endpoint returns {} so callers get a safe default."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("connection error")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _fetch_meta("https://www.youtube.com/watch?v=test")

    assert result == {}


# ── TDD: Strategy 1 generic exception → Strategy 3 fallback ──────────────────


@pytest.mark.asyncio
async def test_strategy1_tries_auto_generated_when_manual_not_found():
    """Strategy 1 explicitly tries to find auto-generated transcripts
    when no manual transcript is found."""
    from youtube_transcript_api import NoTranscriptFound

    # Mock transcript list with one auto-generated transcript
    mock_transcript_entry = MagicMock()
    mock_transcript_entry.is_generated = True
    mock_transcript_entry.language = "en (auto-generated)"
    mock_transcript_entry.fetch.return_value.to_raw_data.return_value = [
        {"start": 0.0, "duration": 2.0, "text": "Auto generated content"}
    ]

    mock_transcript_list = [mock_transcript_entry]

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test Video", "author_name": "Test Channel"},
        ),
    ):
        api_instance = MagicMock()
        # First call to fetch() with explicit languages raises NoTranscriptFound
        api_instance.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en", "en-US", "ko"), MagicMock()
        )
        # Second call to list() returns auto-generated transcript
        api_instance.list.return_value = mock_transcript_list
        mock_api_cls.return_value = api_instance

        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is None
    assert "Auto generated content" in result.text
    assert result.title == "Test Video"


@pytest.mark.asyncio
async def test_strategy1_generic_exception_falls_through_to_strategy3():
    """An unexpected exception from the transcript API (not NoTranscriptFound)
    is caught and Strategy 3 (Groq STT) is invoked as the final fallback."""
    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch(
            "app.adapters.youtube._run_pytubefix_audio_stt",
            return_value="Fallback transcript",
        ),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Title", "author_name": None},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = ValueError("unexpected API shape")
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is None
    assert result.text == "Fallback transcript"


# ── TDD: Strategy 3 integration — success path in extract() ──────────────────


@pytest.mark.asyncio
async def test_strategy3_groq_stt_used_when_strategies_1_and_2_fail():
    """When Strategy 1 and 2 both return no text, Strategy 3 (Groq Whisper STT)
    provides the transcript and the result has no error."""
    from youtube_transcript_api import NoTranscriptFound

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch(
            "app.adapters.youtube._run_pytubefix_audio_stt",
            return_value="Groq STT transcript",
        ),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Video Title", "author_name": "Author"},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is None
    assert result.text == "Groq STT transcript"
    assert result.title == "Video Title"
    assert result.author == "Author"


# ── TDD: YoutubeAdapter class wrapper ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_youtube_adapter_delegates_to_module_extract():
    """YoutubeAdapter.extract() is a thin delegation wrapper; it calls the module-level
    extract() with the URL unchanged and returns its result."""
    from app.adapters.base import ExtractedContent

    expected = ExtractedContent(
        text="adapter test content",
        title="Adapter Test",
        source_url="https://www.youtube.com/watch?v=abc123",
        source_type="youtube",
    )

    with patch(
        "app.adapters.youtube.extract", new=AsyncMock(return_value=expected)
    ) as mock_extract:
        adapter = YoutubeAdapter()
        result = await adapter.extract("https://www.youtube.com/watch?v=abc123")

    mock_extract.assert_called_once_with("https://www.youtube.com/watch?v=abc123")
    assert result.text == "adapter test content"
    assert result.title == "Adapter Test"


# ── TDD: IP-block detection and messaging ──────────────────────────────────

@pytest.mark.asyncio
async def test_strategy1_ip_block_detection(caplog):
    """AC-001: IP-block error from youtube-transcript-api is detected and included."""
    import logging
    caplog.set_level(logging.WARNING, logger="synker.youtube")

    ip_block_error = (
        "YouTube is blocking requests from your IP. This is most likely caused by:"
        " You are doing requests from an IP belonging to a cloud provider"
        " (like AWS, Google Cloud Platform, Azure, etc.)."
    )

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test Video", "author_name": "Test Channel"},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = Exception(ip_block_error)
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is not None
    assert "IP-blocked by CDN" in result.error
    assert result.text == ""


@pytest.mark.asyncio
async def test_strategy1_ip_block_logs_attempt_info(caplog):
    """AC-002: When Strategy 1 detects IP block, Strategy 2 is still attempted."""
    import logging
    caplog.set_level(logging.INFO, logger="synker.youtube")

    ip_block_error = "You are doing requests from an IP belonging to a cloud provider"

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch(
            "app.adapters.youtube._run_yt_dlp_subs",
            return_value="yt-dlp fallback transcript",
        ),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test Video", "author_name": "Test Channel"},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = Exception(ip_block_error)
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # Should succeed via Strategy 2
    assert result.error is None
    assert "yt-dlp fallback" in result.text
    # Check log for transition
    assert "Strategy 1 IP-blocked" in caplog.text


@pytest.mark.asyncio
async def test_all_strategies_fail_with_ip_block_message():
    """AC-003: When all strategies fail and IP block was detected, final error is clear."""
    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test Video", "author_name": "Test Channel"},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = Exception(
            "You are doing requests from an IP belonging to a cloud provider"
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error == (
        "YouTube content cannot be extracted on this deployment"
        " (IP-blocked by CDN). Transcript unavailable."
    )
    assert result.text == ""


@pytest.mark.asyncio
async def test_strategy2_logs_elapsed_time(caplog):
    """AC-004: Strategy 2 failure logs with elapsed time."""
    import logging
    caplog.set_level(logging.INFO, logger="synker.youtube")

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch(
            "app.adapters.youtube._run_yt_dlp_subs",
            return_value=None,
        ),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test", "author_name": None},
        ),
    ):
        from youtube_transcript_api import NoTranscriptFound
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # Should have called Strategy 2 (even though mocked)
    # The log will show the final error message
    assert result.error is not None


@pytest.mark.asyncio
async def test_strategy3_logs_audio_download_failure(monkeypatch, caplog):
    """AC-005: Strategy 3 audio download failure logs with step name."""
    import logging
    caplog.set_level(logging.INFO, logger="synker.youtube")

    _fake_pytubefix(monkeypatch, create_file=False, raise_exc=RuntimeError("network error"))
    _fake_groq(monkeypatch)

    from youtube_transcript_api import NoTranscriptFound
    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test", "author_name": None},
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is not None


@pytest.mark.asyncio
async def test_fallback_title_when_oembed_returns_none():
    """AC-008: When oEmbed returns no title, fallback to 'YouTube video {video_id}'."""
    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={},  # Empty oEmbed response
        ),
    ):
        mock_api_cls.return_value.fetch.side_effect = Exception("no transcript")
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.title == "YouTube video dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_oembed_failure_logged(caplog):
    """AC-010: When oEmbed fetch fails, a WARNING log is recorded."""
    import logging
    caplog.set_level(logging.WARNING, logger="synker.youtube")

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value="transcript"),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_api_cls.return_value.fetch.side_effect = Exception("no transcript")
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("connection failed")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is None
    assert "transcript" in result.text
    # Check for oEmbed failure log
    assert "oEmbed" in caplog.text or "metadata fetch failed" in caplog.text


# ── TDD: _run_supadata (Strategy 1.5) ─────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_returns_transcript_immediately():
    """Supadata returns transcript directly (video ≤20 min)."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "content": "This is a test transcript from Supadata",
            "lang": "en",
        })
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _run_supadata("dQw4w9WgXcQ", "test-key")

    assert result == "This is a test transcript from Supadata"


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_polls_until_completed():
    """Supadata polls status endpoint until completed (video >20 min)."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls, patch(
        "app.adapters.youtube.asyncio.sleep", new_callable=AsyncMock
    ):
        mock_client = AsyncMock()
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json = MagicMock(return_value={"jobId": "job-123"})

        # Poll 1: queued
        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json = MagicMock(return_value={"status": "queued"})

        # Poll 2: active
        mock_response3 = MagicMock()
        mock_response3.status_code = 200
        mock_response3.json = MagicMock(return_value={"status": "active"})

        # Poll 3: completed
        mock_response4 = MagicMock()
        mock_response4.status_code = 200
        mock_response4.json = MagicMock(return_value={
            "status": "completed",
            "content": "Polled transcript text",
            "lang": "en",
        })

        mock_client.get = AsyncMock(
            side_effect=[mock_response1, mock_response2, mock_response3, mock_response4]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _run_supadata("dQw4w9WgXcQ", "test-key")

    assert result == "Polled transcript text"


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_http_402_credit_exhausted():
    """Supadata HTTP 402 raises SUPADATA_CREDIT_EXHAUSTED exception."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(Exception, match="SUPADATA_CREDIT_EXHAUSTED"):
            await _run_supadata("dQw4w9WgXcQ", "test-key")


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_http_500_returns_none():
    """Supadata HTTP 5xx error returns None (no exception raised)."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _run_supadata("dQw4w9WgXcQ", "test-key")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_empty_content_returns_none():
    """Supadata returns empty string content, treated as None."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"content": "", "lang": "en"})
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _run_supadata("dQw4w9WgXcQ", "test-key")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_polling_timeout_returns_none():
    """Supadata polling exceeds 12 attempts, returns None."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls, patch(
        "app.adapters.youtube.asyncio.sleep", new_callable=AsyncMock
    ):
        mock_client = AsyncMock()
        mock_response_initial = MagicMock()
        mock_response_initial.status_code = 200
        mock_response_initial.json = MagicMock(return_value={"jobId": "job-123"})

        # Return "active" for all 12 polls
        mock_response_polling = MagicMock()
        mock_response_polling.status_code = 200
        mock_response_polling.json = MagicMock(return_value={"status": "active"})

        mock_client.get = AsyncMock(
            side_effect=[mock_response_initial] + [mock_response_polling] * 12
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _run_supadata("dQw4w9WgXcQ", "test-key")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_supadata_non_english_lang_logs_and_returns():
    """Supadata response with lang='ko' is logged but transcript is returned."""
    from app.adapters.youtube import _run_supadata

    with patch("app.adapters.youtube.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "content": "한국어 자막입니다",
            "lang": "ko",
        })
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await _run_supadata("dQw4w9WgXcQ", "test-key")

    assert result == "한국어 자막입니다"


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_strategy_1_5_fallback_success():
    """Strategy 1 fails, Strategy 1.5 (Supadata) succeeds, result uses transcript."""
    from youtube_transcript_api import NoTranscriptFound

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch(
            "app.adapters.youtube._run_supadata",
            new_callable=AsyncMock,
            return_value="Supadata transcript text",
        ),
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test Video", "author_name": "Channel"},
        ),
        patch("app.core.config.settings") as mock_settings,
    ):
        mock_settings.supadata_api_key = "test-key"
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.error is None
    assert result.text == "Supadata transcript text"
    assert result.title == "Test Video"


@pytest.mark.asyncio
@pytest.mark.supadata_test
async def test_strategy_1_5_skipped_when_key_empty():
    """When supadata_api_key is empty, Supadata strategy is skipped."""
    from youtube_transcript_api import NoTranscriptFound

    with (
        patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls,
        patch(
            "app.adapters.youtube._run_supadata",
            side_effect=AssertionError("_run_supadata should not be called"),
        ),
        patch("app.adapters.youtube._run_yt_dlp_subs", return_value=None),
        patch("app.adapters.youtube._run_pytubefix_audio_stt", return_value=None),
        patch(
            "app.adapters.youtube._fetch_meta",
            return_value={"title": "Test", "author_name": None},
        ),
        patch("app.core.config.settings") as mock_settings,
    ):
        mock_settings.supadata_api_key = ""
        mock_api_cls.return_value.fetch.side_effect = NoTranscriptFound(
            "dQw4w9WgXcQ", ("en",), MagicMock()
        )
        result = await extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # Should fail at the end since all strategies failed
    assert result.error is not None
