"""Tests for the Web source adapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.adapters.base import ExtractionError
from app.adapters.web import WebAdapter, _html_title


def test_html_title():
    assert _html_title("<title>My Page</title>") == "My Page"
    assert _html_title("<html><body></body></html>") is None


@pytest.mark.asyncio
async def test_happy_path():
    html = """<html><head><title>Test Article</title>
    <meta property=\"og:article:author\" content=\"Jane Doe\"/>
    </head><body><article><p>Article content here. More words follow.</p></article></body></html>"""

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as mock_cls, \
         patch("trafilatura.extract", return_value="Article content here. More words follow."), \
         patch("trafilatura.extract_metadata", return_value=MagicMock(title="Test Article", author="Jane Doe", date=None)):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        result = await WebAdapter().extract("https://example.com/article")

    assert result.title == "Test Article"
    assert result.author == "Jane Doe"
    assert result.word_count > 0
    assert result.source_type == "web"


@pytest.mark.asyncio
async def test_trafilatura_none_falls_back():
    html = "<html><head><title>Fallback Page</title></head><body></body></html>"

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as mock_cls, \
         patch("trafilatura.extract", return_value=None), \
         patch("trafilatura.extract_metadata", return_value=None):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        result = await WebAdapter().extract("https://example.com/js-page")

    assert "[low quality]" in result.title
    assert result.text == ""


@pytest.mark.asyncio
async def test_http_404_raises():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(ExtractionError, match="HTTP 404"):
            await WebAdapter().extract("https://example.com/missing")
