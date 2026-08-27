"""Review queue: findings awaiting human verification.

Surfaces the confidence-aware states that the design mandates — anything the
machine could not confidently clear (review-required, potential violation, low
confidence, insufficient image quality) and that has not yet been reviewed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Pagination, get_current_user, pagination
from app.core.enums import ComplianceStatus
from app.db.session import get_db
from app.models import ComplianceFinding, User
from app.schemas.common import Paginated
from app.schemas.finding import FindingOut

router = APIRouter(prefix="/review", tags=["review"])

_NEEDS_REVIEW = [
    ComplianceStatus.REVIEW_REQUIRED.value,
    ComplianceStatus.POTENTIAL_VIOLATION.value,
    ComplianceStatus.LOW_CONFIDENCE.value,
    ComplianceStatus.IMAGE_QUALITY_INSUFFICIENT.value,
]


@router.get("/queue", response_model=Paginated[FindingOut])
def review_queue(
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Paginated[FindingOut]:
    base = select(ComplianceFinding).where(
        ComplianceFinding.status.in_(_NEEDS_REVIEW),
        ComplianceFinding.is_reviewed.is_(False),
    )
    total = len(db.execute(base).scalars().all())
    page = (
        base.options(
            selectinload(ComplianceFinding.evidence),
            selectinload(ComplianceFinding.review_actions),
        )
        .order_by(ComplianceFinding.created_at.desc())
        .limit(pg.limit)
        .offset(pg.offset)
    )
    findings = db.execute(page).scalars().all()
    return Paginated(
        items=[FindingOut.model_validate(f) for f in findings],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )
