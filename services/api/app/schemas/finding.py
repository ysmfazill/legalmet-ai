"""Finding + evidence + review schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import ComplianceStatus, EvidenceType, FieldType, ReviewActionType
from app.schemas.base import CamelModel


class EvidenceOut(CamelModel):
    id: UUID
    finding_id: UUID
    evidence_type: EvidenceType
    image_id: UUID | None = None
    image_region_id: UUID | None = None
    extracted_field_id: UUID | None = None
    rule_id: UUID | None = None
    data: dict[str, Any] | None = None
    created_at: datetime


class ReviewActionOut(CamelModel):
    id: UUID
    finding_id: UUID
    reviewer_id: UUID | None = None
    action: ReviewActionType
    corrected_status: ComplianceStatus | None = None
    reason: str | None = None
    note: str | None = None
    created_at: datetime


class FindingOut(CamelModel):
    id: UUID
    inspection_id: UUID
    package_id: UUID
    rule_id: UUID | None = None
    rule_version_id: UUID | None = None
    field_type: FieldType | None = None
    status: ComplianceStatus
    confidence: float
    rationale: str
    model_version_id: UUID | None = None
    review_status: ComplianceStatus | None = None
    is_reviewed: bool
    is_demo: bool
    created_at: datetime
    evidence: list[EvidenceOut] = []
    review_actions: list[ReviewActionOut] = []


class ReviewFindingRequest(CamelModel):
    action: ReviewActionType
    corrected_status: ComplianceStatus | None = None
    reason: str | None = None
    note: str | None = Field(default=None, max_length=2000)
