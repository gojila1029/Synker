from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — Source


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Source(CamelModel):
    id: str
    type: Literal["youtube", "web", "pdf", "local"]
    source_scope: Literal["direct_resource", "discovery_provider"] = "direct_resource"
    title: str
    url: str
    topic_id: str | None = None
    status: Literal["queued", "processing", "done", "failed"] = "queued"
    added_at: str
    schedule: str | None = None
    keyword: str | None = None
    discovery_mode: Literal["single", "channel_playlist", "keyword", "web_keyword"] | None = None
    discovery_limit: int = 25


class SourceCreate(CamelModel):
    type: Literal["youtube", "web", "pdf", "local"] = "web"
    source_scope: Literal["direct_resource", "discovery_provider"] = "direct_resource"
    title: str = ""
    url: str = ""
    topic_id: str | None = None
    keyword: str | None = None
    discovery_mode: Literal["single", "channel_playlist", "keyword", "web_keyword"] | None = None
    discovery_limit: int = Field(default=25, ge=1, le=50)

    @model_validator(mode="after")
    def validate_discovery_constraints(self) -> "SourceCreate":
        # YouTube + web_keyword is invalid
        if self.discovery_mode == "web_keyword" and self.type == "youtube":
            raise ValueError("YouTube sources cannot use web_keyword discovery mode")

        # Web + keyword is invalid
        if self.discovery_mode == "keyword" and self.type == "web":
            raise ValueError("Web sources cannot use keyword discovery mode")

        # keyword/web_keyword require non-empty keyword
        if self.discovery_mode in ("keyword", "web_keyword") and not self.keyword:
            raise ValueError(f"{self.discovery_mode} discovery mode requires a non-empty keyword")

        return self
