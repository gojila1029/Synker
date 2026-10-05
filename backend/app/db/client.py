"""
asyncpg connection pool.

statement_cache_size=0 is REQUIRED for Supabase's PgBouncer Session Pooler.
Omitting it causes "prepared statement already exists" errors under concurrent load.
"""
from __future__ import annotations

import json

import asyncpg  # type: ignore[import-untyped]

from app.core.config import settings

_pool: asyncpg.Pool[asyncpg.Connection] | None = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


async def get_pool() -> asyncpg.Pool[asyncpg.Connection]:
    global _pool
    if _pool is None:
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(
            dsn,
            statement_cache_size=0,
            init=_init_conn,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
