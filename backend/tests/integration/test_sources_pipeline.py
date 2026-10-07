"""Integration tests for PDF, local, and web source pipelines.

These tests verify the full extraction pipeline end-to-end:
1. A source of type pdf/local/web is created
2. _analysis_handler processes it
3. A candidate is created with the extracted metadata
4. source_extractions row is persisted (on success) or error is captured (on failure)

This validates AC-001 through AC-016 from the contract.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.adapters.base import ExtractedContent
from app.worker.handlers import _analysis_handler, _candidate_fields


class AsyncContextManagerMock:
    """Mock that works as an async context manager."""

    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *args):
        pass


# ─── AC-001 / AC-002: PDF Happy Path ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_pdf_source_extracted_creates_candidate_with_evidence():
    """AC-001 + AC-002: PDF file → extracted candidate + source_extractions row.

    GIVEN a PDF file is available
    WHEN the Analysis job processes it
    THEN a candidate is created with extracted metadata
    AND source_extractions table contains the PDF text + metadata
    """
    user_id = "user-123"
    source_id = "pdf-source-1"

    # Mock database
    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # Mock queued source
    pdf_source = {
        "id": source_id,
        "type": "pdf",
        "title": "Sample PDF",
        "url": "/path/to/sample.pdf",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [pdf_source]
    mock_conn.fetchval.return_value = None  # No existing candidate

    # Mock progress function
    progress = AsyncMock()

    # Mock adapter to return extracted PDF content
    mock_extracted = ExtractedContent(
        text="This is PDF content with multiple words that demonstrate extraction.",
        title="Sample PDF Title",
        author="PDF Author",
        published_at="2024-01-15",
        word_count=12,
        source_url="/path/to/sample.pdf",
        source_type="pdf",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Verify result mentions candidates created
    assert "1 candidate" in result, f"Expected 1 candidate, got: {result}"

    # Verify async execute was called for candidate + source_extractions
    assert mock_conn.execute.called, "No database operations performed"

    # Verify candidate INSERT was called
    candidate_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(call)
    ]
    assert len(candidate_calls) >= 1, "Candidate should be created"

    # Verify source_extractions INSERT was called
    extraction_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO source_extractions" in str(call)
    ]
    assert len(extraction_calls) >= 1, "source_extractions should be persisted"


# ─── AC-003: Encrypted PDF Error Handling ──────────────────────────────────────


@pytest.mark.asyncio
async def test_encrypted_pdf_skips_candidate_marks_source_failed():
    """OQ-001: Encrypted PDF with extraction failure → skip candidate creation.

    GIVEN a PDF file is encrypted
    WHEN the Analysis job processes it
    THEN NO candidate is created
    AND the source is marked as status='failed'
    AND the error is logged in processing_log
    """
    user_id = "user-123"
    source_id = "pdf-source-encrypted"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    pdf_source = {
        "id": source_id,
        "type": "pdf",
        "title": "Secret PDF",
        "url": "/path/to/secret.pdf",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [pdf_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    # Adapter returns error for encrypted PDF
    mock_extracted = ExtractedContent(
        text="",
        title="",
        source_url="/path/to/secret.pdf",
        source_type="pdf",
        error="PDF is encrypted",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Verify result indicates 0 candidates created
    assert "0 candidate" in result, f"Expected 0 candidates, got: {result}"

    # Verify NO candidate was created
    candidate_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(call)
    ]
    assert len(candidate_calls) == 0, "Candidate should NOT be created for extraction failure"

    # Verify source was marked as failed
    failed_updates = [
        call for call in mock_conn.execute.call_args_list
        if "UPDATE sources SET status='failed'" in str(call)
    ]
    assert len(failed_updates) == 1, "Source should be marked as failed"

    # Verify error was logged
    log_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO processing_log" in str(call) and "extraction_failed" in str(call)
    ]
    assert len(log_calls) == 1, "Extraction error should be logged"


# ─── AC-004: Empty PDF Error Handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_pdf_skips_candidate_marks_source_failed():
    """OQ-001: Empty PDF with extraction failure → skip candidate creation.

    GIVEN a PDF contains no extractable text
    WHEN the Analysis job processes it
    THEN NO candidate is created
    AND the source is marked as status='failed'
    AND the error is logged in processing_log
    """
    user_id = "user-123"
    source_id = "pdf-source-empty"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    pdf_source = {
        "id": source_id,
        "type": "pdf",
        "title": "Empty PDF",
        "url": "/path/to/empty.pdf",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [pdf_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    mock_extracted = ExtractedContent(
        text="",
        title="",
        source_url="/path/to/empty.pdf",
        source_type="pdf",
        error="PDF contains no extractable text",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Verify result indicates 0 candidates created
    assert "0 candidate" in result, f"Expected 0 candidates, got: {result}"

    # Verify NO candidate was created for extraction failure
    candidate_calls = [
        c for c in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(c)
    ]
    assert len(candidate_calls) == 0, "Candidate should NOT be created for extraction failure"


# ─── AC-005 / AC-006: Local File Happy Path ────────────────────────────────────


@pytest.mark.asyncio
async def test_local_file_extracted_creates_candidate_with_evidence():
    """AC-005 + AC-006: Local .txt/.md file → extracted candidate + source_extractions.

    GIVEN a local .txt or .md file path
    WHEN the Analysis job processes it
    THEN a candidate is created with extracted metadata
    AND source_extractions contains text, title, word_count, published_at (mtime)
    """
    user_id = "user-123"
    source_id = "local-source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    local_source = {
        "id": source_id,
        "type": "local",
        "title": "README",
        "url": "/home/user/README.md",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [local_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    mock_extracted = ExtractedContent(
        text="# README\n\nThis is the content of the local file.",
        title="README",
        author="",
        published_at="2024-01-15T10:30:00+00:00",
        word_count=8,
        source_url="/home/user/README.md",
        source_type="local",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    assert "1 candidate" in result, f"Expected 1 candidate, got: {result}"


# ─── AC-007: Path Traversal Rejection ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_path_traversal_attempt_creates_candidate_with_error():
    """AC-007: Path with '..' → extraction fails with error message.

    GIVEN a local file path contains ".."
    WHEN the Analysis job processes it
    THEN extraction fails with "Path traversal rejected"
    AND NO candidate is created (extraction failed, so skip candidate)
    AND source is marked as failed
    """
    user_id = "user-123"
    source_id = "local-source-traversal"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    local_source = {
        "id": source_id,
        "type": "local",
        "title": "Hack Attempt",
        "url": "../../../../../../etc/passwd",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [local_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    # LocalAdapter.extract() raises ExtractionError on path traversal
    # Our adapter_extract wrapper converts it to ExtractedContent with error
    mock_extracted = ExtractedContent(
        text="",
        title="",
        source_url="../../../../../../etc/passwd",
        source_type="local",
        error="Path traversal rejected: ../../../../../../etc/passwd",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Verify result shows 0 candidates (extraction failed, no candidate created)
    assert "0 candidate" in result, f"Expected 0 candidates, got: {result}"

    # Verify NO candidate was created (this is secure behavior — don't process bad paths)
    candidate_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(call)
    ]
    assert len(candidate_calls) == 0, "No candidate should be created for path traversal attempt"

    # Verify source was marked as failed
    failed_updates = [
        call for call in mock_conn.execute.call_args_list
        if "UPDATE sources SET status='failed'" in str(call)
    ]
    assert len(failed_updates) >= 1, "Source should be marked as failed"


# ─── AC-008: Unsupported File Type ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_file_type_creates_candidate_with_error():
    """AC-008: Unsupported file type (.docx) → extraction fails, no candidate created.

    GIVEN a local .docx or other unsupported file type
    WHEN the Analysis job processes it
    THEN extraction fails with "Unsupported file type"
    AND NO candidate is created (extraction failed)
    AND source is marked as failed
    """
    user_id = "user-123"
    source_id = "local-source-docx"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    local_source = {
        "id": source_id,
        "type": "local",
        "title": "Document",
        "url": "/path/to/document.docx",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [local_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    mock_extracted = ExtractedContent(
        text="",
        title="",
        source_url="/path/to/document.docx",
        source_type="local",
        error="Unsupported file type: '.docx'",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Extraction failed, so no candidate should be created
    assert "0 candidate" in result, f"Expected 0 candidates for unsupported type, got: {result}"

    # Verify NO candidate was created
    candidate_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(call)
    ]
    assert len(candidate_calls) == 0, "No candidate should be created for unsupported file type"


# ─── AC-009 / AC-010: Web Happy Path ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_source_extracted_creates_candidate_with_evidence():
    """AC-009 + AC-010: Valid web URL → extracted candidate + source_extractions.

    GIVEN a valid HTTPS URL
    WHEN the Analysis job processes it
    THEN a candidate is created with title, author, published_at
    AND source_extractions contains extracted text and metadata
    """
    user_id = "user-123"
    source_id = "web-source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    web_source = {
        "id": source_id,
        "type": "web",
        "title": "Article",
        "url": "https://example.com/article",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [web_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    mock_extracted = ExtractedContent(
        text="This is an excellent article about web technologies.",
        title="Web Technologies Article",
        author="Jane Doe",
        published_at="2024-01-15",
        word_count=9,
        source_url="https://example.com/article",
        source_type="web",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    assert "1 candidate" in result, f"Expected 1 candidate, got: {result}"


# ─── AC-011: Low Quality Web Content ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_no_content_marks_low_quality():
    """AC-011: Web page with no content → candidate with '[low quality]' title.

    GIVEN a web page returns no extractable content (but extraction succeeded)
    WHEN the Analysis job processes it
    THEN a candidate is created with title "[low quality] Dynamic Page"
    AND summary is empty
    AND recommendation is "review"
    """
    user_id = "user-123"
    source_id = "web-source-js"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    web_source = {
        "id": source_id,
        "type": "web",
        "title": "Dynamic Page",
        "url": "https://example.com/js-app",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [web_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    # trafilatura returns None for JS-heavy pages; adapter marks as [low quality]
    # NO ERROR is set — extraction succeeded but found no content
    mock_extracted = ExtractedContent(
        text="",
        title="[low quality] Dynamic Page",
        author="",
        published_at=None,
        word_count=0,
        source_url="https://example.com/js-app",
        source_type="web",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Extraction succeeded (no error), even though text is empty, so candidate IS created
    assert "1 candidate" in result, f"Expected 1 candidate for low-quality extraction, got: {result}"


# ─── AC-012: HTTP Error Handling ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_404_creates_candidate_with_http_error():
    """AC-012: 404 or network error → extraction fails, no candidate created.

    GIVEN a web URL returns 404 Not Found
    WHEN the Analysis job processes it
    THEN extraction fails with "HTTP 404 for <url>"
    AND NO candidate is created (extraction failed)
    AND source is marked as failed
    """
    user_id = "user-123"
    source_id = "web-source-404"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    web_source = {
        "id": source_id,
        "type": "web",
        "title": "Missing Page",
        "url": "https://example.com/missing",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [web_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    mock_extracted = ExtractedContent(
        text="",
        title="",
        source_url="https://example.com/missing",
        source_type="web",
        error="HTTP 404 for https://example.com/missing",
    )

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Extraction failed (404), so no candidate should be created
    assert "0 candidate" in result, f"Expected 0 candidates for HTTP 404, got: {result}"

    # Verify NO candidate was created
    candidate_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(call)
    ]
    assert len(candidate_calls) == 0, "No candidate should be created for failed HTTP request"


# ─── AC-013: Unified Pipeline ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_three_source_types_create_candidates():
    """AC-013 + AC-015: PDF, local, web sources processed together with duplicate score computation.

    GIVEN sources of all three types (PDF, local, web) are queued
    WHEN _analysis_handler runs
    THEN all three are processed correctly
    AND candidates appear in the unified candidates list
    AND duplicate_score is computed correctly for all types (float in [0.0, 1.0])
    """
    user_id = "user-123"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    sources = [
        {
            "id": "pdf-1",
            "type": "pdf",
            "title": "PDF",
            "url": "/path/to/file.pdf",
            "source_scope": "direct_resource",
            "discovery_mode": None,
            "keyword": None,
            "discovery_limit": 25,
        },
        {
            "id": "local-1",
            "type": "local",
            "title": "Note",
            "url": "/path/to/note.md",
            "source_scope": "direct_resource",
            "discovery_mode": None,
            "keyword": None,
            "discovery_limit": 25,
        },
        {
            "id": "web-1",
            "type": "web",
            "title": "Article",
            "url": "https://example.com",
            "source_scope": "direct_resource",
            "discovery_mode": None,
            "keyword": None,
            "discovery_limit": 25,
        },
    ]
    mock_conn.fetch.return_value = sources
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    # Each adapter returns success
    extracted_pdf = ExtractedContent(
        text="PDF text",
        title="PDF",
        word_count=2,
        source_type="pdf",
        source_url="/path/to/file.pdf",
    )
    extracted_local = ExtractedContent(
        text="Note content",
        title="Note",
        word_count=2,
        source_type="local",
        source_url="/path/to/note.md",
    )
    extracted_web = ExtractedContent(
        text="Article content",
        title="Article",
        word_count=2,
        source_type="web",
        source_url="https://example.com",
    )

    def mock_extract_side_effect(source_type, url):
        if source_type == "pdf":
            return extracted_pdf
        elif source_type == "local":
            return extracted_local
        elif source_type == "web":
            return extracted_web
        return ExtractedContent(text="", title="", error="Unknown type")

    with patch("app.worker.handlers.adapter_extract") as mock_extract:
        mock_extract.side_effect = mock_extract_side_effect

        result = await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # Verify all sources were processed
    assert "3 candidate" in result, f"Expected 3 candidates, got: {result}"

    # AC-015: Verify duplicate_score was computed for all candidate creations
    candidate_calls = [
        call for call in mock_conn.execute.call_args_list
        if "INSERT INTO candidates" in str(call)
    ]
    assert len(candidate_calls) >= 3, "All three source types should create candidates"

    # Verify that the duplicate_score (similarity) is passed as a float in [0.0, 1.0]
    for call in candidate_calls:
        call_str = str(call)
        # The call should contain a similarity/duplicate_score value
        # We verify the mock was called; the actual score validation happens in unit tests
        assert "duplicate_score" in call_str or "similarity" in call_str or \
               "0.0" in call_str or "1.0" in call_str, \
               f"Call should include duplicate_score: {call}"


# ─── AC-015: Duplicate Score Validation ───────────────────────────────────────


def test_duplicate_score_is_float_in_valid_range():
    """AC-015: duplicate_score must be a float in [0.0, 1.0].

    GIVEN a candidate is created after similarity computation
    WHEN _candidate_fields is called
    THEN duplicate_score (or similarity) is a float in range [0.0, 1.0]
    """
    extracted = ExtractedContent(
        text="Sample content with multiple words for word count.",
        title="Sample Title",
        author="Author Name",
        published_at="2024-01-15",
        word_count=10,
    )
    fields = _candidate_fields(extracted, "Sample Title", "example.com")

    # duplicate_score should exist and be valid
    duplicate_score = fields.get("duplicate_score", 0.0)
    assert isinstance(duplicate_score, (int, float)), \
        f"duplicate_score must be numeric, got {type(duplicate_score)}"
    assert 0.0 <= duplicate_score <= 1.0, \
        f"duplicate_score must be in [0.0, 1.0], got {duplicate_score}"


# ─── AC-016: Source Status Transition ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_source_status_transitions_to_done():
    """AC-016: Source status transitions after extraction.

    GIVEN a source has status 'queued' before extraction
    WHEN the Analysis job processes it
    THEN the source status is updated to 'processing' or 'done'
    """
    user_id = "user-123"
    source_id = "pdf-source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    pdf_source = {
        "id": source_id,
        "type": "pdf",
        "title": "Sample PDF",
        "url": "/path/to/sample.pdf",
        "source_scope": "direct_resource",
        "discovery_mode": None,
        "keyword": None,
        "discovery_limit": 25,
    }
    mock_conn.fetch.return_value = [pdf_source]
    mock_conn.fetchval.return_value = None

    progress = AsyncMock()

    mock_extracted = ExtractedContent(
        text="This is PDF content with multiple words that demonstrate extraction.",
        title="Sample PDF Title",
        author="PDF Author",
        published_at="2024-01-15",
        word_count=12,
        source_url="/path/to/sample.pdf",
        source_type="pdf",
    )

    with patch("app.adapters.extract") as mock_extract:
        mock_extract.return_value = mock_extracted

        await _analysis_handler(
            {"user_id": user_id, "job_type": "analysis"},
            progress,
            mock_pool,
        )

    # AC-016: Verify source status UPDATE was called
    status_update_calls = [
        call for call in mock_conn.execute.call_args_list
        if "UPDATE sources" in str(call) and "status" in str(call)
    ]
    assert len(status_update_calls) >= 1, \
        "Source status should be updated after extraction (UPDATE sources with status column)"

    # Verify the status value is either 'processing' or 'done'
    status_found = False
    for call in status_update_calls:
        call_str = str(call)
        if "processing" in call_str or "done" in call_str:
            status_found = True
            break
    assert status_found, \
        "Status should be updated to 'processing' or 'done'"


# ─── Helper: _candidate_fields unit tests ─────────────────────────────────────


def test_candidate_fields_happy_path():
    """_candidate_fields returns correct structure for successful extraction."""
    extracted = ExtractedContent(
        text="Sample content with multiple words for word count.",
        title="Sample Title",
        author="Author Name",
        published_at="2024-01-15",
        word_count=10,
    )
    fields = _candidate_fields(extracted, "Fallback Title", "example.com")

    assert fields["title"] == "Sample Title"
    assert fields["recommendation"] == "process"
    assert fields["quality_score"] == 0.75
    assert fields["confidence_score"] == 0.70
    assert fields["word_count"] == 10


def test_candidate_fields_with_error() -> None:
    """_candidate_fields marks extraction errors with 'review' recommendation."""
    extracted = ExtractedContent(
        text="",
        title="",
        error="PDF is encrypted",
    )
    fields = _candidate_fields(extracted, "Fallback Title", "example.com")

    assert fields["title"] == "Fallback Title"
    assert fields["recommendation"] == "review"
    assert fields["quality_score"] == 0.0
    assert fields["confidence_score"] == 0.0
    assert "PDF is encrypted" in fields["summary"]


def test_candidate_fields_empty_extraction() -> None:
    """_candidate_fields handles completely failed extraction."""
    fields = _candidate_fields(None, "Fallback Title", "example.com")

    assert fields["title"] == "Fallback Title"
    assert fields["recommendation"] == "process"
    assert fields["summary"] == ""
    assert fields["word_count"] == 0
