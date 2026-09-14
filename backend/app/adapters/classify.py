"""Server-side source_scope classification.

The Add Source UI has no field for source_scope (see AI Knowledge Curation
Platform/src/app/App.tsx's "Add a Source" modal — only url/type/topic), so
SourceCreate's "direct_resource" schema default was applied unconditionally
to every source, including bare platform homepages that cannot actually be
extracted as one resource. This module infers the real scope instead of
trusting that default (Stage 6 verification-loop ROOT CAUSE #2).
"""
from __future__ import annotations

from typing import Literal

from app.adapters.youtube import _extract_video_id

SourceScope = Literal["direct_resource", "discovery_provider"]


def classify_source_scope(source_type: str, url: str) -> SourceScope:
    """A YouTube URL with no resolvable video id (a channel, search result,
    or the bare homepage) needs real discovery to turn into candidates —
    which this codebase does not implement yet (see
    _analysis_handler's discovery_provider branch). Flagging it as
    discovery_provider keeps that gap honest instead of silently treating
    the platform's homepage as a single extractable resource.

    web/pdf/local sources are always a single resource in this codebase —
    there is no "web platform homepage" ambiguity to classify for them."""
    if source_type == "youtube" and not _extract_video_id(url):
        return "discovery_provider"
    return "direct_resource"
