"""Web page source adapter.

Fetches HTML with httpx and extracts clean article text with trafilatura.
Falls back to a basic title extraction when trafilatura cannot parse the page.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from app.adapters.base import ExtractedContent, ExtractionError, SourceAdapter

_OG_AUTHOR = re.compile(
    r'<meta[^>]+property=["\'](og:article:author|article:author)["\'"]'
    r'[^>]+content=["\'](.*?)["\'"]',
    re.I,
)
_OG_DATE = re.compile(
    r'<meta[^>]+property=["\'](og:article:published_time|article:published_time)["\'"]'
    r'[^>]+content=["\'](.*?)["\'"]',
    re.I,
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _og_meta(pattern: re.Pattern[str], html: str) -> str | None:
    """Extract Open Graph meta tag value."""
    m = pattern.search(html)
    return m.group(2).strip() if m else None


def _html_title(html: str) -> str | None:
    """Extract title from <title> tag, stripping any HTML tags inside."""
    m = _TITLE.search(html)
    if m:
        raw = m.group(1).strip()
        # Strip basic HTML tags inside title
        return re.sub(r"<[^>]+>", "", raw).strip() or None
    return None


def _is_safe_url(url: str) -> bool:
    """Check if URL is safe from SSRF attacks.

    Validates:
    - Scheme is http or https only (SEC-007)
    - Resolved IP is not private, loopback, link-local, or reserved (SEC-008)

    Returns False if validation fails, True if safe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname or ""
    if not hostname:
        return False

    try:
        # Resolve hostname to IP address(es)
        addrs = socket.getaddrinfo(hostname, None)
        for addr in addrs:
            ip = ipaddress.ip_address(addr[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
                return False
    except (socket.gaierror, ValueError):
        # Cannot resolve or invalid IP = allow (fail open for DNS issues)
        return True

    return True


class WebAdapter(SourceAdapter):
    """Extract clean article text from a web page URL."""

    async def extract(self, url: str) -> ExtractedContent:
        """Fetch and extract content from a web page."""
        if not _is_safe_url(url):
            raise ExtractionError("URL rejected: private or reserved IP address")

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "Synker/1.0 (+https://github.com/synker)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as exc:
            raise ExtractionError(
                f"HTTP {exc.response.status_code} for {url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ExtractionError(f"Cannot reach {url}: {exc}") from exc

        try:
            import trafilatura
            text = trafilatura.extract(
                html,
                include_tables=True,
                output_format="txt",
                url=url,
            )
            meta = trafilatura.extract_metadata(html, default_url=url)
            title = (meta.title if meta else None) or _html_title(html) or url
            author = (meta.author if meta else None) or _og_meta(_OG_AUTHOR, html) or ""
            published_at = (meta.date if meta else None) or _og_meta(_OG_DATE, html)
        except ImportError:
            text = None
            title = _html_title(html) or url
            author = _og_meta(_OG_AUTHOR, html) or ""
            published_at = _og_meta(_OG_DATE, html)

        if not text:
            title = f"[low quality] {title}"
            text = ""

        return ExtractedContent(
            source_url=url,
            text=text,
            title=title,
            source_type="web",
            word_count=len(text.split()) if text else 0,
            author=author,
            published_at=published_at,
        )


async def extract(url: str) -> ExtractedContent:
    """Functional wrapper for backward compatibility."""
    return await WebAdapter().extract(url)
