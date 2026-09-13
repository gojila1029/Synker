"""Tests for the extraction handler."""
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

from app.adapters.base import ExtractionError, ExtractedContent
from app.worker.handlers import _extraction_handler


class AsyncContextManagerMock:
    """Mock that works as an async context manager."""

    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_extraction_handler_success():
    """Test successful extraction flow."""
    job = {
        "user_id": "user-123",
        "source_id": "source-456",
        "id": "job-789",
    }

    # Mock database connection
    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))

    # Mock source row
    mock_conn.fetchrow.return_value = {
        "id": "source-456",
        "type": "web",
        "url": "https://example.com",
        "title": "Example Article",
    }

    # Mock adapter
    mock_adapter = AsyncMock()
    mock_content = ExtractedContent(
        text="This is the extracted content with many words.",
        title="Example Article",
        author="John Doe",
        published_at="2024-01-01",
        word_count=8,
        timestamps=[{"seconds": 0, "text": "some text"}],
    )
    mock_adapter.extract.return_value = mock_content

    # Mock progress function
    progress_fn = AsyncMock()

    with patch("app.worker.handlers.get_adapter", return_value=mock_adapter):
        result = await _extraction_handler(job, progress_fn, mock_pool)

    assert "8 words extracted" in result
    assert "Example Article" in result
    assert mock_conn.execute.call_count == 2  # INSERT + UPDATE
    assert progress_fn.call_count >= 2  # Progress calls


@pytest.mark.asyncio
async def test_extraction_handler_missing_source_id():
    """Test handler when source_id is missing."""
    job = {
        "user_id": "user-123",
    }
    mock_pool = MagicMock()
    progress_fn = AsyncMock()

    result = await _extraction_handler(job, progress_fn, mock_pool)

    assert "No source_id" in result
    progress_fn.assert_called_with(100)


@pytest.mark.asyncio
async def test_extraction_handler_source_not_found():
    """Test handler when source doesn't exist."""
    job = {
        "user_id": "user-123",
        "source_id": "nonexistent",
    }

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))
    mock_conn.fetchrow.return_value = None

    progress_fn = AsyncMock()

    result = await _extraction_handler(job, progress_fn, mock_pool)

    assert "not found" in result


@pytest.mark.asyncio
async def test_extraction_handler_no_adapter():
    """Test handler when no adapter exists for source type."""
    job = {
        "user_id": "user-123",
        "source_id": "source-456",
    }

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))
    mock_conn.fetchrow.return_value = {
        "id": "source-456",
        "type": "unknown_type",
        "url": "https://example.com",
        "title": "Example",
    }

    progress_fn = AsyncMock()

    with patch("app.worker.handlers.get_adapter", return_value=None):
        result = await _extraction_handler(job, progress_fn, mock_pool)

    assert "No adapter" in result or "failed" in result


@pytest.mark.asyncio
async def test_extraction_handler_extraction_error():
    """Test handler when adapter raises ExtractionError."""
    job = {
        "user_id": "user-123",
        "source_id": "source-456",
    }

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))
    mock_conn.fetchrow.return_value = {
        "id": "source-456",
        "type": "web",
        "url": "https://example.com",
        "title": "Example",
    }

    mock_adapter = AsyncMock()
    mock_adapter.extract.side_effect = ExtractionError("Network error")

    progress_fn = AsyncMock()

    with patch("app.worker.handlers.get_adapter", return_value=mock_adapter):
        result = await _extraction_handler(job, progress_fn, mock_pool)

    assert "failed" in result or "Network error" in result


@pytest.mark.asyncio
async def test_extraction_handler_timestamps_serialization():
    """Test that timestamps are properly JSON-serialized."""
    job = {
        "user_id": "user-123",
        "source_id": "source-456",
    }

    mock_conn = AsyncMock()
    mock_pool = Mock()
    mock_pool.acquire = Mock(return_value=AsyncContextManagerMock(mock_conn))
    mock_conn.fetchrow.return_value = {
        "id": "source-456",
        "type": "youtube",
        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Video Title",
    }

    timestamps = [
        {"seconds": 0, "text": "intro"},
        {"seconds": 10, "text": "main content"},
    ]
    mock_content = ExtractedContent(
        text="transcribed content",
        title="Video Title",
        word_count=2,
        timestamps=timestamps,
    )

    mock_adapter = AsyncMock()
    mock_adapter.extract.return_value = mock_content

    progress_fn = AsyncMock()

    with patch("app.worker.handlers.get_adapter", return_value=mock_adapter):
        await _extraction_handler(job, progress_fn, mock_pool)

    # Verify the INSERT call included JSON-serialized timestamps
    calls = mock_conn.execute.call_args_list
    insert_call = [c for c in calls if "INSERT" in c[0][0]][0]
    timestamps_arg = insert_call[0][7]  # 8th parameter
    assert timestamps_arg == json.dumps(timestamps)
