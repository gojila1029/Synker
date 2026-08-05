from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.db.client import get_pool

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({"status": "ok", "db": "ok"})
    except Exception:
        # DB is required by every data route, so report unready (503) when it is
        # unreachable. The app still boots (lifespan tolerates DB-down and retries
        # on first request); this only signals the platform not to route traffic
        # to an instance that cannot serve data.
        return JSONResponse(
            {"status": "degraded", "db": "unreachable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
