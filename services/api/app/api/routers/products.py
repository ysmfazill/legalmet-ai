"""UI-09 product repository routes.

/products — searchable product directory with real aggregate counts.
/products/{id} — overview, inspection history, findings history, evidence
gallery. A HISTORICAL RECORD: it never claims current compliance.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination
from app.db.session import get_db
from app.models import User
from app.schemas.common import Paginated
from app.schemas.discovery import ProductDetail, ProductSummary
from app.services.registry import Services

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Paginated[ProductSummary])
def list_products(
    q: str | None = Query(default=None, description="name / category / GTIN"),
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Paginated[ProductSummary]:
    items, total = services.discovery.product_list(
        db, q=q, limit=pg.limit, offset=pg.offset
    )
    return Paginated(items=items, total=total, page=pg.page, page_size=pg.page_size)


@router.get("/{product_id}", response_model=ProductDetail)
def get_product(
    product_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ProductDetail:
    return services.discovery.product_detail(db, product_id)
