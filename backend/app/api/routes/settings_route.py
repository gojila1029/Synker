from typing import Any

import asyncpg
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
    else:
        col = section  # ai_providers | privacy | discovery | cleanup | notifications
        # P2-3 WARNING: ai_providers JSONB stores claudeKey/openaiKey as plaintext.
        # Do NOT allow real API keys to be stored until Supabase Vault or column-level
        # encryption is implemented. See follow-up.md P2-3.
        await db.execute(
            f"""INSERT INTO user_settings (user_id, {col})
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE
               SET {col} = $2, updated_at = now()""",
            user_id,
            body,  # asyncpg handles dict→jsonb
        )

    return {"section": section, "updated": True}

