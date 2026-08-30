"""Compliance engine schemas (Prompt 6).

These are DECISION-SUPPORT outputs. Compliance findings are system-generated
decision-support outputs — they are not, by themselves, legal enforcement
determinations. Every payload carries the boundary note so no consumer can
mistake a finding for one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import (
    ApplicabilityOutcome,
    ComplianceErrorCode,
    DeterministicRuleType,
    EngineFindingStatus,
    EvaluationStatus,
    FindingReviewState,
    FindingSeverity,
)
from app.schemas.base import CamelModel

FINDING_BOUNDARY_NOTE = (
    "System finding — inspector decision pending. Compliance findings are "
    "system-generated decision-support outputs. They are not, by themselves, "
    "legal enforcement determinations."
)


class ComplianceRuleOut(CamelModel):
    id: UUID
    requirement_id: UUID
    rule_code: str
    rule_type: DeterministicRuleType
    rule_version: int
    configuration: dict[str, Any]
    description: str | None = None
    active: bool
    is_demo: bool
    created_at: datetime


class EngineFindingOut(CamelModel):
    id: UUID
    evaluation_id: UUID
    inspection_id: UUID
    requirement_id: UUID
    rule_id: UUID | None = None
    extracted_field_id: UUID | None = None
    evidence_region_id: UUID | None = None
    image_id: UUID | None = None
    status: EngineFindingStatus
    severity: FindingSeverity
    applicability: ApplicabilityOutcome
    detected_value: str | None = None
    expected_value: str | None = None
    explanation: str
    provenance: dict[str, Any]
    detail: dict[str, Any]
    created_at: datetime
    # --- Prompt 8: human review overlay -------------------------------------
    # PENDING_REVIEW until an authorised human acts. This is the INSPECTOR's
    # verdict on the system finding — distinct from the frozen system status.
    review_state: FindingReviewState = FindingReviewState.PENDING_REVIEW
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_reason: str | None = None
    boundary_note: str = FINDING_BOUNDARY_NOTE


class ComplianceEvaluationOut(CamelModel):
    id: UUID
    inspection_id: UUID
    image_id: UUID | None = None
    regulatory_version_id: UUID | None = None
    status: EvaluationStatus
    engine_version: str
    context_date: datetime
    summary: dict[str, Any]
    error: dict[str, Any] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    actor_id: UUID | None = None
    created_at: datetime
    findings: list[EngineFindingOut] = []
    boundary_note: str = FINDING_BOUNDARY_NOTE


class EvaluateRequest(CamelModel):
    """Optional parameters for POST /inspections/{id}/evaluate."""

    note: str | None = Field(default=None, max_length=500)


class EvaluateResponse(CamelModel):
    """Result of one evaluation run — a new evaluation, never an overwrite."""

    evaluation: ComplianceEvaluationOut
    boundary_note: str = FINDING_BOUNDARY_NOTE


class ComplianceStatusOut(CamelModel):
    """GET /inspections/{id}/compliance — latest evaluation for an inspection.

    When no evaluation has run yet the payload says so explicitly
    (status=NOT_EVALUATED, evaluation=None) — the absence of an evaluation is
    never presented as compliance.
    """

    inspection_id: UUID
    status: EvaluationStatus
    evaluation: ComplianceEvaluationOut | None = None
    boundary_note: str = FINDING_BOUNDARY_NOTE


class RuleTypeOut(CamelModel):
    """One entry of the static rule-type vocabulary (transparency endpoint)."""

    rule_type: DeterministicRuleType
    description: str


class EngineInfoOut(CamelModel):
    """Engine metadata — version, vocabulary, and the honesty contract."""

    engine_version: str
    rule_types: list[RuleTypeOut]
    uses_llm: bool = False
    boundary_note: str = FINDING_BOUNDARY_NOTE


class ComplianceErrorOut(CamelModel):
    """Structured engine error (never converted into a COMPLIANT result)."""

    code: ComplianceErrorCode
    message: str
