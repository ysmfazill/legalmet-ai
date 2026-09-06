"""Department Command Center routes (UI-04).

    GET /department/dashboard?days=7|30|90

One aggregated, read-only payload (KPIs, trend, distributions, evidence
completeness, needs-attention, pipeline, locations, recent activity, priority
queue). Aggregation is server-side; the browser never computes dashboard
figures from raw rows.

Security posture:

* Authentication required — anonymous callers get 401 (citizens have no
  account and no route to this data; the citizen surface stays on the
  anonymous /citizen endpoints).
* The dashboard is read-only, so the AUDITOR role may read it like every
  other read surface. Acting on complaints remains restricted to
  INSPECTOR/SUPERVISOR/ADMIN on the transition endpoint (UI-03, unchanged).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.department import DepartmentDashboardOut
from app.services.department import DepartmentDashboardService

router = APIRouter(prefix="/department", tags=["department"])


@router.get("/dashboard", response_model=DepartmentDashboardOut)
def department_dashboard(
    days: int = Query(default=30, ge=7, le=90, description="Trend window in days (7/30/90)."),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DepartmentDashboardOut:
    return DepartmentDashboardService().dashboard(db, window_days=days)
