"""Tests for _create_candidate_with_evidence function.

Tests verify:
- Pending candidates block duplicate creation
- Approved candidates DO NOT block re-discovery (new behavior after the fix)
- Rejected candidates DO NOT block re-discovery
- New candidates are inserted with correct fields
- Evidence (source_extractions) is persisted when extraction succeeds
- Evidence is not persisted when extraction has errors
- Function returns True on new candidate, False on dedup hit
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.adapters.base import ExtractedContent
from app.worker.handlers import _create_candidate_with_evidence


class AsyncContextManagerMock:
    """Mock that works as an async context manager."""

    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_create_candidate_pending_candidate_blocks_dedup():
    """Pending candidates block duplicate creation."""
    user_id = "user-123"
    source_url = "https://example.com/article"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # Mock: existing pending candidate found
    mock_conn.fetchval.return_value = 1

    fields = {
        "title": "Test Article",
        "published_at": "2024-01-01",
        "recommendation": "high",
        "quality_score": 0.8,
        "confidence_score": 0.9,
        "summary": "A test article",
        "word_count": 100,
    }

    result = await _create_candidate_with_evidence(
        mock_pool, user_id, "source-1", source_url, "example.com", fields, None
    )

    # Should return False (no new candidate created)
    assert result is False
    # Should NOT call INSERT
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_create_candidate_approved_candidate_allows_rediscovery():
    """FIXED: Approved candidates DO NOT block re-discovery.

    After the fix, approved candidates are allowed to be re-discovered
    when the user explicitly triggers discovery again (e.g., Run Discovery Now).
    The dedup query now only checks for pending status, not approved.
    """
    user_id = "user-123"
    source_url = "https://example.com/article"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # Mock: NO existing pending candidate found
    # (the approved one is filtered out by the new query: status = 'pending' only)
    mock_conn.fetchval.return_value = None

    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.2

        fields = {
            "title": "Test Article",
            "published_at": "2024-01-01",
            "recommendation": "high",
            "quality_score": 0.8,
            "confidence_score": 0.9,
            "summary": "A test article",
            "word_count": 100,
        }

        result = await _create_candidate_with_evidence(
            mock_pool, user_id, "source-1", source_url, "example.com", fields, None
        )

    # Should return True (new candidate WAS created, even though an approved one exists)
    assert result is True
    # Should have called execute once (INSERT into candidates)
    assert mock_conn.execute.call_count == 1
    # Verify the INSERT statement
    call_args = mock_conn.execute.call_args
    assert "INSERT INTO candidates" in call_args[0][0]


@pytest.mark.asyncio
async def test_create_candidate_rejected_candidate_allows_rediscovery():
    """FIXED: Rejected candidates DO NOT block re-discovery.

    This is the key fix: after rejecting a source, running discovery again
    should allow the same source to be re-discovered as a new candidate.
    The query now checks: status IN ('pending', 'approved') only.
    Rejected candidates do not match this condition, so re-creation is allowed.
    """
    user_id = "user-123"
    source_url = "https://example.com/article"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # Mock: NO existing pending/approved candidate found
    # (the rejected one is filtered out by the new query)
    mock_conn.fetchval.return_value = None

    # Mock: _compute_candidate_similarity call
    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.2

        fields = {
            "title": "Test Article",
            "published_at": "2024-01-01",
            "recommendation": "high",
            "quality_score": 0.8,
            "confidence_score": 0.9,
            "summary": "A test article",
            "word_count": 100,
        }

        result = await _create_candidate_with_evidence(
            mock_pool, user_id, "source-1", source_url, "example.com", fields, None
        )

    # Should return True (new candidate WAS created)
    assert result is True
    # Should have called execute once (INSERT into candidates)
    assert mock_conn.execute.call_count == 1
    # Verify the INSERT statement
    call_args = mock_conn.execute.call_args
    assert "INSERT INTO candidates" in call_args[0][0]


@pytest.mark.asyncio
async def test_create_candidate_new_candidate_inserted():
    """New candidate is inserted with all required fields."""
    user_id = "user-123"
    source_url = "https://example.com/article"
    source_id = "source-1"
    domain = "example.com"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # No existing candidate
    mock_conn.fetchval.return_value = None

    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.15

        fields = {
            "title": "Interesting Article",
            "published_at": "2024-01-15",
            "recommendation": "medium",
            "quality_score": 0.75,
            "confidence_score": 0.85,
            "summary": "This is a test",
            "word_count": 250,
        }

        result = await _create_candidate_with_evidence(
            mock_pool, user_id, source_id, source_url, domain, fields, None
        )

    assert result is True
    # Verify INSERT was called
    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    sql = call_args[0][0]
    values = call_args[0][1:]

    assert "INSERT INTO candidates" in sql
    # Verify some key values were inserted
    assert user_id in values
    assert source_id in values
    assert "Interesting Article" in values
    assert source_url in values
    assert "pending" in values  # Default status


@pytest.mark.asyncio
async def test_create_candidate_with_extracted_content_persists_evidence():
    """When extraction succeeds, evidence (source_extractions) is persisted."""
    user_id = "user-123"
    source_url = "https://youtube.com/watch?v=abc123"
    source_id = "source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # No existing candidate
    mock_conn.fetchval.return_value = None

    extracted = ExtractedContent(
        text="This is extracted content from a video.",
        title="Video Title",
        author="John Doe",
        published_at="2024-01-20",
        word_count=6,
        timestamps=[{"seconds": 0, "text": "intro"}, {"seconds": 10, "text": "main"}],
    )

    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.0

        fields = {
            "title": "Video Title",
            "published_at": "2024-01-20",
            "recommendation": "high",
            "quality_score": 0.9,
            "confidence_score": 0.95,
            "summary": "Great video",
            "word_count": 100,
        }

        result = await _create_candidate_with_evidence(
            mock_pool, user_id, source_id, source_url, "youtube.com", fields, extracted
        )

    assert result is True
    # Should call execute twice: INSERT candidates + INSERT source_extractions
    assert mock_conn.execute.call_count == 2

    calls = mock_conn.execute.call_args_list
    # First call: INSERT INTO candidates
    assert "INSERT INTO candidates" in calls[0][0][0]
    # Second call: INSERT INTO source_extractions
    assert "INSERT INTO source_extractions" in calls[1][0][0]


@pytest.mark.asyncio
async def test_create_candidate_with_extraction_error_skips_evidence():
    """When extraction has error, evidence is NOT persisted."""
    user_id = "user-123"
    source_url = "https://example.com/article"
    source_id = "source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # No existing candidate
    mock_conn.fetchval.return_value = None

    # Extracted content with error flag set
    extracted = ExtractedContent(
        text=None,
        title="Article",
        author=None,
        published_at=None,
        word_count=0,
        error=True,  # Error flag
    )

    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.0

        fields = {
            "title": "Article",
            "published_at": "2024-01-01",
            "recommendation": "low",
            "quality_score": 0.5,
            "confidence_score": 0.6,
            "summary": "Article",
            "word_count": 50,
        }

        result = await _create_candidate_with_evidence(
            mock_pool, user_id, source_id, source_url, "example.com", fields, extracted
        )

    assert result is True
    # Should call execute only ONCE (INSERT candidates, NOT source_extractions)
    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    assert "INSERT INTO candidates" in call_args[0][0]


@pytest.mark.asyncio
async def test_create_candidate_with_empty_extracted_text_skips_evidence():
    """When extracted text is empty, evidence is NOT persisted."""
    user_id = "user-123"
    source_url = "https://example.com/page"
    source_id = "source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # No existing candidate
    mock_conn.fetchval.return_value = None

    # Extracted content with empty text
    extracted = ExtractedContent(
        text="",  # Empty
        title="Page",
        word_count=0,
    )

    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.0

        fields = {
            "title": "Page",
            "published_at": "2024-01-01",
            "recommendation": "low",
            "quality_score": 0.4,
            "confidence_score": 0.5,
            "summary": "Page",
            "word_count": 30,
        }

        result = await _create_candidate_with_evidence(
            mock_pool, user_id, source_id, source_url, "example.com", fields, extracted
        )

    assert result is True
    # Should call execute only ONCE (INSERT candidates, NOT source_extractions)
    # because extracted.text is empty (falsy)
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_candidate_duplicate_score_computed():
    """Candidate duplicate score is computed via _compute_candidate_similarity."""
    user_id = "user-123"
    source_url = "https://example.com/blog"
    source_id = "source-1"

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # No existing candidate
    mock_conn.fetchval.return_value = None

    with patch(
        "app.worker.handlers._compute_candidate_similarity", new_callable=AsyncMock
    ) as mock_similarity:
        mock_similarity.return_value = 0.42  # Specific score

        fields = {
            "title": "Blog Post",
            "published_at": "2024-01-25",
            "recommendation": "high",
            "quality_score": 0.85,
            "confidence_score": 0.88,
            "summary": "Interesting blog post",
            "word_count": 500,
        }

        await _create_candidate_with_evidence(
            mock_pool, user_id, source_id, source_url, "example.com", fields, None
        )

    # Verify similarity computation was called
    mock_similarity.assert_called_once()
    call_args = mock_similarity.call_args
    assert call_args[0][0] == mock_pool  # pool
    assert call_args[0][1] == user_id
    # text or summary should be in the call
    assert "Blog Post" in str(call_args) or "Interesting blog post" in str(call_args)

    # Verify the score was inserted into the candidate row
    insert_call = mock_conn.execute.call_args
    inserted_values = insert_call[0][1:]
    # The duplicate_score should be in the inserted values
    assert 0.42 in inserted_values
