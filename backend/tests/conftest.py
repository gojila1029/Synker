import os

# Set required secrets before importing app so pydantic-settings validators pass in tests
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.deps import get_current_user, get_db

MOCK_USER = {
    "sub": "00000000-0000-0000-0000-000000000001",
    "email": "test@example.com",
    "role": "authenticated",
}


class MockConn:
    """Minimal asyncpg.Connection stand-in for unit tests that must not hit a real DB."""

    async def fetch(self, *args, **kwargs):  # type: ignore[override]
        return []

    async def fetchrow(self, *args, **kwargs):  # type: ignore[override]
        return None

    async def fetchval(self, *args, **kwargs):  # type: ignore[override]
        return None

    async def execute(self, *args, **kwargs):  # type: ignore[override]
        return None


class MockConnWithSources(MockConn):
    """MockConn variant that reports one source for the scheduler trigger guard."""

    async def fetchval(self, query: str, *args, **kwargs):  # type: ignore[override]
        if "sources" in query.lower() and "count" in query.lower():
            return 1
        return None

    async def fetchrow(self, *args, **kwargs):  # type: ignore[override]
        import uuid as _uuid
        return {"id": _uuid.UUID("00000000-0000-0000-0000-000000000099")}


async def _mock_get_db():
    yield MockConn()


async def _mock_get_db_with_source():
    yield MockConnWithSources()


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authed_client() -> AsyncClient:
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _mock_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def authed_client_with_source() -> AsyncClient:
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _mock_get_db_with_source
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
