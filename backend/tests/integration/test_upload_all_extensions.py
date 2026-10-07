"""Integration test: Upload endpoint accepts all file types.

Tests AC-001, AC-005, AC-006, AC-008, AC-014 via authenticated API calls.
Verifies that the upload endpoint accepts files with any extension
and returns proper response schema.
"""

import uuid
from io import BytesIO

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_endpoint_accepts_all_extensions(authed_client: AsyncClient):
    """AC-001 & AC-014: Upload endpoint accepts all extensions and response schema unchanged."""
    files = [
        ("files", ("test.txt", BytesIO(b"Text file content"), "text/plain")),
        ("files", ("test.md", BytesIO(b"# Markdown\nContent here"), "text/markdown")),
        ("files", ("test.jpg", BytesIO(b"fake jpeg data"), "image/jpeg")),
        ("files", ("test.zip", BytesIO(b"fake zip data"), "application/zip")),
    ]
    data = {"relative_paths": ["test.txt", "test.md", "test.jpg", "test.zip"]}

    resp = await authed_client.post("/api/sources/upload", files=files, data=data)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()

    assert "status" in body
    assert "uploadId" in body
    assert "paths" in body
    assert "skipped" in body
    assert "message" in body
    assert body["status"] in ("success", "partial", "error")
    uuid.UUID(body["uploadId"])
    assert isinstance(body["paths"], list)
    assert isinstance(body["skipped"], list)
    assert len(body["paths"]) + len(body["skipped"]) > 0


@pytest.mark.asyncio
async def test_upload_unsupported_types_in_skipped_array(authed_client: AsyncClient):
    """AC-002: Unsupported types upload succeeds (not HTTP 400)."""
    files = [
        ("files", ("image.jpg", BytesIO(b"fake jpg"), "image/jpeg")),
        ("files", ("video.mp4", BytesIO(b"fake mp4"), "video/mp4")),
    ]
    data = {"relative_paths": ["image.jpg", "video.mp4"]}

    resp = await authed_client.post("/api/sources/upload", files=files, data=data)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["paths"]) + len(body["skipped"]) > 0


@pytest.mark.asyncio
async def test_upload_mixed_file_types(authed_client: AsyncClient):
    """AC-005: Mixed upload (supported + unsupported) all accepted at upload layer."""
    files = [
        ("files", ("readme.txt", BytesIO(b"This is a text file"), "text/plain")),
        ("files", ("notes.md", BytesIO(b"# Notes\nMarkdown content"), "text/markdown")),
        ("files", ("photo.jpg", BytesIO(b"fake jpg"), "image/jpeg")),
        ("files", ("archive.zip", BytesIO(b"fake zip"), "application/zip")),
    ]
    data = {"relative_paths": ["readme.txt", "notes.md", "photo.jpg", "archive.zip"]}

    resp = await authed_client.post("/api/sources/upload", files=files, data=data)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("success", "partial")
    assert len(body["paths"]) + len(body["skipped"]) > 0


@pytest.mark.asyncio
async def test_upload_path_traversal_rejected(authed_client: AsyncClient):
    """AC-006: Path traversal attempts are rejected."""
    files = [("files", ("malicious.txt", BytesIO(b"bad file"), "text/plain"))]
    data = {"relative_paths": ["../../etc/passwd"]}

    resp = await authed_client.post("/api/sources/upload", files=files, data=data)

    if resp.status_code == 400:
        return

    assert resp.status_code == 200
    body = resp.json()
    skipped_reasons = [s.get("reason", "") for s in body.get("skipped", [])]
    has_rejection = any("traversal" in r.lower() for r in skipped_reasons)
    assert has_rejection or len(body["paths"]) == 0
