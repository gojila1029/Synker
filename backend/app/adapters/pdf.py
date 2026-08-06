"""PDF source adapter.

Extracts text and metadata from PDF files using pdfplumber.
Accepts a local file path or an https URL.
"""
from __future__ import annotations

import io
from pathlib import Path

import httpx

from app.adapters.base import ExtractedContent, SourceAdapter


class PdfAdapter(SourceAdapter):
    """Extract text and metadata from a PDF source."""

    async def extract(self, url: str) -> ExtractedContent:
        if url.startswith("http://") or url.startswith("https://"):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.content
            except httpx.HTTPStatusError as exc:
                return ExtractedContent(
                    text="",
                    title="",
                    source_url=url,
                    source_type="pdf",
                    error=f"HTTP {exc.response.status_code} fetching PDF: {url}",
                )
            except httpx.HTTPError as exc:
                return ExtractedContent(
                    text="",
                    title="",
                    source_url=url,
                    source_type="pdf",
                    error=f"Cannot fetch PDF {url}: {exc}",
                )
        else:
            p = Path(url)
            if not p.exists():
                return ExtractedContent(
                    text="",
                    title="",
                    source_url=url,
                    source_type="pdf",
                    error=f"File not found: {url}",
                )
            data = p.read_bytes()

        return self._from_bytes(data, url)

    def _from_bytes(self, data: bytes, source_url: str) -> ExtractedContent:
        try:
            import pdfplumber
        except ImportError:
            return ExtractedContent(
                text="",
                title="",
                source_url=source_url,
                source_type="pdf",
                error="pdfplumber is not installed",
            )

        try:
            pdf = pdfplumber.open(io.BytesIO(data))
        except Exception as exc:
            exc_msg = str(exc).lower()
            if "password" in exc_msg or "encrypted" in exc_msg:
                error = "PDF is encrypted"
            else:
                error = f"Cannot open PDF: {exc}"
            return ExtractedContent(
                text="",
                title="",
                source_url=source_url,
                source_type="pdf",
                error=error,
            )

        with pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n\n".join(p for p in pages if p.strip())
            raw_meta = pdf.metadata or {}

        if not text.strip():
            return ExtractedContent(
                text="",
                title="",
                source_url=source_url,
                source_type="pdf",
                error="PDF contains no extractable text",
            )

        title = str(raw_meta.get("Title") or Path(source_url).stem or "Untitled PDF")
        author = str(raw_meta.get("Author")) if raw_meta.get("Author") else ""
        raw_date = raw_meta.get("CreationDate") or raw_meta.get("ModDate")
        published_at = _parse_pdf_date(raw_date) if raw_date else None

        return ExtractedContent(
            text=text,
            title=title,
            source_url=source_url,
            source_type="pdf",
            word_count=len(text.split()),
            author=author,
            published_at=published_at,
        )


def _parse_pdf_date(raw: str) -> str | None:
    """Convert PDF date string D:YYYYMMDDHHmmSS to ISO-8601 YYYY-MM-DD, best effort."""
    s = raw.lstrip("D:").replace("'", "")
    if len(s) >= 8:
        try:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        except Exception:
            pass
    return None


async def extract(url: str) -> ExtractedContent:
    """Functional wrapper for backward compatibility."""
    return await PdfAdapter().extract(url)
