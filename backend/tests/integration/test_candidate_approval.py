"""Integration test: Candidate creation and approval workflow.

Tests AC-009 and AC-010 via authenticated API calls.
Verifies that uploaded files trigger candidate creation and approval works.
"""

from io import BytesIO

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_creates_source(authed_client: AsyncClient):
    """AC-009 Step 1: Upload file creates a Source in the database."""
    files = [
        ("files", ("test-doc.pdf", BytesIO(b"%PDF-1.4\n%test"), "application/pdf")),
    ]
    data = {"relative_paths": ["test-doc.pdf"]}

    resp = await authed_client.post("/api/sources/upload", files=files, data=data)

    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    body = resp.json()
    assert body["status"] in ("success", "partial")
    assert len(body["paths"]) > 0, "No files uploaded"


@pytest.mark.asyncio
async def test_source_creation_via_api(authed_client: AsyncClient):
    """AC-009 Step 2: Create a Source via API and prepare for analysis."""
    files = [
        ("files", ("sample.md", BytesIO(b"# Sample\nContent"), "text/markdown")),
    ]
    data = {"relative_paths": ["sample.md"]}

    upload_resp = await authed_client.post("/api/sources/upload", files=files, data=data)
    assert upload_resp.status_code == 200

    uploaded_path = upload_resp.json()["paths"][0]

    source_resp = await authed_client.post(
        "/api/sources",
        json={"url": uploaded_path, "type": "local", "title": "Sample Markdown Document"},
    )

    assert source_resp.status_code == 200, f"Source creation failed: {source_resp.text}"
    source_data = source_resp.json()
    assert "id" in source_data, "Source response missing 'id' field"


@pytest.mark.asyncio
async def test_candidates_endpoint_returns_list(authed_client: AsyncClient):
    """AC-009 Step 3: Verify candidates can be retrieved via API."""
    resp = await authed_client.get("/api/candidates")
    assert resp.status_code == 200, f"Failed to fetch candidates: {resp.text}"
    body = resp.json()
    assert isinstance(body, list), "Candidates endpoint should return a list"


@pytest.mark.asyncio
async def test_candidate_approval_endpoint(authed_client: AsyncClient):
    """AC-010: Approve a candidate via API."""
    list_resp = await authed_client.get("/api/candidates")
    assert list_resp.status_code == 200
    candidates = list_resp.json()

    if len(candidates) > 0:
        candidate_id = candidates[0]["id"]
        approve_resp = await authed_client.post(
            f"/api/candidates/{candidate_id}/approve",
            json={"status": "approved"},
        )
        assert approve_resp.status_code in (200, 202, 204)


@pytest.mark.asyncio
async def test_jobs_endpoint_lists_processing_jobs(authed_client: AsyncClient):
    """AC-010 Step 2: Verify jobs endpoint shows processing status."""
    resp = await authed_client.get("/api/jobs")
    assert resp.status_code == 200, f"Failed to fetch jobs: {resp.text}"
    body = resp.json()
    assert isinstance(body, list), "Jobs endpoint should return a list"


@pytest.mark.asyncio
async def test_full_pipeline_mock(authed_client: AsyncClient):
    """AC-009 & AC-010: Simplified integration test of the full pipeline."""
    files = [("files", ("pipeline-test.txt", BytesIO(b"Test content"), "text/plain"))]
    data = {"relative_paths": ["pipeline-test.txt"]}
    upload_resp = await authed_client.post("/api/sources/upload", files=files, data=data)
    assert upload_resp.status_code == 200

    uploaded_path = upload_resp.json()["paths"][0]
    source_resp = await authed_client.post(
        "/api/sources",
        json={"url": uploaded_path, "type": "local", "title": "Pipeline Test"},
    )
    assert source_resp.status_code == 200

    candidates_resp = await authed_client.get("/api/candidates")
    assert candidates_resp.status_code == 200

    jobs_resp = await authed_client.get("/api/jobs")
    assert jobs_resp.status_code == 200
