import json
import uuid
from datetime import datetime
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db

router = APIRouter()

# Safety cap on a single pending-sync response — this is a personal
# single-user vault mirror, not a bulk export API. Combined with
# updated_since, a bridge can still reach every row across repeated syncs;
# this only bounds how much a single response can return.
PENDING_SYNC_MAX_ROWS = 500

# TS counterpart: src/types/index.ts — VaultNode, VaultFile


def _build_tree(rows: list[Any]) -> list[dict[str, Any]]:
    """Convert flat vault_files rows into a nested folder/file tree."""
    folders: dict[str, dict[str, Any]] = {}
    root: list[dict[str, Any]] = []

    for r in sorted(rows, key=lambda x: x["path"]):
        path: str = r["path"]
        parts = path.split("/")
        if len(parts) == 1:
            root.append({"name": parts[0], "path": path, "type": "file", "children": None})
            continue
        parent_path = "/".join(parts[:-1])
        if parent_path not in folders:
            folder: dict[str, Any] = {"name": parts[-2] if len(parts) > 1 else parent_path,
                                      "path": parent_path, "type": "folder", "children": []}
            folders[parent_path] = folder
            root.append(folder)
        folders[parent_path]["children"].append(
            {"name": parts[-1], "path": path, "type": "file", "children": None}
        )
    return root


@router.get("/tree")
async def get_vault_tree(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        "SELECT path FROM vault_files WHERE user_id=$1 ORDER BY path",
        uuid.UUID(user_id),
    )
    if not rows:
        return [{"name": "vault", "path": "/", "type": "folder", "children": []}]
    return _build_tree(rows)


@router.get("/file")
async def get_vault_file(
    path: str = Query(default=""),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    row = await db.fetchrow(
        """SELECT path, content, frontmatter, last_modified, word_count,
                  backlinks, graph_node_type, cloud_safe
           FROM vault_files WHERE path=$1 AND user_id=$2""",
        path,
        uuid.UUID(user_id),
    )
    if row is None:
        return {
            "path": path,
            "content": "",
            "frontmatter": {},
            "lastModified": None,
            "wordCount": 0,
            "backlinks": 0,
            "graphNodeType": "note",
            "cloudSafe": True,
        }
    return {
        "path": row["path"],
        "content": row["content"] or "",
        "frontmatter": row["frontmatter"] or {},
        "lastModified": row["last_modified"].isoformat() if row["last_modified"] else None,
        "wordCount": row["word_count"],
        "backlinks": row["backlinks"],
        "graphNodeType": row["graph_node_type"],
        "cloudSafe": row["cloud_safe"],
    }


# ── Local Sync Bridge endpoints ─────────────────────────────────────────────
# Consumed by the standalone bridge process (bridge/), not the web frontend.
# The bridge authenticates with the same Supabase JWT as the web app — no new
# auth path. See CLAUDE.md "Obsidian vault safety" for the invariants these
# endpoints must not violate (never overwrite a newer manual edit).


@router.get("/pending-sync")
async def get_pending_sync(
    updated_since: str | None = Query(default=None, alias="updatedSince"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    """List vault_files rows for the user, oldest-by-last_modified first, up
    to PENDING_SYNC_MAX_ROWS. The bridge diffs each row's content hash
    against its local manifest and only writes files that actually changed.

    updatedSince (optional ISO 8601 timestamp) lets a bridge with more rows
    than the cap keep paging forward across repeated syncs by passing back
    the max lastModified it saw last time — without this, a vault with more
    than PENDING_SYNC_MAX_ROWS files would have its tail never reachable
    under a flat LIMIT. Always filtered to the authenticated user — one
    user's rows are never visible to another (WHERE user_id=$1)."""
    user_id = current_user["sub"]

    since_dt: datetime | None = None
    if updated_since:
        try:
            since_dt = datetime.fromisoformat(updated_since)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="updatedSince must be an ISO 8601 timestamp",
            ) from exc

    if since_dt is not None:
        rows = await db.fetch(
            """SELECT path, content, frontmatter, last_modified
               FROM vault_files WHERE user_id=$1 AND last_modified > $2
               ORDER BY last_modified ASC LIMIT $3""",
            uuid.UUID(user_id),
            since_dt,
            PENDING_SYNC_MAX_ROWS,
        )
    else:
        rows = await db.fetch(
            """SELECT path, content, frontmatter, last_modified
               FROM vault_files WHERE user_id=$1
               ORDER BY last_modified ASC LIMIT $2""",
            uuid.UUID(user_id),
            PENDING_SYNC_MAX_ROWS,
        )

    return [
        {
            "path": r["path"],
            "content": r["content"] or "",
            "frontmatter": r["frontmatter"] or {},
            "lastModified": r["last_modified"].isoformat() if r["last_modified"] else None,
        }
        for r in rows
    ]


class SyncResult(BaseModel):
    path: str
    status: Literal["written", "skipped_conflict", "error"]
    detail: str = ""


@router.post("/sync-result")
async def post_sync_result(
    body: SyncResult,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    """The bridge reports what happened to one file after a sync pass. Logged
    to the existing processing_log table — no new table needed."""
    user_id = current_user["sub"]
    details = {"path": body.path, "status": body.status, "detail": body.detail}
    await db.execute(
        """INSERT INTO processing_log (user_id, entity_type, entity_id, action, details)
           VALUES ($1, 'vault_file', $2, $3, $4::jsonb)""",
        uuid.UUID(user_id),
        uuid.uuid4(),
        f"bridge_sync_{body.status}",
        json.dumps(details),
    )
    return {"path": body.path, "status": body.status, "logged": True}
