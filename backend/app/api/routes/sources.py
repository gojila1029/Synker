import uuid
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.adapters.classify import classify_source_scope
from app.api.deps import get_current_user, get_db
from app.schemas.sources import FileUploadResponse, SourceCreate

router = APIRouter()

# TS counterpart: src/types/index.ts — Source

UPLOAD_ROOT = Path(__file__).parent.parent.parent / "uploads"
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".doc", ".docx", ".docm"}


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(default=[]),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> FileUploadResponse:
    user_id = current_user["sub"]
    upload_id = str(uuid.uuid4())
    user_upload_dir = UPLOAD_ROOT / user_id / upload_id
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    stored_paths: list[str] = []
    try:
        for i, file in enumerate(files):
            # Validate extension
            filename = file.filename or ""
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    400, detail=f"File type not allowed: {suffix}"
                )

            # Determine target path (preserve relative folder structure)
            relative_path = (
                relative_paths[i] if i < len(relative_paths) else filename
            )
            safe_relative = Path(relative_path).as_posix().lstrip("/")

            # Security: reject traversal
            target = (user_upload_dir / safe_relative).resolve()
            if not str(target).startswith(str(user_upload_dir.resolve())):
                raise HTTPException(400, detail="Path traversal rejected")

            target.parent.mkdir(parents=True, exist_ok=True)

            # Read and validate size
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    400,
                    detail=f"File size exceeds 500 MB: {filename}",
                )

            target.write_bytes(content)
            stored_paths.append(str(target))
    except HTTPException:
        raise
    except Exception as e:
        import shutil

        shutil.rmtree(user_upload_dir, ignore_errors=True)
        raise HTTPException(500, detail=f"Upload failed: {str(e)}")

    return FileUploadResponse(
        status="success",
        upload_id=upload_id,
        paths=stored_paths,
        message=f"{len(stored_paths)} file(s) uploaded successfully",
    )


@router.get("")
async def list_sources(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    user_id = current_user["sub"]
    rows = await db.fetch(
        """SELECT id, type, source_scope, title, url, topic_id, status, schedule, added_at,
                  keyword, discovery_mode, discovery_limit
           FROM sources WHERE user_id=$1 ORDER BY added_at DESC""",
        uuid.UUID(user_id),
    )
    return [
        {
            "id": str(r["id"]),
            "type": r["type"],
            "sourceScope": r["source_scope"],
            "title": r["title"],
            "url": r["url"],
            "topicId": str(r["topic_id"]) if r["topic_id"] else None,
            "status": r["status"],
            "addedAt": r["added_at"].isoformat() if r["added_at"] else None,
            "schedule": r["schedule"],
            "keyword": r["keyword"],
            "discoveryMode": r["discovery_mode"],
            "discoveryLimit": r["discovery_limit"],
        }
        for r in rows
    ]


@router.post("")
async def add_source(
    body: SourceCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    user_id = current_user["sub"]
    topic_id = body.topic_id
    # The client never sends a meaningful source_scope (no UI field for it),
    # so SourceCreate's "direct_resource" default is wrong for a bare
    # platform homepage. Classify it server-side instead of trusting body.
    source_scope = classify_source_scope(body.type, body.url)
    row = await db.fetchrow(
        """INSERT INTO sources (user_id, topic_id, type, source_scope, title, url,
                               schedule, keyword, discovery_mode, discovery_limit)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           RETURNING id, type, source_scope, title, url, topic_id, status, schedule,
                     added_at, keyword, discovery_mode, discovery_limit""",
        uuid.UUID(user_id),
        uuid.UUID(topic_id) if topic_id else None,
        body.type,
        source_scope,
        body.title,
        body.url,
        None,
        body.keyword,
        body.discovery_mode,
        body.discovery_limit,
    )
    if row is None:
        return {
            "id": "",
            "type": body.type,
            "sourceScope": source_scope,
            "title": body.title,
            "url": body.url,
            "topicId": topic_id,
            "status": "queued",
            "addedAt": None,
            "schedule": None,
            "keyword": body.keyword,
            "discoveryMode": body.discovery_mode,
            "discoveryLimit": body.discovery_limit,
        }
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "sourceScope": row["source_scope"],
        "title": row["title"],
        "url": row["url"],
        "topicId": str(row["topic_id"]) if row["topic_id"] else None,
        "status": row["status"],
        "addedAt": row["added_at"].isoformat() if row["added_at"] else None,
        "schedule": row["schedule"],
        "keyword": row["keyword"],
        "discoveryMode": row["discovery_mode"],
        "discoveryLimit": row["discovery_limit"],
    }


@router.patch("/{source_id}/reset")
async def reset_source(
    source_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    user_id = current_user["sub"]
    try:
        sid, uid = uuid.UUID(source_id), uuid.UUID(user_id)
    except ValueError:
        return {"reset": source_id}
    row = await db.fetchrow(
        "UPDATE sources SET status='queued', updated_at=now() "
        "WHERE id=$1 AND user_id=$2 RETURNING id, status",
        sid, uid,
    )
    return {"reset": source_id, "status": row["status"] if row else "not_found"}


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    user_id = current_user["sub"]
    try:
        await db.execute(
            "DELETE FROM sources WHERE id=$1 AND user_id=$2",
            uuid.UUID(source_id),
            uuid.UUID(user_id),
        )
    except ValueError:
        pass
    return Response(status_code=204)

