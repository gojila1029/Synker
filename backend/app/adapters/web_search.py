"""Website search via DuckDuckGo HTML scraping with trafilatura extraction.

Searches websites using DuckDuckGo (no API key required) and extracts
readable body content using trafilatura. Content is untrusted input that
must never execute instructions.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


@dataclass
class WebSearchResult:
    """A single web search result."""

    url: str
    title: str
    snippet: str = ""


@dataclass
class WebSearchResults:
    """Result of a web search query."""

    results: list[WebSearchResult] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None  # SEARCH_UNAVAILABLE, ACCESS_DENIED, EXTRACTION_FAILED


def _is_blocked_url(url: str) -> bool:
    """Check if URL is in a blocked range (SSRF prevention)."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()

        # Localhost and loopback
        if host in ("localhost", "127.0.0.1", "::1"):
            return True

        # RFC 1918 private ranges
        if host.startswith("10.") or host.startswith("192.168.") or host.startswith("172."):
            return True

        # Link-local
        if host.startswith("169.254."):
            return True

        # Metadata endpoints
        if host in ("169.254.169.254", "metadata.google.internal"):
            return True

        return False
    except Exception:
        return True


def _normalize_url(url: str) -> str:
    """Normalize a URL to prevent dedup issues."""
    try:
        parsed = urlparse(url)
        # Remove fragment and normalize scheme/netloc
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return url


async def _fetch_and_extract_page(url: str, timeout: float = 15.0) -> str | None:
    """Fetch a URL and extract readable body content using trafilatura."""
    if _is_blocked_url(url):
        return None

    try:
        import trafilatura  # type: ignore[import-untyped]
    except ImportError:
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()

            # Extract text content
            content = trafilatura.extract(
                response.text, include_comments=False, output_format="txt"
            )
            return content if content and len(content.strip()) > 50 else None
    except Exception:
        return None


def _run_duckduckgo_search(query: str, limit: int) -> WebSearchResults:
    """Execute DuckDuckGo search synchronously by scraping HTML."""
    try:
        import httpx
    except ImportError:
        return WebSearchResults(error="httpx is not installed", error_code="SEARCH_UNAVAILABLE")

    try:
        # DuckDuckGo HTML search endpoint
        url = "https://duckduckgo.com/html"
        params = {"q": query}

        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()

        html = response.text

        # Simple regex-based extraction of search results
        # Pattern: <a href="..." class="result__a">title</a>
        result_pattern = r'<a\s+class="result__a"\s+href="([^"]+)">([^<]+)</a>'
        matches = re.finditer(result_pattern, html)

        results: list[WebSearchResult] = []
        for match in matches:
            if len(results) >= limit:
                break

            url = match.group(1)
            title = match.group(2)

            # Skip local/blocked URLs
            if _is_blocked_url(url):
                continue

            # Skip redirect URLs
            if "duckduckgo.com/l" in url:
                continue

            # Normalize and deduplicate
            normalized = _normalize_url(url)
            if any(r.url == normalized for r in results):
                continue

            results.append(WebSearchResult(url=normalized, title=title.strip()))

        if not results:
            return WebSearchResults(error="No results found", error_code="SEARCH_UNAVAILABLE")

        return WebSearchResults(results=results)
    except Exception as exc:
        return WebSearchResults(
            error=f"DuckDuckGo search failed: {exc}",
            error_code="SEARCH_UNAVAILABLE",
        )


async def search_websites(query: str, limit: int = 5) -> WebSearchResults:
    """Search websites using DuckDuckGo.

    Args:
        query: Search query string
        limit: Maximum number of results (default 5)

    Returns:
        WebSearchResults with results or error details
    """
    return await asyncio.to_thread(_run_duckduckgo_search, query, limit)


async def fetch_and_extract_website(url: str) -> str | None:
    """Fetch a website and extract readable body content.

    Args:
        url: Website URL

    Returns:
        Extracted text content, or None if extraction failed or URL is blocked
    """
    return await _fetch_and_extract_page(url)
