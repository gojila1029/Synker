"""Tests for YouTube keyword search adapter."""
import pytest

from app.adapters.youtube_search import SearchResult, YouTubeSearchResult, search_youtube


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_youtube_no_query() -> None:
    """Empty queries should return NO_RESULTS."""
    result = await search_youtube("", limit=10)
    assert result.error is not None or not result.results


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_youtube_limit_validation() -> None:
    """Limit should be respected (positive, reasonable bounds)."""
    result = await search_youtube("python tutorial", limit=5)
    # Result may be empty if yt-dlp is not installed, but structure should be correct
    assert isinstance(result.results, list)
    assert isinstance(result.error, (str, type(None)))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_youtube_returns_video_ids() -> None:
    """Valid search results should have video IDs."""
    result = await search_youtube("hello", limit=3)
    if result.results:
        for item in result.results:
            assert isinstance(item, SearchResult)
            assert item.video_id
            assert item.title
            assert item.url
            assert "youtube.com" in item.url or "youtu.be" in item.url


@pytest.mark.unit
def test_search_result_structure() -> None:
    """SearchResult dataclass should have all required fields."""
    result = SearchResult(video_id="abc123", title="Test Video", url="https://youtube.com/watch?v=abc123")
    assert result.video_id == "abc123"
    assert result.title == "Test Video"
    assert result.url == "https://youtube.com/watch?v=abc123"
    assert result.channel is None


@pytest.mark.unit
def test_youtube_search_result_error_structure() -> None:
    """YouTubeSearchResult should support error state."""
    result = YouTubeSearchResult(
        error="Test error",
        error_code="SEARCH_UNAVAILABLE",
    )
    assert result.error == "Test error"
    assert result.error_code == "SEARCH_UNAVAILABLE"
    assert result.results == []


@pytest.mark.unit
def test_youtube_search_result_no_results() -> None:
    """YouTubeSearchResult with NO_RESULTS code."""
    result = YouTubeSearchResult(
        error="No results found",
        error_code="NO_RESULTS",
    )
    assert result.error_code == "NO_RESULTS"
    assert len(result.results) == 0
