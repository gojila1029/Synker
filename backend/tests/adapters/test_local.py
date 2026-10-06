"""Tests for the Local file source adapter."""
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from app.adapters.base import ExtractionError, ExtractedContent
from app.adapters.local import LocalAdapter


@pytest.mark.asyncio
async def test_txt_file(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("Hello from text file.", encoding="utf-8")
    result = await LocalAdapter().extract(str(f))
    assert result.text == "Hello from text file."
    assert result.title == "note"
    assert result.source_type == "local"
    assert result.word_count == 4


@pytest.mark.asyncio
async def test_md_file(tmp_path: Path):
    f = tmp_path / "readme.md"
    f.write_text("# Title\n\nContent here.", encoding="utf-8")
    result = await LocalAdapter().extract(str(f))
    assert "Content here." in result.text
    assert result.title == "readme"
    assert result.source_type == "local"


@pytest.mark.asyncio
async def test_unsupported_extension_raises(tmp_path: Path):
    f = tmp_path / "doc.docx"
    f.write_bytes(b"fake docx")
    with pytest.raises(ExtractionError, match="Unsupported file type"):
        await LocalAdapter().extract(str(f))


@pytest.mark.asyncio
async def test_path_traversal_raises():
    with pytest.raises(ExtractionError, match="Path traversal"):
        await LocalAdapter().extract("../../../etc/passwd")


@pytest.mark.asyncio
async def test_missing_file_raises():
    with pytest.raises(ExtractionError, match="File not found"):
        await LocalAdapter().extract("/nonexistent/file.txt")


@pytest.mark.asyncio
async def test_pdf_delegates_to_pdf_adapter(tmp_path: Path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"fake pdf")
    fake_result = ExtractedContent(
        source_url=str(f),
        text="PDF content",
        title="doc",
        source_type="pdf",
        word_count=2,
    )
    with patch("app.adapters.pdf.PdfAdapter.extract", new_callable=AsyncMock, return_value=fake_result):
        result = await LocalAdapter().extract(str(f))
    assert result.text == "PDF content"
    assert result.source_type == "pdf"


@pytest.mark.asyncio
async def test_published_at_from_mtime(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("Content", encoding="utf-8")
    result = await LocalAdapter().extract(str(f))
    assert result.published_at is not None
    assert "T" in result.published_at  # ISO format includes T


@pytest.mark.asyncio
async def test_empty_text_file(tmp_path: Path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    result = await LocalAdapter().extract(str(f))
    assert result.text == ""
    assert result.word_count == 0


@pytest.mark.asyncio
async def test_backward_compat_extract_function(tmp_path: Path):
    """Test the functional wrapper for backward compatibility."""
    from app.adapters.local import extract
    f = tmp_path / "note.txt"
    f.write_text("Test content", encoding="utf-8")
    result = await extract(str(f))
    assert result.text == "Test content"
    assert result.title == "note"
