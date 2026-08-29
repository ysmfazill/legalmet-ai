"""Compliance engine routes (Prompt 6).

Thin by design: authenticate → delegate to ComplianceService → serialise.
All compliance logic lives in ``app/services/compliance`` — never in a router.

Endpoints (Phase 16):

    POST /inspections/{id}/evaluate       run one evaluation (INSPECTOR+)
    GET  /inspections/{id}/compliance     latest evaluation + findings
    GET  /inspections/{id}/findings       latest evaluation's findings
    GET  /compliance/evaluations/{id}     one evaluation + findings
    GET  /compliance/findings/{id}        one finding with explanation
    GET  /compliance/engine               engine info (rule vocabulary, no-LLM)

Every response carries the boundary note: compliance findings are
system-generated decision-support outputs — not, by themselves, legal
enforcement determinations.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    Pagination,
    get_current_user,
    get_services_dep,
    pagination,
    require_role,
)
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import User
from app.schemas.common import Paginated
from app.schemas.compliance import (
    ComplianceEvaluationOut,
    ComplianceStatusOut,
    EngineFindingOut,
    EngineInfoOut,
    EvaluateRequest,
    EvaluateResponse,
)
from app.services.registry import Services

router = APIRouter(tags=["compliance"])

# Only inspection-side roles may trigger an evaluation (it writes audit events).
_EVALUATE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


@router.post(
    "/inspections/{inspection_id}/evaluate",
    response_model=EvaluateResponse,
)
def evaluate_inspection(
    inspection_id: UUID,
    body: EvaluateRequest | None = None,
    user: User = Depends(require_role(*_EVALUATE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EvaluateResponse:
    """Run one deterministic compliance evaluation over an inspection.

    Creates a NEW evaluation — historical evaluations are never overwritten.
    Note: the request body is accepted (future parameters) but the engine's
    behaviour is fully determined by the inspection's perception evidence and
    the regulatory version in force; there is nothing to tune per request.
    """
    evaluation = services.compliance.evaluate_inspection(
        db, inspection_id=inspection_id, actor_id=user.id
    )
    out = ComplianceEvaluationOut.model_validate(evaluation)
    return EvaluateResponse(evaluation=out)


@router.get(
    "/inspections/{inspection_id}/compliance",
    response_model=ComplianceStatusOut,
)
def get_compliance_status(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ComplianceStatusOut:
    """Latest evaluation for an inspection, or an explicit NOT_EVALUATED."""
    evaluation = services.compliance.latest_evaluation(db, inspection_id)
    if evaluation is None:
        return ComplianceStatusOut(inspection_id=inspection_id, status="NOT_EVALUATED")
    return ComplianceStatusOut(
        inspection_id=inspection_id,
        status=evaluation.status,
        evaluation=ComplianceEvaluationOut.model_validate(evaluation),
    )


@router.get(
    "/inspections/{inspection_id}/compliance/findings",
    response_model=list[EngineFindingOut],
)
def list_findings(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[EngineFindingOut]:
    """Findings of the LATEST compliance evaluation for this inspection.

    Path note: ``GET /inspections/{id}/findings`` (no ``/compliance`` segment)
    is the Prompt 1 endpoint and continues to serve the demo-flow findings,
    unchanged. Engine findings live under the ``/compliance`` namespace so the
    two vocabularies (demo ComplianceStatus vs engine EngineFindingStatus)
    never mix.
    """
    findings = services.compliance.findings_for_inspection(db, inspection_id)
    return [EngineFindingOut.model_validate(f) for f in findings]


@router.get(
    "/compliance/evaluations/{evaluation_id}",
    response_model=ComplianceEvaluationOut,
)
def get_evaluation(
    evaluation_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ComplianceEvaluationOut:
    evaluation = services.compliance.get_evaluation(db, evaluation_id)
    return ComplianceEvaluationOut.model_validate(evaluation)


@router.get(
    "/compliance/findings/{finding_id}",
    response_model=EngineFindingOut,
)
def get_finding(
    finding_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EngineFindingOut:
    finding = services.compliance.get_finding(db, finding_id)
    return EngineFindingOut.model_validate(finding)


@router.get("/compliance/engine", response_model=EngineInfoOut)
def get_engine_info(
    _user: User = Depends(get_current_user),
    services: Services = Depends(get_services_dep),
) -> EngineInfoOut:
    """Engine metadata: version, rule-type vocabulary, and the no-LLM contract."""
    return EngineInfoOut.model_validate(services.compliance.engine_info())


@router.get("/compliance/review/queue", response_model=Paginated[EngineFindingOut])
def compliance_review_queue(
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Paginated[EngineFindingOut]:
    """Engine findings awaiting an inspector decision (Phase 18).

    Each entry is a SYSTEM finding — the inspector's decision is pending. This
    queue performs no approval or rejection: recording a final enforcement
    decision is a later phase, and the inspector remains responsible for it.
    """
    items, total = services.compliance.review_queue(db, limit=pg.limit, offset=pg.offset)
    return Paginated(
        items=[EngineFindingOut.model_validate(f) for f in items],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )
