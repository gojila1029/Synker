from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — Job


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Job(CamelModel):
    id: str
    source_title: str
    type: Literal[
        "Extraction", "Transcription", "Analysis", "PII Check",
        "Note Gen", "Verification", "Graphify Sync", "Cleanup",
    ]
    status: Literal["running", "queued", "done", "completed", "failed"]
    progress: int
    started_at: str
    duration: str
    error: str | None = None
    error_code: str | None = None
    artifact_path: str | None = None
