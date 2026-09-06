"""Lot intelligence routes (UI-07).

Thin by design: authenticate → enforce role → delegate to LotService →
serialise. The sampling honesty contract (configured procedure vs
AI-recommended + inspector confirmation), the observed-vs-legal labelling and
the evidence gate on the lot decision live in the service layer.

Endpoints:

    POST /inspections/{inspection_id}/lots   create a lot + package records
    GET  /inspections/{inspection_id}/lots   lot summaries with progress
    GET  /lots/{lot_id}                      full lot intelligence read model
    POST /lots/{lot_id}/sample               draw one audited, reproducible
                                             sample
    POST /lots/{lot_id}/decision             the explicit, gated lot result

Lot measurements are NOT recorded here — they reuse the verification routes
with lotPackageId as the anchor, so RBAC, validation and the append-only
contract exist exactly once.

Authorization: INSPECTOR/SUPERVISOR/ADMIN write (assignment-guarded in the
service); any authenticated user reads. A citizen can never alter lot
evidence — they have no account and no write route.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep, require_role
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import User
from app.schemas.lot import (
    LotCreateRequest,
    LotDecisionRequest,
    LotDetailOut,
    LotListOut,
    SampleGenerateRequest,
    SamplingRunOut,
)
from app.services.registry import Services

router = APIRouter(tags=["lots"])

_LOT_WRITE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


@router.post(
    "/inspections/{inspection_id}/lots",
    response_model=LotDetailOut,
    status_code=201,
)
def create_lot(
    inspection_id: UUID,
    body: LotCreateRequest,
    user: User = Depends(require_role(*_LOT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> LotDetailOut:
    """Create a lot + its positional package records. The declared quantity
    is stored verbatim and is immutable after creation."""
    lot = services.lots.create_lot(
        db,
        inspection_id=inspection_id,
        actor=user,
        label=body.label,
        declared_value=body.declared_value,
        lot_size=body.lot_size,
        product_id=body.product_id,
        location=body.location,
        notes=body.notes,
    )
    return LotDetailOut.model_validate(services.lots.get_lot(db, lot.id))


@router.get(
    "/inspections/{inspection_id}/lots", response_model=LotListOut
)
def list_lots(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> LotListOut:
    """Lot summaries with progress (e.g. '7 / 10 measurements completed')."""
    return LotListOut(
        inspection_id=inspection_id,
        lots=services.lots.list_lots(db, inspection_id),
    )


@router.get("/lots/{lot_id}", response_model=LotDetailOut)
def get_lot(
    lot_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> LotDetailOut:
    """The full lot read model: packages with their real measurement records,
    sampling runs, the configured procedure (or its absence) and OBSERVED
    statistics. Read-only: any authenticated role, including AUDITOR."""
    return LotDetailOut.model_validate(services.lots.get_lot(db, lot_id))


@router.post(
    "/lots/{lot_id}/sample", response_model=SamplingRunOut, status_code=201
)
def generate_sample(
    lot_id: UUID,
    body: SampleGenerateRequest,
    user: User = Depends(require_role(*_LOT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> SamplingRunOut:
    """Draw ONE audited, reproducible sample.

    A configured legal procedure drives size/method (referenced by code +
    version). Without one, the run is AI-recommended and requires
    confirmAiSample — otherwise 422 with 'Sampling procedure requires
    inspector confirmation.'. The selected packages persist; the sample is
    never regenerated on read.
    """
    run = services.lots.generate_sample(
        db,
        lot_id=lot_id,
        actor=user,
        sample_size=body.sample_size,
        selection_method=body.selection_method,
        seed=body.seed,
        confirm_ai_sample=body.confirm_ai_sample,
    )
    return SamplingRunOut.model_validate(services.lots.run_row(run))


@router.post("/lots/{lot_id}/decision", response_model=LotDetailOut)
def submit_lot_decision(
    lot_id: UUID,
    body: LotDecisionRequest,
    user: User = Depends(require_role(*_LOT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> LotDetailOut:
    """Submit the explicit lot result (COMPLIANT / NON_COMPLIANT /
    REQUIRES_REVIEW, reason mandatory).

    Gated: sampled packages still lacking measurements block the submission
    with 'Insufficient evidence — N measurements remaining.' Missing evidence
    never implies any outcome.
    """
    services.lots.submit_decision(
        db, lot_id=lot_id, actor=user, decision=body.decision, reason=body.reason
    )
    return LotDetailOut.model_validate(services.lots.get_lot(db, lot_id))
