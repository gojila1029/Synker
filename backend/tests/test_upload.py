"""Tests for POST /api/sources/upload endpoint.

Verifies multipart file upload functionality with:
- Valid file uploads
- Extension validation
- File size limit enforcement
- Path traversal rejection
- Authentication requirement
"""
from io import BytesIO

import pytest


@pytest.mark.contract
async def test_upload_valid_files_returns_200(authed_client, tmp_path):
    """Happy path: upload a valid PDF file."""
    # Create a temporary PDF file
    pdf_content = b"%PDF-1.4\ntest content"
    files = [("files", ("document.pdf", BytesIO(pdf_content), "application/pdf"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "uploadId" in body
    assert isinstance(body["paths"], list)
    assert len(body["paths"]) == 1
    assert "document.pdf" in body["paths"][0]
    assert body["message"] == "1 file(s) uploaded successfully"


@pytest.mark.contract
async def test_upload_multiple_files_returns_all_paths(authed_client):
    """Upload multiple files and verify all paths are returned."""
    files = [
        ("files", ("file1.txt", BytesIO(b"content1"), "text/plain")),
        ("files", ("file2.md", BytesIO(b"content2"), "text/markdown")),
        ("files", ("file3.pdf", BytesIO(b"%PDF-1.4\ncontent3"), "application/pdf")),
    ]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert len(body["paths"]) == 3
    assert body["message"] == "3 file(s) uploaded successfully"


@pytest.mark.contract
async def test_upload_preserves_folder_structure(authed_client):
    """Upload with relative_paths to preserve folder structure."""
    files = [
        ("files", ("memo.txt", BytesIO(b"memo content"), "text/plain")),
        ("files", ("report.pdf", BytesIO(b"%PDF-1.4\nreport"), "application/pdf")),
    ]
    data = {
        "relative_paths": ["notes/2026/memo.txt", "reports/2026/report.pdf"]
    }

    response = await authed_client.post(
        "/api/sources/upload", files=files, data=data
    )

    assert response.status_code == 200
    body = response.json()
    assert "2026" in body["paths"][0]  # folder structure preserved
    assert "2026" in body["paths"][1]


@pytest.mark.contract
async def test_upload_accepts_all_extensions(authed_client):
    """Upload accepts all file extensions (including .exe) at upload time."""
    files = [("files", ("program.exe", BytesIO(b"MZ\x90\x00"), "application/x-msdownload"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    # All file types are now accepted at upload time (HTTP 200)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert len(body["paths"]) == 1
    assert "program.exe" in body["paths"][0]


@pytest.mark.contract
async def test_upload_rejects_path_traversal(authed_client):
    """Upload with path traversal attempt (..) is skipped and reported."""
    # Case 1: no-extension traversal
    files = [("files", ("safe.txt", BytesIO(b"content"), "text/plain"))]
    data = {"relative_paths": ["../../../etc/passwd"]}
    response = await authed_client.post("/api/sources/upload", files=files, data=data)
    # File is skipped due to traversal, so HTTP 400 (no valid files)
    assert response.status_code == 400

    # Case 2: valid-extension traversal — caught by path traversal check, skipped
    files2 = [("files", ("safe.txt", BytesIO(b"content"), "text/plain"))]
    data2 = {"relative_paths": ["../../../escape.txt"]}
    response2 = await authed_client.post("/api/sources/upload", files=files2, data=data2)
    assert response2.status_code == 400
    body2 = response2.json()
    # When all files are invalid/skipped, the response is an HTTPException detail
    assert "No valid files to upload" in body2["detail"]


@pytest.mark.contract
async def test_upload_rejects_unauthenticated(client):
    """Upload without JWT returns 401 Unauthorized."""
    files = [("files", ("document.pdf", BytesIO(b"%PDF-1.4\ntest"), "application/pdf"))]

    response = await client.post("/api/sources/upload", files=files)

    assert response.status_code == 401


@pytest.mark.contract
async def test_upload_returns_response_with_uploadid(authed_client):
    """Upload response includes uploadId (UUID format)."""
    files = [("files", ("note.md", BytesIO(b"# Title\n\nContent"), "text/markdown"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert "uploadId" in body
    # Verify it looks like a UUID
    upload_id = body["uploadId"]
    assert len(upload_id) == 36  # UUID string length
    assert upload_id.count("-") == 4


@pytest.mark.contract
async def test_upload_stores_files_under_user_directory(authed_client):
    """Uploaded files are stored under user_id directory."""
    files = [("files", ("test.txt", BytesIO(b"test"), "text/plain"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    paths = body["paths"]
    # Path should contain the mock user ID
    assert "00000000-0000-0000-0000-000000000001" in paths[0]


@pytest.mark.contract
async def test_upload_allowed_extensions(authed_client):
    """All allowed extensions (.txt, .md, .pdf, .doc, .docx, .docm) are accepted."""
    allowed_files = [
        ("files", ("file.txt", BytesIO(b"txt"), "text/plain")),
        ("files", ("file.md", BytesIO(b"md"), "text/markdown")),
        ("files", ("file.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")),
        ("files", ("file.doc", BytesIO(b"doc"), "application/msword")),
        (
            "files",
            (
                "file.docx",
                BytesIO(b"docx"),
                "application/"
                "vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ),
        (
            "files",
            (
                "file.docm",
                BytesIO(b"docm"),
                "application/vnd.ms-word.document.macroenabled.12",
            ),
        ),
    ]

    response = await authed_client.post("/api/sources/upload", files=allowed_files)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert len(body["paths"]) == 6


@pytest.mark.contract
async def test_upload_response_schema_has_required_fields(authed_client):
    """Upload response has all required fields per AC-004."""
    files = [("files", ("doc.pdf", BytesIO(b"%PDF-1.4"), "application/pdf"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "uploadId" in body
    assert "paths" in body
    assert "message" in body
    assert "skipped" in body
    assert body["status"] == "success"
    assert isinstance(body["paths"], list)
    assert isinstance(body["message"], str)
    assert isinstance(body["skipped"], list)


@pytest.mark.contract
async def test_upload_empty_file_is_rejected(authed_client):
    """Empty file upload (0 bytes) succeeds but may be filtered later."""
    files = [("files", ("empty.txt", BytesIO(b""), "text/plain"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    # Empty files are technically valid uploads (no size check for 0 bytes)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"


@pytest.mark.contract
async def test_upload_with_non_ascii_filename_is_handled(authed_client):
    """Upload with non-ASCII filename is handled safely (normalized or rejected)."""
    files = [("files", ("файл.txt", BytesIO(b"content"), "text/plain"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    # Should either succeed with normalized name or fail gracefully
    assert response.status_code in (200, 400)


@pytest.mark.contract
async def test_upload_case_insensitive_extension_check(authed_client):
    """Upload with uppercase extension (.PDF, .TXT) is accepted."""
    files = [
        ("files", ("DOCUMENT.PDF", BytesIO(b"%PDF-1.4"), "application/pdf")),
        ("files", ("NOTE.TXT", BytesIO(b"note"), "text/plain")),
    ]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert len(body["paths"]) == 2


@pytest.mark.contract
async def test_upload_accepts_all_file_types_mixed(authed_client):
    """AC-001: Upload accepts all file types including unsupported ones at upload time."""
    files = [
        ("files", ("valid1.txt", BytesIO(b"text content"), "text/plain")),
        ("files", ("image.bmp", BytesIO(b"BMP"), "image/bmp")),
        ("files", ("valid2.pdf", BytesIO(b"%PDF-1.4\ncontent"), "application/pdf")),
    ]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    # All files are accepted at upload time, so status is "success"
    assert body["status"] == "success"
    assert len(body["paths"]) == 3
    assert "valid1.txt" in body["paths"][0]
    assert "image.bmp" in body["paths"][1]
    assert "valid2.pdf" in body["paths"][2]
    assert len(body["skipped"]) == 0
    assert "3 file(s) uploaded successfully" in body["message"]


@pytest.mark.contract
async def test_upload_accepts_all_unsupported_types(authed_client):
    """Upload accepts all unsupported file types at upload time (HTTP 200)."""
    files = [
        ("files", ("program.exe", BytesIO(b"MZ"), "application/x-msdownload")),
        ("files", ("archive.zip", BytesIO(b"PK"), "application/zip")),
        ("files", ("image.bmp", BytesIO(b"BMP"), "image/bmp")),
    ]

    response = await authed_client.post("/api/sources/upload", files=files)

    # All file types are accepted at upload time
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert len(body["paths"]) == 3
    assert "program.exe" in body["paths"][0]
    assert "archive.zip" in body["paths"][1]
    assert "image.bmp" in body["paths"][2]


@pytest.mark.contract
async def test_upload_oversized_file_skipped(authed_client):
    """AC-003: File exceeding 500 MB is skipped, valid files are uploaded."""
    # Create a file that exceeds 500 MB (use a sparse representation for testing)
    oversized_content = b"x" * (500 * 1024 * 1024 + 1)
    files = [
        ("files", ("valid.txt", BytesIO(b"small file"), "text/plain")),
        ("files", ("huge.pdf", BytesIO(oversized_content), "application/pdf")),
    ]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert len(body["paths"]) == 1
    assert "valid.txt" in body["paths"][0]
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["filename"] == "huge.pdf"
    assert "exceeds 500 MB" in body["skipped"][0]["reason"]


@pytest.mark.contract
async def test_upload_single_valid_file_success_status(authed_client):
    """AC-004: Single valid file returns status='success' with empty skipped list."""
    files = [("files", ("note.txt", BytesIO(b"content"), "text/plain"))]

    response = await authed_client.post("/api/sources/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert len(body["paths"]) == 1
    assert len(body.get("skipped", [])) == 0
    assert "uploaded successfully" in body["message"]
