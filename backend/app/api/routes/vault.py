import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_db

router = APIRouter()

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
