"""Analytics routes: dashboard summary and recurring-violation intelligence."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep
from app.db.session import get_db
from app.models import User
from app.schemas.analytics import DashboardSummary, RecurringViolation
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
