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
        return JSONResponse(
            {"status": "degraded", "db": "unreachable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
