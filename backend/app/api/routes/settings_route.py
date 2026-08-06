import asyncio
import base64
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import asyncpg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_db
from app.schemas.settings import (
    AIProvidersSettingsRead,
    CleanupSettings,
    DiscoverySettings,
    NotificationsSettings,
    PrivacySettings,
    SettingsRead,
    TeamSettings,
    VaultSettings,
)


def _encrypt_field(plaintext: str) -> str:
    """AES-256-GCM encrypt a string. Returns base64(nonce + ciphertext).
    Requires SETTINGS_ENCRYPTION_KEY env var with at least 32 characters.
    Returns plaintext unchanged when key is absent or too short."""
    raw_key = os.environ.get("SETTINGS_ENCRYPTION_KEY", "")
    if len(raw_key) < 32 or not plaintext:
        return plaintext
    aesgcm = AESGCM(raw_key[:32].encode("utf-8"))
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")

router = APIRouter()

# TS counterpart: src/types/index.ts — Settings

JSONB_SECTIONS = {"ai_providers", "privacy", "discovery", "cleanup", "notifications"}


@router.get("", response_model=SettingsRead)
async def get_settings(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> SettingsRead:
    user_id = current_user["sub"]
    row = await db.fetchrow("SELECT * FROM user_settings WHERE user_id = $1", user_id)
    if row is None:
        return SettingsRead()
    ai_raw: dict = row["ai_providers"] or {}
    return SettingsRead(
        vault=VaultSettings(path=row["vault_path"], name=row["vault_name"]),
        ai_providers=AIProvidersSettingsRead(
            claude_key_set=bool(ai_raw.get("claudeKey")),
            openai_key_set=bool(ai_raw.get("openaiKey")),
            ollama_url=ai_raw.get("ollamaUrl", ""),
            fallback_order=ai_raw.get("fallbackOrder", ["claude", "openai"]),
        ),
        privacy=PrivacySettings.model_validate(row["privacy"] or {}),
        discovery=DiscoverySettings.model_validate(row["discovery"] or {}),
        cleanup=CleanupSettings.model_validate(row["cleanup"] or {}),
        notifications=NotificationsSettings.model_validate(row["notifications"] or {}),
        team=TeamSettings(tier=row["team_tier"]),
    )


@router.patch("/{section}")
async def update_settings(
    section: str,
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),  # type: ignore[type-arg]
) -> dict[str, Any]:
    user_id = current_user["sub"]
    valid = {"vault", "ai_providers", "privacy", "discovery", "cleanup", "notifications", "team"}
    if section not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown section: {section}",
        )

    if section == "vault":
        await db.execute(
            """INSERT INTO user_settings (user_id, vault_path, vault_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE
               SET vault_path = $2, vault_name = $3, updated_at = now()""",
            user_id,
            body.get("path", ""),
            body.get("name", "My Vault"),
        )
    elif section == "team":
        tier = body.get("tier", "single")
        await db.execute(
            """INSERT INTO user_settings (user_id, team_tier)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE
               SET team_tier = $2, updated_at = now()""",
            user_id,
            tier,
        )
    elif section == "ai_providers":
        data = dict(body)
        for key_field in ("claudeKey", "openaiKey"):
            val = data.get(key_field, "")
            if val:
                data[key_field] = _encrypt_field(val)
        await db.execute(
            """INSERT INTO user_settings (user_id, ai_providers)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE
               SET ai_providers = $2, updated_at = now()""",
            user_id,
            data,
        )
    else:
        col = section  # privacy | discovery | cleanup | notifications
        await db.execute(
            f"""INSERT INTO user_settings (user_id, {col})
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE
               SET {col} = $2, updated_at = now()""",
            user_id,
            body,
        )

    return {"section": section, "updated": True}


def _open_directory_dialog() -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        path = filedialog.askdirectory(title="Select Obsidian Vault Folder")
        root.destroy()
        return path or ""
    except Exception:
        return ""


@router.get("/browse-directory")
async def browse_directory(
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        path = await loop.run_in_executor(pool, _open_directory_dialog)
    return {"path": path}

