"""GET /api/vault/pending-sync: tenant isolation, pagination cap, and the
updatedSince cursor. Calls the route function directly (unit-level) so the
exact SQL/args passed to the connection can be inspected, complementing the
route-level 200-check in test_routes.py.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.routes.vault import PENDING_SYNC_MAX_ROWS, get_pending_sync

USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())


def _user(sub: str) -> dict:
    return {"sub": sub}


@pytest.mark.asyncio
async def test_query_is_filtered_by_the_authenticated_users_id():
    """Tenant isolation: the WHERE clause must key on the caller's own user_id
    — proven by inspecting the actual bound parameter, not just trusting the
    SQL text."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await get_pending_sync(updated_since=None, current_user=_user(USER_A), db=conn)

    sql, args = conn.fetch.call_args.args[0], conn.fetch.call_args.args[1:]
    assert "WHERE user_id=$1" in sql
    assert args[0] == uuid.UUID(USER_A)


@pytest.mark.asyncio
async def test_one_user_cannot_retrieve_another_users_rows():
    """Two different callers must produce two different user_id bindings —
    there is no code path that could leak user B's rows to user A."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await get_pending_sync(updated_since=None, current_user=_user(USER_A), db=conn)
    await get_pending_sync(updated_since=None, current_user=_user(USER_B), db=conn)

    bound_users = [call.args[1] for call in conn.fetch.call_args_list]
    assert bound_users == [uuid.UUID(USER_A), uuid.UUID(USER_B)]
    assert bound_users[0] != bound_users[1]


@pytest.mark.asyncio
async def test_query_applies_a_safe_maximum_row_limit():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await get_pending_sync(updated_since=None, current_user=_user(USER_A), db=conn)

    sql, args = conn.fetch.call_args.args[0], conn.fetch.call_args.args[1:]
    assert "LIMIT $2" in sql
    assert args[1] == PENDING_SYNC_MAX_ROWS


@pytest.mark.asyncio
async def test_repeated_pulls_with_no_new_data_return_the_same_empty_result():
    """Idempotency: pulling twice with nothing new in between must not error
    or fabricate rows."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    first = await get_pending_sync(updated_since=None, current_user=_user(USER_A), db=conn)
    second = await get_pending_sync(updated_since=None, current_user=_user(USER_A), db=conn)

    assert first == second == []


@pytest.mark.asyncio
async def test_updated_since_filters_and_orders_by_last_modified():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    cursor = "2026-01-01T00:00:00+00:00"

    await get_pending_sync(updated_since=cursor, current_user=_user(USER_A), db=conn)

    sql, args = conn.fetch.call_args.args[0], conn.fetch.call_args.args[1:]
    assert "last_modified > $2" in sql
    assert "ORDER BY last_modified ASC" in sql
    assert args[1] == datetime.fromisoformat(cursor)


@pytest.mark.asyncio
async def test_invalid_updated_since_returns_400_not_a_silent_empty_list():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        await get_pending_sync(updated_since="not-a-timestamp", current_user=_user(USER_A), db=conn)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_acknowledged_rows_are_not_rewritten_by_the_endpoint_itself():
    """The endpoint is read-only — it must never mutate vault_files as a side
    effect of being polled (that would risk corrupting last_modified and
    breaking the updatedSince cursor for other callers)."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"path": "a.md", "content": "A", "frontmatter": {}, "last_modified": datetime.now(timezone.utc)},
    ])

    await get_pending_sync(updated_since=None, current_user=_user(USER_A), db=conn)

    conn.execute.assert_not_called()
