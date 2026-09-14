"""Tests for YouTube channel/playlist discovery (yt-dlp, no login/API key).

Real Discovery engine for `source_scope='discovery_provider'` sources (see
app/adapters/classify.py) -- previously _analysis_handler skipped these
unconditionally because nothing enumerated a channel/playlist's videos.
"""
import sys

from app.adapters import youtube_discovery as disc


class _FakeYDL:
    """Mimics yt_dlp.YoutubeDL's context-manager + extract_info() shape."""

    def __init__(self, opts, entries=None, raise_exc=None):
        self.opts = opts
        self._entries = entries if entries is not None else []
        self._raise_exc = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if self._raise_exc:
            raise self._raise_exc
        return {"entries": self._entries}


def _install_fake_yt_dlp(monkeypatch, entries=None, raise_exc=None, capture=None):
    def _ydl_factory(opts):
        if capture is not None:
            capture["opts"] = opts
        return _FakeYDL(opts, entries=entries, raise_exc=raise_exc)

    fake_module = type("_FakeYtDlpModule", (), {"YoutubeDL": staticmethod(_ydl_factory)})
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)


async def test_search_url_is_explicitly_unsupported():
    """A /results?search_query= URL cannot be enumerated without the paid
    YouTube Data API -- must be reported as unsupported, not a fake empty
    'channel has no videos' result."""
    result = await disc.discover_channel_videos(
        "https://www.youtube.com/results?search_query=insurance+broking"
    )

    assert result.videos == []
    assert result.error is None
    assert result.unsupported_reason is not None


async def test_channel_url_returns_flat_entries(monkeypatch):
    _install_fake_yt_dlp(
        monkeypatch,
        entries=[
            {"id": "vid1", "title": "First video", "url": "https://www.youtube.com/watch?v=vid1"},
            {"id": "vid2", "title": "Second video", "url": "https://www.youtube.com/watch?v=vid2"},
        ],
    )

    result = await disc.discover_channel_videos("https://www.youtube.com/@somechannel")

    assert result.error is None
    assert result.unsupported_reason is None
    assert [v.url for v in result.videos] == [
        "https://www.youtube.com/watch?v=vid1",
        "https://www.youtube.com/watch?v=vid2",
    ]
    assert result.videos[0].title == "First video"


async def test_entry_without_url_falls_back_to_id(monkeypatch):
    """Flat playlist extraction sometimes omits 'url' but always has 'id'."""
    _install_fake_yt_dlp(monkeypatch, entries=[{"id": "vid3", "title": "Third video"}])

    result = await disc.discover_channel_videos("https://www.youtube.com/playlist?list=PL123")

    assert result.videos[0].url == "https://www.youtube.com/watch?v=vid3"


async def test_blank_entries_in_playlist_are_skipped(monkeypatch):
    """yt-dlp can yield None entries for deleted/private videos in a playlist."""
    _install_fake_yt_dlp(
        monkeypatch,
        entries=[None, {"id": "vid4", "title": "Real video"}],
    )

    result = await disc.discover_channel_videos("https://www.youtube.com/playlist?list=PL123")

    assert len(result.videos) == 1
    assert result.videos[0].url == "https://www.youtube.com/watch?v=vid4"


async def test_yt_dlp_failure_is_reported_honestly(monkeypatch):
    """A real yt-dlp error (private channel, network failure, etc.) must
    surface as .error text, never a silent empty-success result."""
    _install_fake_yt_dlp(monkeypatch, raise_exc=RuntimeError("network unreachable"))

    result = await disc.discover_channel_videos("https://www.youtube.com/@somechannel")

    assert result.videos == []
    assert result.error is not None
    assert "network unreachable" in result.error


async def test_yt_dlp_not_installed_is_reported_honestly(monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    result = await disc.discover_channel_videos("https://www.youtube.com/@somechannel")

    assert result.videos == []
    assert result.error is not None
    assert "yt-dlp is not installed" in result.error


async def test_limit_is_passed_to_yt_dlp_options(monkeypatch):
    captured: dict = {}
    _install_fake_yt_dlp(monkeypatch, entries=[], capture=captured)

    await disc.discover_channel_videos("https://www.youtube.com/playlist?list=PL123", limit=10)

    assert captured["opts"]["playlistend"] == 10


async def test_extract_flat_option_is_set(monkeypatch):
    """Must use flat extraction -- fetching every video's full page just to
    enumerate a channel would be far slower and unnecessary."""
    captured: dict = {}
    _install_fake_yt_dlp(monkeypatch, entries=[], capture=captured)

    await disc.discover_channel_videos("https://www.youtube.com/@somechannel")

    assert captured["opts"]["extract_flat"] is True
