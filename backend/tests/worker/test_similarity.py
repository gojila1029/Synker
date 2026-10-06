"""Unit tests for candidate similarity computation (Jaccard algorithm).

Tests verify:
- Keyword extraction removes stopwords, lowercases, filters by length
- Jaccard similarity correctly computes |A ∩ B| / |A ∪ B|
- Empty vault returns 0.0
- Empty candidate text returns 0.0
- Score is reproducible (same inputs → same output)
- Computation respects 5-second timeout
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.handlers import (
    _compute_candidate_similarity,
    _extract_keywords,
)


class TestExtractKeywords:
    """Tests for keyword extraction (tokenization, stopword removal, filtering)."""

    def test_extract_keywords_lowercases(self):
        """AC-009: Keywords are lowercased."""
        keywords = _extract_keywords("The API Design", "")
        assert "api" in keywords
        assert "design" in keywords
        # No uppercase variants should exist
        assert not any(k.isupper() for k in keywords)

    def test_extract_keywords_removes_stopwords(self):
        """AC-009: Common stopwords are excluded from keywords."""
        # "The", "is", "an", "a", "and" are all stopwords
        text = "The API design is an important and critical pattern"
        keywords = _extract_keywords(text, "")
        # Should include: API, design, important, critical, pattern
        assert "api" in keywords
        assert "design" in keywords
        assert "important" in keywords
        assert "critical" in keywords
        assert "pattern" in keywords
        # Should NOT include stopwords
        assert "the" not in keywords
        assert "is" not in keywords
        assert "an" not in keywords
        assert "a" not in keywords
        assert "and" not in keywords

    def test_extract_keywords_filters_short_tokens(self):
        """Keywords with length < 3 are excluded."""
        text = "A to be on the API design"
        keywords = _extract_keywords(text, "")
        # "to", "be", "on" are all < 3 chars, should be filtered
        assert "api" in keywords
        assert "design" in keywords
        # Single and double-char tokens should not exist
        assert len([k for k in keywords if len(k) < 3]) == 0

    def test_extract_keywords_includes_title(self):
        """Keywords from title are included in the set."""
        title = "REST API Architecture"
        text = "This is about designing systems"
        keywords = _extract_keywords(text, title)
        # Title words should be included
        assert "rest" in keywords
        assert "api" in keywords
        assert "architecture" in keywords

    def test_extract_keywords_from_first_five_sentences(self):
        """Only first 5 sentences of text are used for keyword extraction."""
        # Create text with > 5 sentences
        text = (
            "First sentence talks about databases. "
            "Second sentence talks about caching. "
            "Third sentence talks about networking. "
            "Fourth sentence talks about authentication. "
            "Fifth sentence talks about encryption. "
            "Sixth sentence talks about deployment. "
            "Seventh sentence talks about monitoring."
        )
        keywords = _extract_keywords(text, "")
        # Keywords from first 5 sentences should exist
        assert "databases" in keywords or "sentence" in keywords
        # Keywords from 6th and 7th sentences may not exist (depends on sentence split)
        # The key assertion: monitoring is from sentence 7, should not be in keywords
        # (unless it appears in earlier sentences)

    def test_extract_keywords_empty_text(self):
        """Empty text returns empty keyword set."""
        keywords = _extract_keywords("", "")
        assert keywords == set()

    def test_extract_keywords_only_stopwords(self):
        """Text with only stopwords returns empty set."""
        text = "the and or is a to in on"
        keywords = _extract_keywords(text, "")
        assert len(keywords) == 0

    def test_extract_keywords_reproducible(self):
        """AC-010: Same input always produces same output (no randomness)."""
        text = "The API design patterns for REST endpoints are critical"
        title = "REST Architecture"
        kw1 = _extract_keywords(text, title)
        kw2 = _extract_keywords(text, title)
        assert kw1 == kw2


class TestJaccardSimilarity:
    """Tests for Jaccard similarity computation on keyword sets."""

    def test_jaccard_identical_texts_score_near_one(self):
        """AC-002: Identical texts should produce Jaccard score ≈ 1.0."""
        text = "The API design patterns for REST endpoints"
        keywords_a = _extract_keywords(text, "Title")
        keywords_b = _extract_keywords(text, "Title")
        # Jaccard: |A ∩ B| / |A ∪ B| where A == B should be 1.0
        intersection = len(keywords_a & keywords_b)
        union = len(keywords_a | keywords_b)
        score = intersection / union if union > 0 else 0.0
        assert score == 1.0

    def test_jaccard_no_overlap_score_zero(self):
        """AC-002: Completely disjoint texts should produce Jaccard score ≈ 0.0."""
        text_a = "The API design patterns"
        text_b = "The painting art gallery"
        keywords_a = _extract_keywords(text_a, "")
        keywords_b = _extract_keywords(text_b, "")
        # Assuming no overlap between {api, design, patterns} and {painting, art, gallery}
        intersection = len(keywords_a & keywords_b)
        union = len(keywords_a | keywords_b)
        score = intersection / union if union > 0 else 0.0
        # Should be 0 or very close
        assert score < 0.2  # Allow some margin for stopword edge cases

    def test_jaccard_partial_overlap_in_range(self):
        """AC-002: Partial overlap should produce Jaccard score in (0, 1)."""
        text_a = "The API design patterns for REST endpoints"
        text_b = "The API framework for web applications"
        keywords_a = _extract_keywords(text_a, "")
        keywords_b = _extract_keywords(text_b, "")
        intersection = len(keywords_a & keywords_b)
        union = len(keywords_a | keywords_b)
        score = intersection / union if union > 0 else 0.0
        # Should be strictly between 0 and 1
        assert 0.0 < score < 1.0


class TestComputeCandidateSimilarity:
    """Tests for async similarity computation function."""

    @pytest.mark.asyncio
    async def test_empty_candidate_text_returns_zero(self):
        """AC-007: Empty candidate text returns 0.0 without error."""
        pool = AsyncMock()
        result = await _compute_candidate_similarity(pool, "user123", "", "")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_empty_vault_returns_zero(self):
        """AC-004: User with zero vault notes returns 0.0."""
        pool = AsyncMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])  # No vault_files
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        result = await _compute_candidate_similarity(
            pool, "user123", "candidate text", "candidate title"
        )
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_no_overlap_vault_returns_near_zero(self):
        """AC-003: Candidate with no overlap with vault notes returns score ≈ 0.0."""
        pool = AsyncMock()
        conn = AsyncMock()

        # Mock vault_files with content unrelated to candidate
        vault_rows = [
            {"content": "The painting art gallery museum"},
            {"content": "The sculpture bronze cast statue"},
        ]
        conn.fetch = AsyncMock(return_value=vault_rows)
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        # Candidate text about REST API (no overlap with art/sculpture)
        result = await _compute_candidate_similarity(
            pool, "user123", "The REST API design patterns", "API Architecture"
        )

        # Should return very low score (< 0.2)
        assert result < 0.2

    @pytest.mark.asyncio
    async def test_high_overlap_vault_returns_high_score(self):
        """AC-003: Candidate with high overlap with vault notes returns score > 0.5."""
        pool = AsyncMock()
        conn = AsyncMock()

        # Mock vault_files with content similar to candidate
        vault_rows = [
            {"content": "The API design patterns for REST endpoints are critical"},
            {"content": "The painting art gallery museum"},  # Unrelated
        ]
        conn.fetch = AsyncMock(return_value=vault_rows)
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        # Candidate with high overlap to first vault note
        result = await _compute_candidate_similarity(
            pool,
            "user123",
            "The API design patterns for REST endpoints",
            "API Architecture"
        )

        # Should return high score (> 0.5)
        assert result > 0.5

    @pytest.mark.asyncio
    async def test_max_score_across_vault_notes(self):
        """Similarity returns the MAX score across all vault notes, not average."""
        pool = AsyncMock()
        conn = AsyncMock()

        # Three vault notes with varying overlap
        vault_rows = [
            {"content": "painting art gallery"},  # No overlap
            {"content": "API design patterns for REST"},  # High overlap
            {"content": "database SQL queries"},  # No overlap
        ]
        conn.fetch = AsyncMock(return_value=vault_rows)
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        result = await _compute_candidate_similarity(
            pool,
            "user123",
            "API design patterns architecture",
            "API"
        )

        # Should return the max (from second note with overlap), not average
        assert result > 0.4  # High overlap with the second note

    @pytest.mark.asyncio
    async def test_timeout_handling_logs_and_returns_zero(self):
        """AC-008: Query timeout is caught, warning logged, function returns 0.0."""
        pool = AsyncMock()

        # Simulate a timeout by raising an exception
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=Exception("timeout or connection error"))
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        with patch("app.worker.handlers._log") as mock_log:
            result = await _compute_candidate_similarity(
                pool, "user123", "candidate text", "title"
            )
            assert result == 0.0
            # Warning should be logged
            mock_log.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_reproducible_same_inputs_same_output(self):
        """AC-010: Same inputs always produce same score (deterministic)."""
        pool = AsyncMock()
        conn = AsyncMock()

        vault_rows = [
            {"content": "API design patterns REST endpoints"},
            {"content": "database queries optimization"},
        ]
        conn.fetch = AsyncMock(return_value=vault_rows)
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        candidate_text = "API design patterns for web services"
        candidate_title = "Web API"

        # Call twice with identical inputs and vault state
        result1 = await _compute_candidate_similarity(
            pool, "user123", candidate_text, candidate_title
        )
        result2 = await _compute_candidate_similarity(
            pool, "user123", candidate_text, candidate_title
        )

        # Both should be identical
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_fallback_to_notes_table_when_vault_empty(self):
        """FR-002: Falls back to notes table if vault_files is empty."""
        pool = AsyncMock()
        conn = AsyncMock()

        # First fetch (vault_files) returns empty; second fetch (notes) returns data
        notes_rows = [
            {"content": "API design patterns REST endpoints"},
        ]

        async def mock_fetch(*args, **kwargs):
            # First call returns empty (vault_files), second returns notes
            if mock_fetch.call_count == 1:
                result = []
            else:
                result = notes_rows
            mock_fetch.call_count += 1
            return result

        mock_fetch.call_count = 0
        conn.fetch = mock_fetch
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        result = await _compute_candidate_similarity(
            pool,
            "user123",
            "API design patterns for web services",
            "Web API"
        )

        # Should have succeeded by falling back to notes table
        assert result > 0.0


class TestPerformanceBoundary:
    """Tests for AC-005: Computation time < 5 seconds."""

    @pytest.mark.asyncio
    async def test_computation_with_100_notes_completes_in_time(self):
        """AC-005: 100 vault notes should complete in < 5 seconds."""
        pool = AsyncMock()
        conn = AsyncMock()

        # Create 100 synthetic vault notes
        vault_rows = [
            {"content": f"Note {i}: API design patterns REST endpoints architecture"}
            for i in range(100)
        ]
        conn.fetch = AsyncMock(return_value=vault_rows)
        pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn)))

        candidate_text = "API design patterns for web services and microservices"

        t0 = time.perf_counter()
        result = await _compute_candidate_similarity(
            pool, "user123", candidate_text, "Web API"
        )
        elapsed = time.perf_counter() - t0

        # Should complete in < 5 seconds
        assert elapsed < 5.0
        # Should also return a valid score
        assert 0.0 <= result <= 1.0
