"""Tests for the Web source adapter."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.base import ExtractionError
from app.adapters.web import WebAdapter, _html_title, _is_safe_url


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

    with (
        patch("httpx.AsyncClient") as mock_cls,
        patch(
            "trafilatura.extract",
            return_value="Article content here. More words follow.",
        ),
        patch(
            "trafilatura.extract_metadata",
            return_value=MagicMock(
                title="Test Article", author="Jane Doe", date=None
            ),
        ),
    ):
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


# ─── SEC-007 / SEC-008: SSRF Protection Tests ──────────────────────────────────


def test_is_safe_url_rejects_invalid_scheme():
    """SEC-007: Reject non-http/https schemes."""
    assert not _is_safe_url("ftp://example.com")
    assert not _is_safe_url("file:///etc/passwd")
    assert not _is_safe_url("gopher://example.com")
    assert not _is_safe_url("data:text/html,<script>alert(1)</script>")


def test_is_safe_url_rejects_private_ips():
    """SEC-008: Reject URLs pointing to private IP ranges."""
    # Loopback
    assert not _is_safe_url("http://127.0.0.1")
    assert not _is_safe_url("http://localhost")

    # Private ranges
    assert not _is_safe_url("http://10.0.0.1")
    assert not _is_safe_url("http://172.16.0.1")
    assert not _is_safe_url("http://192.168.1.1")

    # Link-local
    assert not _is_safe_url("http://169.254.169.254")


def test_is_safe_url_accepts_public_ips():
    """SEC-008: Accept URLs pointing to public IP addresses."""
    # These are public IPs (8.8.8.8 is Google DNS)
    assert _is_safe_url("http://8.8.8.8")
    assert _is_safe_url("https://1.1.1.1")


def test_is_safe_url_accepts_public_hostnames():
    """SEC-007: Accept valid public hostnames with http/https."""
    assert _is_safe_url("https://example.com")
    assert _is_safe_url("http://google.com")
    assert _is_safe_url("https://github.com/synker")


@pytest.mark.asyncio
async def test_ssrf_attack_rejected():
    """SEC-008: SSRF attack attempting to reach private IP is rejected."""
    with pytest.raises(ExtractionError, match="private or reserved IP address"):
        await WebAdapter().extract("http://127.0.0.1:8000/admin")
