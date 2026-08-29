"""Evidence Graph routes (Prompt 7).

Thin by design: authenticate → delegate to EvidenceGraphService → serialise.
The graph is READ-ONLY traceability over real persisted data — these routes
never write, never decide compliance, and expose no credentials or storage
paths in node metadata.

Endpoints:

    GET /inspections/{id}/evidence-graph            full graph (latest or
                                                     historical evaluation via
                                                     ?evaluationId=)
    GET /compliance/findings/{id}/evidence-graph    focused trace for one
                                                     ENGINE finding
    GET /fields/{id}/evidence-graph                 reverse trace for one
                                                     extracted field
    GET /evidence-graph                             vocabulary

Namespace note: the spec-level path ``GET /findings/{id}/evidence-graph`` is
already owned by the Prompt 1 DEMO finding flow (``findings.py``); engine
findings live under ``/compliance`` exactly as Prompt 6 established, so the
engine trace keeps that prefix and the demo route is untouched.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep
from app.core.enums import EvidenceEdgeType, EvidenceNodeType
from app.db.session import get_db
from app.models import User
from app.schemas.evidence_trace import (
    EvidenceGraphOut,
    EvidenceStrengthInfo,
)
from app.services.evidence_graph.builder import EVIDENCE_GRAPH_BOUNDARY_NOTE
from app.services.registry import Services

router = APIRouter(tags=["evidence-graph"])


@router.get(
    "/inspections/{inspection_id}/evidence-graph",
    response_model=EvidenceGraphOut,
)
def inspection_evidence_graph(
    inspection_id: UUID,
    evaluation_id: UUID | None = Query(default=None, alias="evaluationId"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EvidenceGraphOut:
    """Full evidence graph for one inspection.

    ``?evaluationId=`` selects a HISTORICAL evaluation — the graph then traces
    the regulatory relationships recorded on that run's findings (the frozen
    provenance), never the newest regulatory data.
    """
    payload = services.evidence_graph.graph_for_inspection(
        db, inspection_id, evaluation_id=evaluation_id
    )
    return EvidenceGraphOut.model_validate(payload)


@router.get(
    "/compliance/findings/{finding_id}/evidence-graph",
    response_model=EvidenceGraphOut,
)
def finding_evidence_graph(
    finding_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EvidenceGraphOut:
    """Focused trace for ONE compliance-engine finding.

    Both directions: Finding → Rule → Requirement → Version → Document →
    Source AND Finding → Field → OCR → Region → Image → Inspection.
    """
    payload = services.evidence_graph.graph_for_finding(db, finding_id)
    return EvidenceGraphOut.model_validate(payload)


@router.get(
    "/fields/{field_id}/evidence-graph",
    response_model=EvidenceGraphOut,
)
def field_evidence_graph(
    field_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EvidenceGraphOut:
    """Reverse trace for ONE extracted field.

    Field → OCR → Region → Image (+ processing run), plus every finding that
    used this field as evidence → requirement → version → source.
    """
    payload = services.evidence_graph.graph_for_field(db, field_id)
    return EvidenceGraphOut.model_validate(payload)


@router.get("/evidence-graph", response_model=EvidenceStrengthInfo)
def evidence_graph_vocabulary(
    _user: User = Depends(get_current_user),
    services: Services = Depends(get_services_dep),
) -> EvidenceStrengthInfo:
    """Node/edge/evidence-strength vocabulary + the traceability boundary note."""
    return EvidenceStrengthInfo(
        strengths=services.evidence_graph.strength_vocabulary(),
        boundary_note=EVIDENCE_GRAPH_BOUNDARY_NOTE,
    )


# Keep the enum vocabularies referenced so drift between route docs and the
# enums is caught at import time.
assert set(n.value for n in EvidenceNodeType)
assert set(e.value for e in EvidenceEdgeType)
