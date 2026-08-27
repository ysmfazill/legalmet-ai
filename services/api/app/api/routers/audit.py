"""Audit trail + model-version provenance routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination, require_role
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import AuditEvent, ModelVersion, User
from app.schemas.audit import AuditEventOut, ModelVersionOut
from app.schemas.common import Paginated
from app.services.registry import Services

router = APIRouter(tags=["audit"])


@router.get("/inspections/{inspection_id}/audit", response_model=list[AuditEventOut])
def inspection_audit(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[AuditEventOut]:
    events = services.audit.list_for_inspection(db, inspection_id)
    return [AuditEventOut.model_validate(e) for e in events]


@router.get("/audit", response_model=Paginated[AuditEventOut])
def recent_audit(
    pg: Pagination = Depends(pagination),
    _user: User = Depends(require_role(UserRole.ADMIN, UserRole.AUDITOR, UserRole.SUPERVISOR)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Paginated[AuditEventOut]:
    total = db.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    events = services.audit.list_recent(db, limit=pg.limit, offset=pg.offset)
    return Paginated(
        items=[AuditEventOut.model_validate(e) for e in events],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


@router.get("/model-versions", response_model=list[ModelVersionOut])
def model_versions(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ModelVersionOut]:
    rows = db.execute(select(ModelVersion).order_by(ModelVersion.service_type)).scalars().all()
    return [ModelVersionOut.model_validate(m) for m in rows]
