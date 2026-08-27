"""Regulatory knowledge schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.enums import RegulationVersionStatus, RuleStatus
from app.schemas.base import CamelModel


class RuleApplicabilityOut(CamelModel):
    id: UUID
    rule_id: UUID
    product_category: str
    condition_expression: dict[str, Any]
    is_demo: bool
    created_at: datetime


class RuleOut(CamelModel):
    id: UUID
    regulation_version_id: UUID
    rule_code: str
    title: str
    requirement_summary: str
    validation_logic_ref: str
    evidence_requirement: str | None = None
    status: RuleStatus
    is_demo: bool
    created_at: datetime


class RegulationVersionOut(CamelModel):
    id: UUID
    regulation_id: UUID
    version_label: str
    status: RegulationVersionStatus
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    amendment_of_id: UUID | None = None
    source_document_ref: str | None = None
    is_demo: bool
    created_at: datetime


class RegulationOut(CamelModel):
    id: UUID
    code: str
    title: str
    jurisdiction: str
    authority: str
    description: str | None = None
    official_source_url: str | None = None
    is_demo: bool
    created_at: datetime
    versions: list[RegulationVersionOut] = []
