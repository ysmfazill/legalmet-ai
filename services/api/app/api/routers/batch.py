"""Batch inspection routes — the container for batch/analytics intelligence.

Foundation phase: create a batch, list batches, and read a batch with freshly
recomputed aggregate stats. Inspections join a batch via ``batchId`` at
creation time.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    Pagination,
    get_current_user,
    get_services_dep,
    pagination,
    require_role,
)
from app.core.enums import BatchStatus, UserRole
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import BatchInspection, User
from app.schemas.analytics import BatchInspectionOut
from app.schemas.base import CamelModel
from app.schemas.common import Paginated
from app.services.registry import Services

router = APIRouter(prefix="/batches", tags=["batch"])


class CreateBatchRequest(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


@router.post("", response_model=BatchInspectionOut, status_code=201)
def create_batch(
    body: CreateBatchRequest,
    user: User = Depends(
        require_role(UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> BatchInspectionOut:
    batch = BatchInspection(
        name=body.name,
        description=body.description,
        status=BatchStatus.OPEN.value,
        total_count=0,
        created_by=user.id,
        is_demo=False,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return BatchInspectionOut.model_validate(batch)


@router.get("", response_model=Paginated[BatchInspectionOut])
def list_batches(
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Paginated[BatchInspectionOut]:
    base = select(BatchInspection)
    total = len(db.execute(base).scalars().all())
    rows = db.execute(
        base.order_by(BatchInspection.created_at.desc()).limit(pg.limit).offset(pg.offset)
    ).scalars().all()
    return Paginated(
        items=[BatchInspectionOut.model_validate(b) for b in rows],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


@router.get("/{batch_id}", response_model=BatchInspectionOut)
def get_batch(
    batch_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> BatchInspectionOut:
    batch = db.get(BatchInspection, batch_id)
    if batch is None:
        raise NotFoundError(f"Batch not found: {batch_id}")
    services.analytics.compute_batch_stats(db, batch)
    db.commit()
    db.refresh(batch)
    return BatchInspectionOut.model_validate(batch)
