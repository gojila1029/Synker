"""Tests for intent parser."""
import pytest

from app.ai.intent_parser import ParsedIntent, parse_website_intent, parse_youtube_intent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_youtube_intent_fallback_no_key() -> None:
    """Intent parser should fall back to original message when no API key."""
    ai_settings: dict = {}
    result = await parse_youtube_intent("find python tutorials", ai_settings, fallback_limit=10)

    assert isinstance(result, ParsedIntent)
    assert result.fallback_used
    assert result.confidence == 0.0
    assert result.search_query == "find python tutorials"
    assert result.limit == 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_youtube_intent_preserves_korean() -> None:
    """Intent parser should preserve Korean characters in original message fallback."""
    ai_settings: dict = {}
    result = await parse_youtube_intent("파이썬 튜토리얼", ai_settings, fallback_limit=10)

    assert isinstance(result, ParsedIntent)
    assert "파이썬" in result.search_query or result.search_query == "파이썬 튜토리얼"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_youtube_intent_limit_bounds() -> None:
    """Intent parser should bound limit to 1-25 range."""
    ai_settings: dict = {}
    # Test with fallback (no API key)
    result = await parse_youtube_intent("test query", ai_settings, fallback_limit=5)

    assert result.limit >= 1
    assert result.limit <= 25


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_website_intent_fallback_no_key() -> None:
    """Website intent parser should fall back to original message when no API key."""
    ai_settings: dict = {}
    result = await parse_website_intent("find react documentation", ai_settings, fallback_limit=5)

    assert isinstance(result, ParsedIntent)
    assert result.fallback_used
    assert result.confidence == 0.0
    assert result.search_query == "find react documentation"
    assert result.limit == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_website_intent_limit_bounds() -> None:
    """Website intent parser should bound limit to 1-10 range."""
    ai_settings: dict = {}
    result = await parse_website_intent("test query", ai_settings, fallback_limit=3)

    assert result.limit >= 1
    assert result.limit <= 10


@pytest.mark.unit
def test_parsed_intent_structure() -> None:
    """ParsedIntent should have required fields."""
    intent = ParsedIntent(
        search_query="test",
        limit=10,
        confidence=0.85,
        fallback_used=False,
    )
    assert intent.search_query == "test"
    assert intent.limit == 10
    assert intent.confidence == 0.85
    assert intent.fallback_used is False
    assert intent.error is None


@pytest.mark.unit
def test_parsed_intent_with_error() -> None:
    """ParsedIntent should support error state."""
    intent = ParsedIntent(
        search_query="original",
        limit=10,
        confidence=0.0,
        fallback_used=True,
        error="Test error message",
    )
    assert intent.error == "Test error message"
    assert intent.fallback_used
