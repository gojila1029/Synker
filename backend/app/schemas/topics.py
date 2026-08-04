from pydantic import BaseModel

# TS counterpart: src/types/index.ts — Topic


class Topic(BaseModel):
    id: str
    label: str
    color: str


class TopicCreate(BaseModel):
    label: str
