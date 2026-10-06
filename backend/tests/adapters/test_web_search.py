"""Tests for website search adapter."""
import pytest

from app.adapters.web_search import (
    WebSearchResult,
    WebSearchResults,
    _is_blocked_url,
    _normalize_url,
    search_websites,
)


@pytest.mark.unit
def test_is_blocked_url_localhost() -> None:
    """Localhost URLs should be blocked (SSRF prevention)."""
    assert _is_blocked_url("http://localhost:8000/api")
    assert _is_blocked_url("http://127.0.0.1:8000/api")
    assert _is_blocked_url("http://[::1]/api")


@pytest.mark.unit
def test_is_blocked_url_private_ranges() -> None:
    """RFC 1918 private IP ranges should be blocked."""
    assert _is_blocked_url("http://10.0.0.1/api")
    assert _is_blocked_url("http://192.168.1.1/api")
    assert _is_blocked_url("http://172.16.0.1/api")


@pytest.mark.unit
def test_is_blocked_url_link_local() -> None:
    """Link-local addresses should be blocked."""
    assert _is_blocked_url("http://169.254.169.254/api")


@pytest.mark.unit
def test_is_blocked_url_public() -> None:
    """Public URLs should not be blocked."""
    assert not _is_blocked_url("https://example.com")
    assert not _is_blocked_url("https://www.google.com")


@pytest.mark.unit
def test_normalize_url_removes_fragment() -> None:
    """normalize_url should remove fragments and trailing slashes."""
    url = "https://example.com/path#section"
    normalized = _normalize_url(url)
    assert "#" not in normalized
    assert normalized == "https://example.com/path"


@pytest.mark.unit
def test_normalize_url_trailing_slash() -> None:
    """normalize_url should remove trailing slashes."""
    url = "https://example.com/path/"
    normalized = _normalize_url(url)
    assert normalized == "https://example.com/path"


@pytest.mark.unit
def test_normalize_url_idempotent() -> None:
    """normalize_url should be idempotent."""
    url = "https://example.com/path"
    assert _normalize_url(url) == _normalize_url(_normalize_url(url))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_websites_empty_query() -> None:
    """Empty queries should be handled gracefully."""
    result = await search_websites("", limit=5)
    assert isinstance(result, WebSearchResults)
    # Result may be error or empty, but structure should be correct


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_websites_returns_results() -> None:
    """Valid search should return structured results."""
    result = await search_websites("test", limit=3)
    assert isinstance(result, WebSearchResults)
    assert isinstance(result.results, list)
    if result.results:
        for item in result.results:
            assert isinstance(item, WebSearchResult)
            assert item.url
            assert item.title
            # URLs should not be blocked
            assert not _is_blocked_url(item.url)


@pytest.mark.unit
def test_web_search_result_structure() -> None:
    """WebSearchResult should have required fields."""
    result = WebSearchResult(
        url="https://example.com",
        title="Example Page",
    )
    assert result.url == "https://example.com"
    assert result.title == "Example Page"
    assert result.snippet == ""


@pytest.mark.unit
def test_web_search_results_error() -> None:
    """WebSearchResults should support error state."""
    result = WebSearchResults(
        error="Search unavailable",
        error_code="SEARCH_UNAVAILABLE",
    )
    assert result.error == "Search unavailable"
    assert result.error_code == "SEARCH_UNAVAILABLE"
    assert len(result.results) == 0


@pytest.mark.unit
def test_web_search_results_access_denied() -> None:
    """WebSearchResults should support ACCESS_DENIED error."""
    result = WebSearchResults(
        error="Access denied to site",
        error_code="ACCESS_DENIED",
    )
    assert result.error_code == "ACCESS_DENIED"
