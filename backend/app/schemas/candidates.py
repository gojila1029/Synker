from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — Candidate


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Candidate(CamelModel):
    id: str
    title: str
    source_info: str
    domain: str
    published_at: str
    topic_id: Optional[str] = None
    recommendation: Literal["process", "merge", "skip", "review"]
    quality_score: float
    confidence_score: float
    duplicate_score: float
    expected_notes: int
    estimated_tokens: int
    summary: str
    extracted_topics: list[str]
    status: Literal["pending", "approved", "rejected"]


class BulkIds(BaseModel):
    ids: list[str]
