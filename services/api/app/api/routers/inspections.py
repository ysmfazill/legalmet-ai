"""Inspection routes: create, list, detail, image registration, analyze.

Handlers are thin — all orchestration lives in ``services.inspection``.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination
from app.db.session import get_db
from app.models import Inspection, User
from app.schemas.common import Paginated
from app.schemas.image import ImageOut, RegisterImageRequest
from app.schemas.inspection import (
    AnalyzeInspectionRequest,
    CreateInspectionRequest,
    InspectionDetailOut,
    InspectionSummaryOut,
)
from app.services.registry import Services

router = APIRouter(prefix="/inspections", tags=["inspections"])


def _detail(services: Services, db: Session, inspection: Inspection) -> InspectionDetailOut:
    out = InspectionDetailOut.model_validate(inspection)
    out.finding_counts = services.analytics.finding_counts(db, inspection_id=inspection.id)
    return out


@router.post("", response_model=InspectionDetailOut, status_code=201)
def create_inspection(
    body: CreateInspectionRequest,
    user: User = Depends(get_current_user),
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
        out.append(summary)
    return Paginated(items=out, total=total, page=pg.page, page_size=pg.page_size)


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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDetailOut:
    inspection = services.inspection.analyze(
        db, inspection_id=inspection_id, request=body, actor_id=user.id
    )
    return _detail(services, db, inspection)
