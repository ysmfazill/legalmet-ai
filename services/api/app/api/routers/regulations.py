"""Regulatory knowledge routes: regulations, rules, and validator registry.

Read-only in the foundation phase. Everything returned is DEMO data and is
flagged as such (``isDemo`` on each row).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination
from app.db.session import get_db
from app.models import User
from app.schemas.common import Paginated
from app.schemas.regulatory import RegulationOut, RuleOut
from app.services.registry import Services
from app.services.rules.validators import registered_validators

router = APIRouter(tags=["regulatory"])


@router.get("/regulations", response_model=list[RegulationOut])
def list_regulations(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[RegulationOut]:
    regulations = services.regulatory.list_regulations(db)
    return [RegulationOut.model_validate(r) for r in regulations]


@router.get("/rules/validators", response_model=list[str])
def list_validators(_user: User = Depends(get_current_user)) -> list[str]:
    # The deterministic validators available to rules (structural, not legal).
    return registered_validators()


@router.get("/rules", response_model=Paginated[RuleOut])
def list_rules(
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Paginated[RuleOut]:
    rules, total = services.regulatory.list_rules(db, limit=pg.limit, offset=pg.offset)
    return Paginated(
        items=[RuleOut.model_validate(r) for r in rules],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )
