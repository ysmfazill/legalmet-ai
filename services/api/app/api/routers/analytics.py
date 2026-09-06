"""Analytics routes: dashboard summary and recurring-violation intelligence."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep
from app.db.session import get_db
from app.models import User
from app.schemas.analytics import DashboardSummary, OperationalAnalytics, RecurringViolation
from app.services.registry import Services

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> DashboardSummary:
    return services.analytics.dashboard_summary(db)


@router.get("/recurring-violations", response_model=list[RecurringViolation])
def recurring_violations(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[RecurringViolation]:
    return services.analytics.recurring_violations(db)


@router.get("/operational", response_model=OperationalAnalytics)
def operational(
    granularity: str = Query(default="month", pattern="^(day|week|month)$"),
    dateFrom: datetime | None = Query(default=None),
    dateTo: datetime | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> OperationalAnalytics:
    """Operational intelligence (UI-09 §12–§23) — every figure is a real
    COUNT over stored rows; rates with zero denominators are null (N/A)."""
    return services.analytics.operational(
        db, granularity=granularity, date_from=dateFrom, date_to=dateTo
    )
