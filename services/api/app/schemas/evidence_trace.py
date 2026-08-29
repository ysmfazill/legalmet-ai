"""Evidence Graph schemas (Prompt 7).

The Evidence Graph is a read-only traceability view over REAL persisted
entities (Prompt 4 perception, Prompt 5 regulatory, Prompt 6 compliance,
audit events). Nodes carry whitelisted metadata only — no credentials, no
internal filesystem paths, no storage keys.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import EvidenceEdgeType, EvidenceNodeType, EvidenceStrength
from app.schemas.base import CamelModel


class TraceNode(CamelModel):
    """One graph node == one persisted record (id is ``"<type>:<uuid>"``)."""

    id: str
    type: EvidenceNodeType
    label: str
    metadata: dict[str, Any] | None = None


class TraceEdge(CamelModel):
    """One typed relationship between two real entity nodes."""

    id: str
    source: str
    target: str
    type: EvidenceEdgeType
    metadata: dict[str, Any] | None = None


class EvidenceGraphOut(CamelModel):
    """A bounded, cycle-free traceability graph."""

    root_type: str
    root_id: UUID
    inspection_id: UUID
    evaluation_id: UUID | None = None
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    node_count: int
    edge_count: int
    truncated: bool = False
    boundary_note: str = Field(default="")


class EvidenceStrengthInfo(CamelModel):
    """Vocabulary + semantics of the evidence-strength labels."""

    strengths: list[dict[str, str]]
    boundary_note: str


__all__ = [
    "EvidenceGraphOut",
    "EvidenceStrengthInfo",
    "TraceEdge",
    "TraceNode",
    "EvidenceStrength",
]
