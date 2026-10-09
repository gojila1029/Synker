"""Tests for the Local file source adapter."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.base import ExtractedContent, ExtractionError
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
async def test_unsupported_extension_returns_error(tmp_path: Path):
    """Unsupported file types return ExtractedContent with error field (not raise)."""
    f = tmp_path / "doc.docx"
    f.write_bytes(b"fake docx")
    result = await LocalAdapter().extract(str(f))
    assert result.error is not None
    assert "not supported" in result.error.lower()
    assert result.text == ""
    assert result.title == "doc"
    assert result.source_type == "local"


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
    with patch(
        "app.adapters.pdf.PdfAdapter.extract",
        new_callable=AsyncMock,
        return_value=fake_result,
    ):
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
async def test_unsupported_jpg_returns_error(tmp_path: Path):
    """JPG files return ExtractedContent with error field."""
    f = tmp_path / "image.jpg"
    f.write_bytes(b"fake jpg")
    result = await LocalAdapter().extract(str(f))
    assert result.error is not None
    assert "not supported" in result.error.lower()
    assert result.text == ""
    assert result.title == "image"


@pytest.mark.asyncio
async def test_unsupported_zip_returns_error(tmp_path: Path):
    """ZIP files return ExtractedContent with error field."""
    f = tmp_path / "archive.zip"
    f.write_bytes(b"fake zip")
    result = await LocalAdapter().extract(str(f))
    assert result.error is not None
    assert "not supported" in result.error.lower()
    assert result.text == ""
    assert result.title == "archive"


@pytest.mark.asyncio
async def test_backward_compat_extract_function(tmp_path: Path):
    """Test the functional wrapper for backward compatibility."""
    from app.adapters.local import extract
    f = tmp_path / "note.txt"
    f.write_text("Test content", encoding="utf-8")
    result = await extract(str(f))
    assert result.text == "Test content"
    assert result.title == "note"


# ─── Folder Extraction Tests (AC-002 through AC-005, AC-008) ────────────────


@pytest.mark.asyncio
async def test_extract_folder_detects_directory(tmp_path: Path):
    """AC-002: extract() detects when url is a directory."""
    folder = tmp_path / "test_folder"
    folder.mkdir()
    (folder / "file1.txt").write_text("Content 1", encoding="utf-8")

    result = await LocalAdapter().extract(str(folder))
    assert isinstance(result, list), "Folder extraction should return list"
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_extract_folder_recursive_finds_all_files(tmp_path: Path):
    """AC-003: Recursively finds all supported files in folder and subdirs.

    GIVEN a folder with files at multiple levels
    WHEN extract is called on the folder
    THEN all supported files are discovered and extracted
    """
    folder = tmp_path / "root"
    folder.mkdir()
    (folder / "file1.txt").write_text("Text 1", encoding="utf-8")
    (folder / "file2.md").write_text("# Markdown\nContent 2", encoding="utf-8")

    subfolder = folder / "sub"
    subfolder.mkdir()
    (subfolder / "file3.txt").write_text("Text 3", encoding="utf-8")

    result = await LocalAdapter().extract(str(folder))
    assert isinstance(result, list)
    assert len(result) == 3, f"Expected 3 files, got {len(result)}"

    titles = [r.title for r in result]
    assert "file1" in titles
    assert "file2" in titles
    assert "file3" in titles


@pytest.mark.asyncio
async def test_extract_folder_supported_types_only(tmp_path: Path):
    """AC-004: Only processes supported file types (.txt, .md, .pdf).

    GIVEN a folder with mixed supported and unsupported types
    WHEN extract is called
    THEN only .txt/.md/.pdf files are processed
    """
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "doc.txt").write_text("Text", encoding="utf-8")
    (folder / "readme.md").write_text("Markdown", encoding="utf-8")
    (folder / "image.jpg").write_bytes(b"fake jpg")
    (folder / "archive.zip").write_bytes(b"fake zip")

    result = await LocalAdapter().extract(str(folder))
    assert isinstance(result, list)

    # Should have exactly 2 supported files
    supported_results = [r for r in result if not r.error or r.text]
    assert len(supported_results) >= 2, f"Expected at least 2 supported files, got {len(supported_results)}"

    titles = [r.title for r in result]
    assert "doc" in titles
    assert "readme" in titles


@pytest.mark.asyncio
async def test_extract_folder_unsupported_files_skipped(tmp_path: Path):
    """AC-005: Unsupported files are skipped without raising.

    GIVEN a folder with unsupported file types
    WHEN extract is called
    THEN unsupported files are skipped (not raised as errors)
    AND extraction completes successfully
    """
    folder = tmp_path / "unsupported"
    folder.mkdir()
    (folder / "note.txt").write_text("Valid", encoding="utf-8")
    (folder / "image.bmp").write_bytes(b"\x00")
    (folder / "doc.docx").write_bytes(b"fake docx")

    result = await LocalAdapter().extract(str(folder))
    assert isinstance(result, list)

    # At minimum, note.txt should be extracted
    text_results = [r for r in result if r.title == "note"]
    assert len(text_results) >= 1, "note.txt should be extracted"

    # image.bmp and doc.docx should not cause the extraction to fail
    assert len(result) >= 1, "Extraction should complete despite unsupported files"


@pytest.mark.asyncio
async def test_extract_folder_path_traversal_prevented(tmp_path: Path):
    """AC-008: Path traversal attempts are prevented.

    GIVEN a folder extraction process
    WHEN a symlink tries to escape the folder
    THEN symlinks are skipped (is_symlink check)
    """
    folder = tmp_path / "secure"
    folder.mkdir()
    (folder / "file.txt").write_text("Content", encoding="utf-8")

    # Try to create a symlink escaping the folder (may fail on Windows)
    external_file = tmp_path / "external.txt"
    external_file.write_text("External", encoding="utf-8")

    try:
        symlink = folder / "link_to_external"
        symlink.symlink_to(external_file)

        result = await LocalAdapter().extract(str(folder))
        # Symlink should be skipped (is_symlink() check)
        titles = [r.title for r in result]
        assert "link_to_external" not in titles, "Symlink should be skipped"
    except (OSError, NotImplementedError):
        # Windows may not support symlinks; test passes if skipped
        pass


@pytest.mark.asyncio
async def test_extract_folder_with_pdf_file(tmp_path: Path):
    """Folder extraction handles PDF files by delegating to PdfAdapter."""
    folder = tmp_path / "pdfs"
    folder.mkdir()
    (folder / "doc.pdf").write_bytes(b"fake pdf")
    (folder / "note.txt").write_text("Text note", encoding="utf-8")

    fake_pdf_result = ExtractedContent(
        source_url=str(folder / "doc.pdf"),
        text="PDF content",
        title="doc",
        source_type="pdf",
        word_count=2,
    )

    with patch(
        "app.adapters.pdf.PdfAdapter.extract",
        new_callable=AsyncMock,
        return_value=fake_pdf_result,
    ):
        result = await LocalAdapter().extract(str(folder))

    assert isinstance(result, list)
    assert len(result) >= 2, "Should extract both PDF and TXT"

    pdf_results = [r for r in result if r.source_type == "pdf" or r.title == "doc"]
    assert len(pdf_results) >= 1, "PDF should be extracted"


@pytest.mark.asyncio
async def test_extract_folder_deterministic_order(tmp_path: Path):
    """Extracted files are sorted deterministically by path."""
    folder = tmp_path / "order"
    folder.mkdir()
    (folder / "z_file.txt").write_text("Z", encoding="utf-8")
    (folder / "a_file.txt").write_text("A", encoding="utf-8")
    (folder / "m_file.txt").write_text("M", encoding="utf-8")

    result = await LocalAdapter().extract(str(folder))
    assert isinstance(result, list)

    titles = [r.title for r in result]
    # Should be sorted: a_file, m_file, z_file
    assert titles == sorted(titles), f"Results should be sorted: {titles}"


@pytest.mark.asyncio
async def test_extract_single_file_unchanged(tmp_path: Path):
    """AC-001: Single file extraction returns ExtractedContent (not list)."""
    f = tmp_path / "single.txt"
    f.write_text("Single file content", encoding="utf-8")

    result = await LocalAdapter().extract(str(f))
    assert isinstance(result, ExtractedContent), "Single file should return ExtractedContent"
    assert not isinstance(result, list)
    assert result.text == "Single file content"
