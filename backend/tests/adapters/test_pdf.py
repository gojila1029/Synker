"""Tests for the PDF source adapter."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.pdf import MAX_PDF_SIZE, PdfAdapter, _parse_pdf_date


def test_parse_pdf_date() -> None:
    assert _parse_pdf_date("D:20230115120000") == "2023-01-15"
    assert _parse_pdf_date("20230115") == "2023-01-15"
    assert _parse_pdf_date("bad") is None


def _make_mock_pdf(pages_text: list[str], metadata: dict | None = None) -> MagicMock:
    mock_pdf = MagicMock()
    mock_pdf.metadata = metadata or {"Title": "Test Doc", "Author": "Alice"}
    mock_pages = []
    for t in pages_text:
        p = MagicMock()
        p.extract_text.return_value = t
        mock_pages.append(p)
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=None)
    return mock_pdf


def test_extract_happy_path() -> None:
    mock_pdf = _make_mock_pdf(
        ["Page one text.", "Page two text."],
        metadata={"Title": "Test PDF", "Author": "Alice"},
    )
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value = mock_pdf
    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = PdfAdapter()._from_bytes(b"fake", "doc.pdf")
    assert "Page one text." in result.text
    assert result.title == "Test PDF"
    assert result.author == "Alice"
    assert result.source_type == "pdf"
    assert result.word_count > 0
    assert result.error is None


def test_extract_empty_pdf() -> None:
    mock_pdf = _make_mock_pdf(["", "  "])
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value = mock_pdf
    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = PdfAdapter()._from_bytes(b"fake", "empty.pdf")
    assert result.error == "PDF contains no extractable text"
    assert result.text == ""


def test_extract_encrypted_pdf() -> None:
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.side_effect = Exception("password required encrypted")
    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = PdfAdapter()._from_bytes(b"fake", "secret.pdf")
    assert "encrypted" in result.error.lower()


def test_extract_corrupted_pdf() -> None:
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.side_effect = ValueError("Invalid PDF structure")
    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = PdfAdapter()._from_bytes(b"fake", "corrupted.pdf")
    assert "cannot open pdf" in result.error.lower()


@pytest.mark.asyncio
async def test_extract_local_file(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"fake")
    mock_pdf = _make_mock_pdf(["Local PDF content."])
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value = mock_pdf
    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = await PdfAdapter().extract(str(fake_pdf))
    assert "Local PDF content." in result.text
    assert result.error is None


@pytest.mark.asyncio
async def test_extract_missing_file() -> None:
    result = await PdfAdapter().extract("/nonexistent/path.pdf")
    assert result.error == "File not found: /nonexistent/path.pdf"
    assert result.text == ""
    assert result.source_type == "pdf"


@pytest.mark.asyncio
async def test_extract_http_pdf(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    mock_pdf = _make_mock_pdf(["HTTP PDF content."])
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value = mock_pdf

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()

        # Mock HEAD response
        mock_head_response = MagicMock()
        mock_head_response.headers = {"content-length": str(1000)}
        mock_head_response.raise_for_status.return_value = None

        # Mock GET response
        mock_get_response = MagicMock()
        mock_get_response.content = b"fake pdf data"
        mock_get_response.raise_for_status.return_value = None

        mock_client.head = AsyncMock(return_value=mock_head_response)
        mock_client.get = AsyncMock(return_value=mock_get_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
            result = await PdfAdapter().extract("https://example.com/doc.pdf")

    assert "HTTP PDF content." in result.text
    assert result.error is None


# ─── Risk-001: File Size Validation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_oversized_local_file(tmp_path: Path) -> None:
    """Risk-001: Local PDF exceeding 50MB is rejected."""
    large_file = tmp_path / "large.pdf"
    # Create a file larger than MAX_PDF_SIZE (50MB)
    with open(large_file, "wb") as f:
        f.seek(MAX_PDF_SIZE + 1)
        f.write(b"x")

    result = await PdfAdapter().extract(str(large_file))
    assert "exceeds 50MB limit" in result.error
    assert result.text == ""


@pytest.mark.asyncio
async def test_extract_oversized_http_pdf() -> None:
    """Risk-001: HTTP PDF with Content-Length > 50MB is rejected."""
    from unittest.mock import AsyncMock

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()

        # Mock HEAD response with large Content-Length
        mock_head_response = MagicMock()
        mock_head_response.headers = {"content-length": str(MAX_PDF_SIZE + 1000)}
        mock_head_response.raise_for_status.return_value = None

        mock_client.head = AsyncMock(return_value=mock_head_response)
        mock_client.get = AsyncMock()  # Should not be called
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await PdfAdapter().extract("https://example.com/large.pdf")

    assert "exceeds 50MB limit" in result.error
    assert result.text == ""
    # Verify GET was not called (we stopped at HEAD)
    assert not mock_client.get.called


@pytest.mark.asyncio
async def test_extract_valid_size_http_pdf(tmp_path: Path) -> None:
    """Risk-001: HTTP PDF under 50MB is processed normally."""
    from unittest.mock import AsyncMock

    mock_pdf = _make_mock_pdf(["Valid size HTTP PDF content."])
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value = mock_pdf

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()

        # Mock HEAD response with small Content-Length
        mock_head_response = MagicMock()
        mock_head_response.headers = {"content-length": str(1000)}
        mock_head_response.raise_for_status.return_value = None

        # Mock GET response
        mock_get_response = MagicMock()
        mock_get_response.content = b"fake pdf data"
        mock_get_response.raise_for_status.return_value = None

        mock_client.head = AsyncMock(return_value=mock_head_response)
        mock_client.get = AsyncMock(return_value=mock_get_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
            result = await PdfAdapter().extract("https://example.com/doc.pdf")

    assert "Valid size HTTP PDF content." in result.text
    assert result.error is None
