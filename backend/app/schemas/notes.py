from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — Note


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Note(CamelModel):
    id: str
    title: str
    source: str
    generated_at: str
    ai_action: Literal["created", "merged", "updated", "skipped"]
    quality_score: float
    has_duplicate: bool
    content: str
    frontmatter: dict[str, str]
    citations: list[str]
    wiki_links: list[str]
    similarity_reasoning: str
    similar_to: Optional[str] = None
