from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — Settings


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class VaultSettings(BaseModel):
    path: str = ""
    name: str = "My Vault"


class AIProvidersSettings(CamelModel):
    claude_key: str = ""
    openai_key: str = ""
    ollama_url: str = ""
    fallback_order: list[str] = ["claude", "openai"]


class PrivacySettings(CamelModel):
    pii_mode: Literal["regex", "ml"] = "regex"
    block_insurance_data: bool = False
    cloud_block_list: list[str] = []


class DiscoverySettings(CamelModel):
    default_interval: int = 3600
    youtube_interval: int = 3600
    web_interval: int = 86400
    pdf_interval: int = 0
    local_debounce: int = 300


class CleanupSettings(BaseModel):
    youtube: Literal["keep", "zip", "delete"] = "keep"
    web: Literal["keep", "zip", "delete"] = "keep"
    pdf: Literal["keep", "zip", "delete"] = "keep"
    local: Literal["keep", "zip", "delete"] = "keep"


class NotificationsSettings(CamelModel):
    desktop: bool = False
    in_app: bool = True
    email: bool = False
    email_provider: Literal["resend", "sendgrid", "smtp"] = "resend"
    email_address: str = ""


class TeamMember(CamelModel):
    id: str
    name: str
    email: str
    role: Literal["admin", "editor", "viewer"]


class TeamSettings(BaseModel):
    tier: Literal["single", "small", "larger"] = "single"
    members: list[TeamMember] = []


class Settings(CamelModel):
    vault: VaultSettings = VaultSettings()
    ai_providers: AIProvidersSettings = AIProvidersSettings()
    privacy: PrivacySettings = PrivacySettings()
    discovery: DiscoverySettings = DiscoverySettings()
    cleanup: CleanupSettings = CleanupSettings()
    notifications: NotificationsSettings = NotificationsSettings()
    team: TeamSettings = TeamSettings()


# Read-only schemas — AI keys replaced with presence flags so secrets are never returned to clients
class AIProvidersSettingsRead(CamelModel):
    claude_key_set: bool = False
    openai_key_set: bool = False
    ollama_url: str = ""
    fallback_order: list[str] = ["claude", "openai"]


class SettingsRead(CamelModel):
    vault: VaultSettings = VaultSettings()
    ai_providers: AIProvidersSettingsRead = AIProvidersSettingsRead()
    privacy: PrivacySettings = PrivacySettings()
    discovery: DiscoverySettings = DiscoverySettings()
    cleanup: CleanupSettings = CleanupSettings()
    notifications: NotificationsSettings = NotificationsSettings()
    team: TeamSettings = TeamSettings()
