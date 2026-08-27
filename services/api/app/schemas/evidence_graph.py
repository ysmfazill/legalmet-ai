"""Evidence graph schema (powers the Evidence Viewer "Why?" panel)."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelModel

NodeType = Literal[
    "INSPECTION",
    "PACKAGE",
    "IMAGE",
    "IMAGE_REGION",
    "EXTRACTED_FIELD",
    "EVIDENCE",
    "RULE",
    "RULE_VERSION",
    "FINDING",
    "REVIEW_ACTION",
]


class EvidenceGraphNode(CamelModel):
    id: str
    type: NodeType
    label: str
    data: dict[str, Any] | None = None


class EvidenceGraphEdge(CamelModel):
    # `from` is a Python keyword, so the field is `from_` with explicit aliases
    # matching the TS contract ({ from, to, relation }).
    from_: str = Field(validation_alias="from", serialization_alias="from")
    to: str
    relation: str


class EvidenceGraph(CamelModel):
    finding_id: UUID
    nodes: list[EvidenceGraphNode]
    edges: list[EvidenceGraphEdge]
