from __future__ import annotations

from collections.abc import Callable

from app.adapters import local, pdf, web, youtube
from app.adapters.base import ExtractedContent

_REGISTRY: dict[str, Callable[[str], "Awaitable[ExtractedContent]"]] = {
    "youtube": youtube.extract,
    "web": web.extract,
    "pdf": pdf.extract,
    "local": local.extract,
}

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Awaitable


async def extract(source_type: str, url: str) -> ExtractedContent:
    fn = _REGISTRY.get(source_type)
    if fn is None:
        return ExtractedContent(
            text="",
            title=url,
            source_url=url,
            source_type=source_type,
            error=f"No adapter for source type: {source_type!r}",
        )
    result = await fn(url)
    return result
