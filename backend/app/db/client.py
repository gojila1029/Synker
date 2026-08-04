"""
asyncpg connection pool.

statement_cache_size=0 is REQUIRED for Supabase's PgBouncer Session Pooler.
Omitting it causes "prepared statement already exists" errors under concurrent load.
"""
from typing import Optional

import asyncpg

from app.core.config import settings

_pool: Optional[asyncpg.Pool] = None  # type: ignore[type-arg]


async def get_pool() -> asyncpg.Pool:  # type: ignore[type-arg]
    global _pool
    if _pool is None:
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(
            dsn,
            statement_cache_size=0,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
