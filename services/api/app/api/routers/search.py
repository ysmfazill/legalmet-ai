"""UI-09 global search route.

One endpoint, grouped results, server-side, RBAC-aware. Authenticated staff
only — anonymous access is 401 (checked by get_current_user). The service
never selects citizen reporter PII.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep
from app.db.session import get_db
from app.models import User
from app.schemas.discovery import SearchResults
from app.services.registry import Services

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResults)
def global_search(
    q: str = Query(min_length=0),
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> SearchResults:
    """Grouped search over inspections, complaints, products, reports,
    findings and evidence. Case-insensitive, trimmed, server-side."""
    return services.discovery.search(db, q=q, actor=user, limit=limit)
