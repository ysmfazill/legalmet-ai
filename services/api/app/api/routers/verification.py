"""Evidence Planner + verification routes (UI-06).

Thin by design: authenticate → enforce role → delegate to VerificationService
→ serialise. The gap analysis, task state machine, assignment guard and
declared-vs-measured boundary live in the service layer — never in a router,
never in the frontend.

Endpoints:

    GET  /inspections/{inspection_id}/evidence-plan   what exists / what is
                                                      missing / what closes it
    POST /inspections/{inspection_id}/verifications   create one task (explicit
                                                      human action, reason
                                                      mandatory)
    GET  /inspections/{inspection_id}/verifications   tasks + recorded results
    GET  /verifications/{task_id}                     one task (read: any
                                                      authenticated user)
    POST /verifications/{task_id}/start               PENDING → IN_PROGRESS
    POST /verifications/{task_id}/result              append one outcome
    POST /verifications/{task_id}/cancel              reason mandatory

Authorization: INSPECTOR/SUPERVISOR/ADMIN write (assignment-guarded in the
service); AUDITOR read-only; anonymous → 401. A citizen can never modify
inspection evidence — they have no account and no write route.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep, require_role
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import User
from app.schemas.verification import (
    EvidencePlanOut,
    MeasurementHistoryOut,
    VerificationCancelRequest,
    VerificationCreateRequest,
    VerificationListOut,
    VerificationResultRequest,
    VerificationTaskOut,
)
from app.services.registry import Services

router = APIRouter(tags=["verification"])

# Who may create/act on verification tasks. AUDITOR is deliberately absent —
# the audit role is read-only and can never modify inspection evidence.
_VERIFY_WRITE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


def _task_out(task, db: Session) -> VerificationTaskOut:
    out = VerificationTaskOut.model_validate(task)
    creator = db.get(User, task.created_by)
    out.created_by_name = getattr(creator, "full_name", None) if creator else None
    for result in out.results:
        recorder = db.get(User, result.recorded_by)
        result.recorded_by_name = (
            getattr(recorder, "full_name", None) if recorder else None
        )
    return out


# -------------------------------------------------------------- evidence plan


@router.get(
    "/inspections/{inspection_id}/evidence-plan", response_model=EvidencePlanOut
)
def get_evidence_plan(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> EvidencePlanOut:
    """The Evidence Planner view: per finding/declaration, the evidence that
    EXISTS, the evidence that is MISSING, and the verification task that
    closes the gap. Evidence completeness is never a compliance verdict."""
    plan = services.verification.evidence_plan(db, inspection_id)
    return EvidencePlanOut.model_validate(plan)


# -------------------------------------------------------------- task endpoints


@router.post(
    "/inspections/{inspection_id}/verifications",
    response_model=VerificationTaskOut,
    status_code=201,
)
def create_verification(
    inspection_id: UUID,
    body: VerificationCreateRequest,
    user: User = Depends(require_role(*_VERIFY_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VerificationTaskOut:
    """Create ONE verification task — an explicit human action with a
    mandatory reason. The engine never auto-creates tasks."""
    task = services.verification.create_task(
        db,
        inspection_id=inspection_id,
        actor=user,
        finding_id=body.finding_id,
        field_id=body.field_id,
        lot_package_id=body.lot_package_id,
        task_type=body.type,
        reason=body.reason,
        requirement_level=body.requirement_level,
    )
    return _task_out(task, db)


@router.get(
    "/inspections/{inspection_id}/verifications",
    response_model=VerificationListOut,
)
def list_verifications(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VerificationListOut:
    """All verification tasks of one inspection with their recorded results
    (oldest first). Read-only: any authenticated role, including AUDITOR."""
    tasks = services.verification.list_tasks(db, inspection_id)
    return VerificationListOut(
        inspection_id=inspection_id,
        tasks=[_task_out(task, db) for task in tasks],
    )


@router.get("/verifications/{task_id}", response_model=VerificationTaskOut)
def get_verification(
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VerificationTaskOut:
    """One verification task with its append-only result history."""
    task = services.verification.get_task(db, task_id)
    return _task_out(task, db)


@router.post(
    "/verifications/{task_id}/start", response_model=VerificationTaskOut
)
def start_verification(
    task_id: UUID,
    user: User = Depends(require_role(*_VERIFY_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VerificationTaskOut:
    """PENDING → IN_PROGRESS (invalid transitions raise 409)."""
    task = services.verification.start_task(db, task_id=task_id, actor=user)
    return _task_out(task, db)


@router.post(
    "/verifications/{task_id}/result", response_model=VerificationTaskOut
)
def record_verification_result(
    task_id: UUID,
    body: VerificationResultRequest,
    user: User = Depends(require_role(*_VERIFY_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VerificationTaskOut:
    """Record ONE verification outcome (append-only).

    MEASUREMENT tasks require measuredValue (> 0) and unit. The measured
    value is stored SEPARATELY from the declared value — the system never
    evaluates the difference against a rule; the inspector does. The
    instrument verification status is stored only when supplied: absent means
    "not recorded", never "verified".
    """
    task = services.verification.record_result(
        db,
        task_id=task_id,
        actor=user,
        measured_value=body.measured_value,
        unit=body.unit,
        observation=body.observation,
        instrument_id=body.instrument_id,
        instrument_verification_status=body.instrument_verification_status,
        notes=body.notes,
        complete=True,
    )
    return _task_out(task, db)


@router.post(
    "/verifications/{task_id}/cancel", response_model=VerificationTaskOut
)
def cancel_verification(
    task_id: UUID,
    body: VerificationCancelRequest,
    user: User = Depends(require_role(*_VERIFY_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VerificationTaskOut:
    """Cancel a task (reason mandatory — the audit trail must show why)."""
    task = services.verification.cancel_task(
        db, task_id=task_id, actor=user, reason=body.reason
    )
    return _task_out(task, db)


# -------------------------------------------------------- measurement history


@router.get(
    "/inspections/{inspection_id}/measurements",
    response_model=MeasurementHistoryOut,
)
def get_measurement_history(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> MeasurementHistoryOut:
    """Every recorded physical measurement of one inspection (append-only).

    Each row pairs the DECLARED value (never overwritten) with the MEASURED
    value, the instrument metadata ("not recorded" is a fact, never
    "verified"), the inspector, the timestamp, the observed difference and
    the frozen regulatory evaluation. Read-only: any authenticated role."""
    rows = services.verification.measurement_history(db, inspection_id)
    user_names: dict = {}
    if rows:
        user_names = {
            u.id: getattr(u, "full_name", None)
            for u in db.execute(
                select(User).where(
                    User.id.in_({r["recorded_by"] for r in rows})
                )
            ).scalars()
        }
    return MeasurementHistoryOut(
        inspection_id=inspection_id,
        measurements=[
            {**row, "recorded_by_name": user_names.get(row["recorded_by"])}
            for row in rows
        ],
    )
