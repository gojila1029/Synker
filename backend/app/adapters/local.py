"""Local file source adapter.

Reads .txt and .md files directly; delegates .pdf to PdfAdapter.
Enforces path traversal safety (rejects paths containing ..).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from app.adapters.base import ExtractedContent, ExtractionError, SourceAdapter

_SUPPORTED = {".txt", ".md", ".pdf"}


class LocalAdapter(SourceAdapter):
    """Extract content from a local file path."""

    async def extract(self, url: str) -> ExtractedContent:
        path = Path(url)

        if ".." in path.parts:
            raise ExtractionError(f"Path traversal rejected: {url}")

        if not path.exists():
            raise ExtractionError(f"File not found: {url}")

        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED:
            raise ExtractionError(f"Unsupported file type: {suffix!r}")

        if suffix == ".pdf":
            from app.adapters.pdf import PdfAdapter
            return await PdfAdapter().extract(url)

        text = path.read_text(encoding="utf-8")
        try:
            mtime = path.stat().st_mtime
            published_at = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.UTC
            ).isoformat()
        except OSError:
            published_at = None

        return ExtractedContent(
            source_url=url,
            text=text,
            title=path.stem,
            source_type="local",
            word_count=len(text.split()),
            published_at=published_at,
        )


async def extract(url: str) -> ExtractedContent:
    """Functional wrapper for backward compatibility."""
    return await LocalAdapter().extract(url)
