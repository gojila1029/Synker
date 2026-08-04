import contextlib
from unittest.mock import patch


class _MockConn:
    async def fetchval(self, *args, **kwargs):
        return 1


class _MockPool:
    @contextlib.asynccontextmanager
    async def acquire(self):
        yield _MockConn()


async def _healthy_pool():
    return _MockPool()


async def test_health_returns_200(client):
    with patch("app.api.routes.health.get_pool", new=_healthy_pool):
        response = await client.get("/health")
    assert response.status_code == 200


async def test_health_body_is_ok(client):
    with patch("app.api.routes.health.get_pool", new=_healthy_pool):
        response = await client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


async def test_health_no_auth_required(client):
    with patch("app.api.routes.health.get_pool", new=_healthy_pool):
        response = await client.get("/health")
    assert response.status_code != 401
    assert response.status_code != 403


async def test_health_degraded_when_db_unreachable(client):
    async def _failing_pool():
        raise Exception("DB unavailable")

    with patch("app.api.routes.health.get_pool", new=_failing_pool):
        response = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["db"] == "unreachable"
