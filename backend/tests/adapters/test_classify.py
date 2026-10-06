"""source_scope classification (Stage 6 verification-loop fix). The client
never sends a meaningful source_scope — the Add Source UI has no field for
it, so SourceCreate's schema default of "direct_resource" was silently
applied to every source, including bare platform homepages. These tests
lock in the server-side classification that replaces that blind default."""
from app.adapters.classify import classify_source_scope


def test_youtube_video_url_is_direct_resource():
    assert classify_source_scope("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ") == (
        "direct_resource"
    )


def test_youtube_bare_homepage_is_discovery_provider():
    assert classify_source_scope("youtube", "https://www.youtube.com/") == "discovery_provider"


def test_youtube_domain_without_trailing_slash_is_discovery_provider():
    assert classify_source_scope("youtube", "https://www.youtube.com") == "discovery_provider"


def test_youtube_shorts_url_is_direct_resource():
    assert classify_source_scope("youtube", "https://www.youtube.com/shorts/dQw4w9WgXcQ") == (
        "direct_resource"
    )


def test_web_source_is_always_direct_resource():
    assert classify_source_scope("web", "https://example.com") == "direct_resource"


def test_pdf_source_is_always_direct_resource():
    assert classify_source_scope("pdf", "https://example.com/doc.pdf") == "direct_resource"


def test_local_source_is_always_direct_resource():
    assert classify_source_scope("local", "/home/user/docs") == "direct_resource"
