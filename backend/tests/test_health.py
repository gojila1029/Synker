"""
Tests for GET /health

Guarantees:
- Returns HTTP 200
- Body contains {"status": "ok"}
- Unauthenticated (no auth header required)
"""


async def test_health_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_body_is_ok(client):
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


async def test_health_no_auth_required(client):
    response = await client.get("/health")
    assert response.status_code != 401
    assert response.status_code != 403
