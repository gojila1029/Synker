"""One-time cleanup: remove test video and Unknown title candidates from Railway Postgres.

Run with:
    ! cd backend && uv run python ..\scripts\cleanup_test_candidates.py
"""
import asyncio
import os
import sys


async def cleanup() -> None:
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

    rows = await conn.fetch(
        "SELECT id, title, status FROM candidates "
        "WHERE title IN ('Unknown','Test Video') OR source_info LIKE '%dQw4w9WgXcQ%'"
    )
    print(f"INSPECT: {len(rows)} rows targeted for deletion")
    for r in rows:
        print(f"  {r['id']} | {r['title']!r} | {r['status']}")

    if not rows:
        print("Nothing to delete — database already clean.")
        await conn.close()
        return

    result = await conn.execute(
        "DELETE FROM candidates "
        "WHERE title IN ('Unknown','Test Video') OR source_info LIKE '%dQw4w9WgXcQ%'"
    )
    print(f"DELETE: {result}")

    remaining = await conn.fetchval(
        "SELECT COUNT(*) FROM candidates "
        "WHERE title IN ('Unknown','Test Video') OR source_info LIKE '%dQw4w9WgXcQ%'"
    )
    print(f"VERIFY: remaining = {remaining}  (must be 0 for AC-006/007/009 PASS)")
    await conn.close()


asyncio.run(cleanup())
