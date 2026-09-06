"""Inspection routes: create, list, detail, image registration, analyze.

Handlers are thin — all orchestration lives in ``services.inspection``.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    Pagination,
    get_current_user,
    get_services_dep,
    pagination,
    require_role,
)
from app.core.enums import UserRole
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import Inspection, User
from app.schemas.citizen import SourceComplaintOut
from app.schemas.common import Paginated
from app.schemas.image import ImageOut, RegisterImageRequest
from app.schemas.inspection import (
    AnalyzeInspectionRequest,
    AssignInspectionRequest,
    CreateInspectionRequest,
    InspectionDetailOut,
    InspectionSummaryOut,
    SourceComplaintRefOut,
)
from app.services.registry import Services

router = APIRouter(prefix="/inspections", tags=["inspections"])

# Write operations require an operational role (Prompt 9, Phase 10): AUDITOR is
# a read-only role and must not create inspections, register images, or start
# analysis.
_WRITE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)

# UI-05: assigning an inspection to an inspector is a DEPARTMENT act —
# operational inspectors execute, they do not distribute work. Mirrored in
# the frontend action visibility.
_ASSIGN_ROLES = (UserRole.SUPERVISOR, UserRole.ADMIN)


def _detail(services: Services, db: Session, inspection: Inspection) -> InspectionDetailOut:
    out = InspectionDetailOut.model_validate(inspection)
    out.finding_counts = services.analytics.finding_counts(db, inspection_id=inspection.id)
    out.inspector_name = inspection.inspector.full_name if inspection.inspector else None
    _attach_source_ref(out, inspection)
    return out


def _attach_source_ref(out: InspectionSummaryOut, inspection: Inspection) -> None:
    """Serialize the complaint provenance carried on the ORM row (UI-05)."""
    report = inspection.source_complaint
    if report is None:
        return
    out.source_complaint = SourceComplaintRefOut(
        id=report.id,
        reference=report.reference,
        status=report.status,
        issue=report.issue,
        location=report.location,
        priority=(report.official_priority or report.screening_risk),
    )


@router.post("", response_model=InspectionDetailOut, status_code=201)
def create_inspection(
    body: CreateInspectionRequest,
    user: User = Depends(require_role(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDetailOut:
    inspection = services.inspection.create_inspection(db, inspector_id=user.id, request=body)
    return _detail(services, db, inspection)


@router.get("", response_model=Paginated[InspectionSummaryOut])
def list_inspections(
    status: str | None = Query(default=None),
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Paginated[InspectionSummaryOut]:
    items, total = services.inspection.list(db, status=status, limit=pg.limit, offset=pg.offset)
    counts = services.analytics.finding_counts_for_inspections(db, [i.id for i in items])
    out: list[InspectionSummaryOut] = []
    for inspection in items:
        summary = InspectionSummaryOut.model_validate(inspection)
        summary.finding_counts = counts.get(inspection.id)
        summary.inspector_name = (
            inspection.inspector.full_name if inspection.inspector else None
        )
        _attach_source_ref(summary, inspection)
        out.append(summary)
    return Paginated(items=out, total=total, page=pg.page, page_size=pg.page_size)


@router.get("/{inspection_id}/source-complaint", response_model=SourceComplaintOut)
def get_source_complaint(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> SourceComplaintOut:
    """The citizen complaint this targeted inspection originated from (UI-05):
    the inspection brief (reported issue, product, location, priority) plus the
    immutable SOURCE evidence the citizen submitted. Read-only for any
    authenticated staff role — inspectors need it to verify, auditors to trace.
    """
    report = services.inspection.get_source_complaint(db, inspection_id)
    if report is None:
        raise NotFoundError(
            f"Inspection {inspection_id} did not originate from a citizen complaint."
        )
    return SourceComplaintOut(
        id=report.id,
        reference=report.reference,
        status=report.status,
        product=report.product,
        shop=report.shop,
        location=report.location,
        issue=report.issue,
        description=report.description,
        reporter_name=report.reporter_name,
        screening_risk=report.screening_risk,
        official_priority=report.official_priority,
        assigned_inspector_id=report.assigned_inspector_id,
        assigned_inspector_name=(
            report.inspector.full_name if report.inspector else None
        ),
        evidence=report.evidence,
        event_count=len(report.events),
        created_at=report.created_at,
    )


@router.post("/{inspection_id}/assign", response_model=InspectionDetailOut)
def assign_inspection(
    inspection_id: UUID,
    body: AssignInspectionRequest,
    user: User = Depends(require_role(*_ASSIGN_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDetailOut:
    """Assign (or explicitly reassign) the inspector of an inspection (UI-05).

    RBAC: SUPERVISOR / ADMIN only — a department act, enforced here in the
    backend, not just hidden in the frontend. Every assignment is audited and
    the source complaint (if any) is kept in sync.
    """
    inspection = services.inspection.assign_inspection(
        db,
        inspection_id=inspection_id,
        actor=user,
        inspector_id=body.inspector_id,
        note=body.note,
        reassign=body.reassign,
    )
    return _detail(services, db, inspection)


@router.get("/{inspection_id}", response_model=InspectionDetailOut)
def get_inspection(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDetailOut:
    inspection = services.inspection.get(db, inspection_id)
    return _detail(services, db, inspection)


@router.post("/{inspection_id}/images", response_model=ImageOut, status_code=201)
def add_image(
    inspection_id: UUID,
    body: RegisterImageRequest,
    user: User = Depends(require_role(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ImageOut:
    image = services.inspection.add_image(
        db, inspection_id=inspection_id, request=body, actor_id=user.id
    )
    return ImageOut.model_validate(image)


@router.post("/{inspection_id}/analyze", response_model=InspectionDetailOut)
def analyze_inspection(
    inspection_id: UUID,
    body: AnalyzeInspectionRequest | None = None,
    user: User = Depends(require_role(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDetailOut:
    inspection = services.inspection.analyze(
        db, inspection_id=inspection_id, request=body, actor_id=user.id
    )
    return _detail(services, db, inspection)
