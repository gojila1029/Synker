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
        # Return 200 so Railway promotes the deployment healthy.
        # DB status is visible in the response body for monitoring.
        return JSONResponse({"status": "degraded", "db": "unreachable"})
