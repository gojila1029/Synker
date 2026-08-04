from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# TS counterpart: src/types/index.ts — VaultNode, VaultFile


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class VaultNode(BaseModel):
    name: str
    path: str
    type: Literal["file", "folder"]
    children: Optional[list["VaultNode"]] = None


VaultNode.model_rebuild()


class VaultFile(CamelModel):
    path: str
    content: str
    frontmatter: dict[str, str]
    last_modified: str
    word_count: int
    backlinks: int
    graph_node_type: str
    cloud_safe: bool
