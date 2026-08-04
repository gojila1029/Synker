from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — Source


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Source(CamelModel):
    id: str
    type: Literal["youtube", "web", "pdf", "local"]
    title: str
    url: str
    topic_id: Optional[str] = None
    status: Literal["queued", "processing", "done", "failed"] = "queued"
    added_at: str
    schedule: Optional[str] = None


class SourceCreate(CamelModel):
    type: Literal["youtube", "web", "pdf", "local"] = "web"
    title: str = ""
    url: str = ""
    topic_id: Optional[str] = None
