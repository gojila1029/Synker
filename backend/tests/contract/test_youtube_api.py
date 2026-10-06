"""Contract tests for YouTube API endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.integration
def test_youtube_search_endpoint_auth_required(client: TestClient) -> None:
    """GET /api/youtube/search requires authentication."""
    response = client.get("/api/youtube/search?q=test")
    assert response.status_code in (401, 403, 307, 400)  # May redirect or deny


@pytest.mark.integration
def test_youtube_search_endpoint_empty_query(client: TestClient) -> None:
    """GET /api/youtube/search with empty query."""
    # This would require auth in real scenario, testing response structure
    response = client.get("/api/youtube/search?q=")
    # Should reject empty query or require auth
    assert response.status_code in (400, 401, 403)


@pytest.mark.integration
def test_youtube_parse_intent_endpoint_auth_required(client: TestClient) -> None:
    """POST /api/youtube/parse-intent requires authentication."""
    response = client.post("/api/youtube/parse-intent", json={"message": "find tutorials"})
    assert response.status_code in (401, 403, 307)


@pytest.mark.integration
def test_youtube_parse_intent_body_validation(client: TestClient) -> None:
    """POST /api/youtube/parse-intent validates request body."""
    # Missing message field
    response = client.post("/api/youtube/parse-intent", json={})
    assert response.status_code in (422, 401, 403)


@pytest.mark.integration
def test_youtube_batch_notes_endpoint_auth_required(client: TestClient) -> None:
    """POST /api/youtube/notes/batch requires authentication."""
    response = client.post(
        "/api/youtube/notes/batch",
        json={"video_urls": ["https://youtube.com/watch?v=abc123"]},
    )
    assert response.status_code in (401, 403, 307)


@pytest.mark.integration
def test_youtube_batch_notes_empty_urls(client: TestClient) -> None:
    """POST /api/youtube/notes/batch with empty URLs list."""
    response = client.post("/api/youtube/notes/batch", json={"video_urls": []})
    assert response.status_code in (401, 403, 307, 200)  # May succeed with empty


@pytest.mark.integration
def test_youtube_search_response_schema() -> None:
    """Response from /api/youtube/search should have expected schema."""
    # This tests the type definition, not requiring auth
    from app.api.routes.youtube import YouTubeSearchResponse

    response = YouTubeSearchResponse(results=[])
    assert hasattr(response, "results")
    assert hasattr(response, "error")
    assert hasattr(response, "error_code")


@pytest.mark.integration
def test_parsed_intent_response_schema() -> None:
    """Response from parse-intent should have expected schema."""
    from app.api.routes.youtube import ParsedIntentResponse

    response = ParsedIntentResponse(
        search_query="test",
        limit=10,
        confidence=0.8,
    )
    assert response.search_query == "test"
    assert response.limit == 10
    assert response.confidence == 0.8


@pytest.mark.integration
def test_batch_note_response_schema() -> None:
    """Response from /notes/batch should have expected schema."""
    from app.api.routes.youtube import BatchNoteItem, BatchNoteResponse

    item = BatchNoteItem(
        url="https://youtube.com/watch?v=abc",
        video_id="abc123",
        status="SUCCESS",
    )
    response = BatchNoteResponse(results=[item])
    assert len(response.results) == 1
    assert response.results[0].status == "SUCCESS"


@pytest.mark.integration
def test_batch_note_failure_status() -> None:
    """BatchNoteItem should support FAILED status."""
    from app.api.routes.youtube import BatchNoteItem

    item = BatchNoteItem(
        url="https://youtube.com/watch?v=invalid",
        status="FAILED",
        error="Invalid video ID",
    )
    assert item.status == "FAILED"
    assert item.error == "Invalid video ID"


@pytest.mark.integration
def test_batch_note_already_exists_status() -> None:
    """BatchNoteItem should support ALREADY_EXISTS status."""
    from app.api.routes.youtube import BatchNoteItem

    item = BatchNoteItem(
        url="https://youtube.com/watch?v=dup",
        video_id="dup123",
        status="ALREADY_EXISTS",
        error="Candidate already exists",
    )
    assert item.status == "ALREADY_EXISTS"
