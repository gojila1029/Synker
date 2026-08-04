from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — DashboardStats, ActivityEvent


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DashboardStats(CamelModel):
    pending_approvals: int = 0
    active_jobs: int = 0
    notes_today: int = 0
    sources_indexed: int = 0
    pipeline_counts: dict[str, int] = {}


class ActivityEvent(CamelModel):
    id: str
    type: Literal["approved", "merged", "created", "failed", "synced", "rejected", "indexed"]
    message: str
    timestamp: str
