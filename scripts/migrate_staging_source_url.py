"""Apply migration 007 (source_url column) to Railway staging Postgres.

Run with:
    ! cd backend && uv run python ..\scripts\migrate_staging_source_url.py
"""
import asyncio
import os
import sys


async def migrate() -> None:
    try:
        import asyncpg  # type: ignore[import-untyped]
    except ImportError:
        print("asyncpg not installed — run from backend venv", file=sys.stderr)
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("Set DATABASE_URL env var before running", file=sys.stderr)
        sys.exit(1)

    conn_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn=conn_url)

    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='source_extractions' AND column_name='source_url'"
    )
    if cols:
        print("source_url column already exists — nothing to do")
        await conn.close()
        return

    await conn.execute("ALTER TABLE source_extractions ADD COLUMN IF NOT EXISTS source_url text")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_extractions_url "
        "ON source_extractions(source_url) WHERE source_url IS NOT NULL"
    )
    print("DONE: source_url column added to source_extractions")
    await conn.close()


asyncio.run(migrate())
