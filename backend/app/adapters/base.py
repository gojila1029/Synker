from dataclasses import dataclass, field


class ExtractionError(Exception):
    """Raised when a source adapter cannot extract content."""


class SourceAdapter:
    """Base class for source adapters. Subclasses must override extract()."""

    async def extract(self, url: str) -> "ExtractedContent":
        raise NotImplementedError


@dataclass
class ExtractedContent:
    text: str
    title: str
    author: str = ""
    published_at: str | None = None
    source_url: str = ""
    source_type: str = ""
    word_count: int = 0
    domain: str = ""
    timestamps: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None
