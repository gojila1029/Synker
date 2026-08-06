"""Maps source type strings to adapter instances."""
from __future__ import annotations

from app.adapters.base import SourceAdapter
from app.adapters.local import LocalAdapter
from app.adapters.pdf import PdfAdapter
from app.adapters.web import WebAdapter
from app.adapters.youtube import YoutubeAdapter

_ADAPTERS: dict[str, SourceAdapter] = {
    "youtube": YoutubeAdapter(),
    "web": WebAdapter(),
    "pdf": PdfAdapter(),
    "local": LocalAdapter(),
}


def get_adapter(source_type: str) -> SourceAdapter | None:
    return _ADAPTERS.get(source_type)
