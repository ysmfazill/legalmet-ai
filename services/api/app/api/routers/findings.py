"""Finding routes: list per inspection, detail, evidence graph, and review.

The evidence-graph endpoint powers the "Why?" panel — it returns the full
provenance chain behind a finding. The review endpoint records a human decision
without ever mutating the original machine ``status``.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_services_dep, require_role
from app.core.enums import UserRole
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import ComplianceFinding, User
from app.schemas.evidence_graph import EvidenceGraph
from app.schemas.finding import FindingOut, ReviewFindingRequest
from app.services.registry import Services

router = APIRouter(tags=["findings"])

_FINDING_LOAD = (
    selectinload(ComplianceFinding.evidence),
    selectinload(ComplianceFinding.review_actions),
)


def _load_finding(db: Session, finding_id: UUID) -> ComplianceFinding:
    stmt = (
        select(ComplianceFinding)
        .where(ComplianceFinding.id == finding_id)
        .options(*_FINDING_LOAD)
    )
    finding = db.execute(stmt).scalar_one_or_none()
    if finding is None:
        raise NotFoundError(f"Finding not found: {finding_id}")
    return finding


@router.get("/inspections/{inspection_id}/findings", response_model=list[FindingOut])
def list_findings(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FindingOut]:
    stmt = (
        select(ComplianceFinding)
        .where(ComplianceFinding.inspection_id == inspection_id)
        .options(*_FINDING_LOAD)
        .order_by(ComplianceFinding.created_at.asc())
    )
    findings = db.execute(stmt).scalars().all()
    return [FindingOut.model_validate(f) for f in findings]


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FindingOut:
    return FindingOut.model_validate(_load_finding(db, finding_id))


@router.get("/findings/{finding_id}/evidence-graph", response_model=EvidenceGraph)
def evidence_graph(
    finding_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EvidenceGraph:
    return services.evidence.build_graph(db, finding_id)


@router.post("/findings/{finding_id}/review", response_model=FindingOut)
def review_finding(
    finding_id: UUID,
    body: ReviewFindingRequest,
    user: User = Depends(require_role(UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> FindingOut:
    finding = _load_finding(db, finding_id)
    services.review.record_review(db, finding=finding, reviewer_id=user.id, request=body)
    db.commit()
    return FindingOut.model_validate(_load_finding(db, finding_id))
