"""Local file source adapter.

Reads .txt and .md files directly; delegates .pdf to PdfAdapter.
Gracefully handles unsupported file types by returning ExtractedContent with error field.
Enforces path traversal safety (rejects paths containing ..).
Supports recursive folder extraction with AC-002 through AC-005 compliance.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any

from app.adapters.base import ExtractedContent, ExtractionError, SourceAdapter

_log = logging.getLogger(__name__)
_SUPPORTED = {".txt", ".md", ".pdf", ".docx", ".xlsx"}
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv"}
_MAX_FILES = 10000


class LocalAdapter(SourceAdapter):
    """Extract content from a local file path or folder."""

    async def extract(self, url: str) -> Any:
        """Extract from a file or folder.

        If url is a directory, returns list[ExtractedContent].
        If url is a file, returns ExtractedContent (backward compat).
        """
        path = Path(url)

        if ".." in path.parts:
            raise ExtractionError(f"Path traversal rejected: {url}")

        if not path.exists():
            raise ExtractionError(f"File not found: {url}")

        if path.is_dir():
            return await self._extract_folder(path)

        return await self._extract_single_file(path)

    async def _extract_single_file(self, path: Path) -> ExtractedContent:
        """Extract content from a single file."""
        url = str(path)
        suffix = path.suffix.lower()

        if suffix not in _SUPPORTED and suffix not in _VIDEO_EXTENSIONS:
            return ExtractedContent(
                source_url=url,
                text="",
                title=path.stem,
                source_type="local",
                error=f"File type {suffix!r} is not supported for text extraction",
            )

        if suffix == ".pdf":
            from app.adapters.pdf import PdfAdapter
            return await PdfAdapter().extract(url)

        if suffix == ".docx":
            return self._extract_docx(path)

        if suffix == ".xlsx":
            return self._extract_xlsx(path)

        if suffix in _VIDEO_EXTENSIONS:
            return await self._extract_video_file(path)

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

    def _extract_docx(self, path: Path) -> ExtractedContent:
        """Extract text from a .docx file using stdlib zipfile (no extra deps)."""
        import re
        import zipfile

        url = str(path)
        try:
            with zipfile.ZipFile(path) as z:
                with z.open("word/document.xml") as f:
                    xml = f.read().decode("utf-8", errors="replace")
            # Strip XML tags and collapse whitespace
            text = re.sub(r"<[^>]+>", " ", xml)
            text = re.sub(r"\s+", " ", text).strip()
            try:
                published_at = datetime.datetime.fromtimestamp(
                    path.stat().st_mtime, tz=datetime.UTC
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
        except Exception as exc:
            return ExtractedContent(
                source_url=url,
                text="",
                title=path.stem,
                source_type="local",
                error=f"docx extraction failed: {str(exc)[:100]}",
            )

    def _extract_xlsx(self, path: Path) -> ExtractedContent:
        """Extract text from a .xlsx file using zipfile + regex (no XML parser, no extra deps).

        Uses regex instead of xml.etree to avoid XXE/billion-laughs risks from
        user-supplied xlsx content.
        """
        import re
        import zipfile

        url = str(path)
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()

                # Extract shared string values via regex (avoids XML parser risk)
                shared: list[str] = []
                if "xl/sharedStrings.xml" in names:
                    raw = z.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
                    shared = re.findall(r"<t(?:\s[^>]*)?>([^<]*)</t>", raw)

                # Extract cell values from the first 3 sheets
                texts: list[str] = []
                sheet_files = sorted(
                    n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml", n)
                )[:3]
                for sheet_file in sheet_files:
                    raw = z.read(sheet_file).decode("utf-8", errors="replace")
                    for m in re.finditer(r'<c\b([^>]*)>.*?<v>([^<]*)</v>', raw, re.DOTALL):
                        attrs, val = m.group(1), m.group(2)
                        if 't="s"' in attrs and shared:
                            try:
                                texts.append(shared[int(val)])
                            except (ValueError, IndexError):
                                pass
                        else:
                            texts.append(val)

            text = " ".join(t for t in texts if t.strip())
            try:
                published_at = datetime.datetime.fromtimestamp(
                    path.stat().st_mtime, tz=datetime.UTC
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
        except Exception as exc:
            return ExtractedContent(
                source_url=url,
                text="",
                title=path.stem,
                source_type="local",
                error=f"xlsx extraction failed: {str(exc)[:100]}",
            )

    async def _extract_video_file(self, path: Path) -> ExtractedContent:
        """Extract video file, delegating to video adapter if available."""
        from app.adapters.registry import get_adapter

        video_adapter = get_adapter("video")
        if video_adapter:
            try:
                return await video_adapter.extract(str(path))
            except Exception as exc:
                _log.warning("Video extraction failed for %s: %s", path, exc)

        # No transcription available — create a minimal candidate so the user
        # can see the video was found and decide whether to approve or reject it.
        return ExtractedContent(
            source_url=str(path),
            text=f"[Video file — automatic transcription is not available. Title: {path.stem}]",
            title=path.stem,
            source_type="local",
        )

    async def _extract_folder(self, folder_path: Path) -> list[ExtractedContent]:
        """Recursively extract files from a folder.

        AC-002: Detects when url is a directory.
        AC-003: Uses rglob to find all files recursively, sorted deterministically.
        AC-004: Only processes supported file types (.txt, .md, .pdf, video).
        AC-005: Skips unsupported files without raising; logs them.
        """
        results: list[ExtractedContent] = []
        file_count = 0

        # Discover all files recursively, sorted deterministically
        all_files = sorted(folder_path.rglob("*"), key=lambda p: str(p))

        if len(all_files) > _MAX_FILES:
            _log.warning(
                "Folder %s contains %d files, capped at %d",
                folder_path,
                len(all_files),
                _MAX_FILES,
            )

        for file_path in all_files[:_MAX_FILES]:
            # Skip non-files and symlinks
            if file_path.is_symlink() or not file_path.is_file():
                continue

            # Verify path is within folder root (security: no path traversal escapes)
            try:
                file_path.relative_to(folder_path)
            except ValueError:
                _log.warning("Path %s outside folder root, skipping", file_path)
                continue

            file_count += 1
            suffix = file_path.suffix.lower()

            # Skip unsupported files; log but do not raise
            if suffix not in _SUPPORTED and suffix not in _VIDEO_EXTENSIONS:
                _log.info(
                    "Skipping unsupported file type %s: %s",
                    suffix,
                    file_path,
                )
                continue

            # Extract file
            try:
                extracted = await self._extract_single_file(file_path)
                results.append(extracted)
            except Exception as exc:
                _log.warning("Extraction failed for %s: %s", file_path, exc)
                results.append(
                    ExtractedContent(
                        source_url=str(file_path),
                        text="",
                        title=file_path.stem,
                        source_type="local",
                        error=f"Extraction failed: {str(exc)[:100]}",
                    )
                )

        _log.info(
            "Extracted %d files from folder %s (found %d files total)",
            len(results),
            folder_path,
            file_count,
        )
        return results


async def extract(url: str) -> Any:
    """Functional wrapper for backward compatibility.

    Returns ExtractedContent for a file, or list[ExtractedContent] for a folder.
    """
    return await LocalAdapter().extract(url)
