from collections.abc import AsyncGenerator

import asyncpg  # type: ignore[import-untyped]

from app.core.security import get_current_user
from app.db.client import get_pool

__all__ = ["get_current_user", "get_db"]


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
