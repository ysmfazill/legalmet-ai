"""UI-09 inspection history routes.

/history/inspections — filtered, paginated history + KPIs (real counts).
/history/inspections/{id}/timeline — the real recorded event chain.

Every filter is applied server-side; KPIs are COUNT()s over the filtered set.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination
from app.db.session import get_db
from app.models import User
from app.schemas.common import Paginated
from app.schemas.discovery import InspectionHistoryItem, InspectionHistoryKpis, InspectionTimeline
from app.services.registry import Services

router = APIRouter(prefix="/history", tags=["history"])


class HistoryPage(Paginated[InspectionHistoryItem]):
    """Page + the KPI counts for the CURRENT filter (so the header cards and
    the table can never disagree)."""

    kpis: InspectionHistoryKpis


@router.get("/inspections", response_model=HistoryPage)
def inspection_history(
    q: str | None = Query(default=None, description="reference / product name"),
    status: str | None = Query(default=None),
    result: str | None = Query(default=None),
    source: str | None = Query(
        default=None, description="CITIZEN_COMPLAINT | DIRECT_INSPECTION"
    ),
    inspectorId: UUID | None = Query(default=None),
    productId: UUID | None = Query(default=None),
    dateFrom: datetime | None = Query(default=None),
    dateTo: datetime | None = Query(default=None),
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> HistoryPage:
    items, total, kpis = services.discovery.inspection_history(
        db,
        q=q,
        status=status,
        result=result,
        source=source,
        inspector_id=inspectorId,
        product_id=productId,
        date_from=dateFrom,
        date_to=dateTo,
        limit=pg.limit,
        offset=pg.offset,
    )
    return HistoryPage(items=items, total=total, page=pg.page, page_size=pg.page_size, kpis=kpis)


@router.get("/inspections/{inspection_id}/timeline", response_model=InspectionTimeline)
def inspection_timeline(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionTimeline:
    """The recorded chain (created → package → OCR → findings → evidence
    review → physical verification → decision → report). Only events that
    actually exist in the database are returned — nothing is fabricated."""
    return services.discovery.inspection_timeline(db, inspection_id)
