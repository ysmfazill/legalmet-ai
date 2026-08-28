"""Regulatory knowledge schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.enums import (
    CandidateMappingStatus,
    DocumentType,
    RegulationVersionStatus,
    RequirementType,
    RuleStatus,
    SourceType,
    VerificationStatus,
    VersionSelectionStatus,
)
from app.schemas.base import CamelModel
from app.schemas.common import Paginated


class RegulatorySourceOut(CamelModel):
    id: UUID
    name: str
    authority: str
    source_type: SourceType
    canonical_url: str | None = None
    jurisdiction: str
    verification_status: VerificationStatus
    verification_note: str | None = None
    created_at: datetime
    updated_at: datetime


class RegulatorySourceUpdateIn(CamelModel):
    verification_status: VerificationStatus
    verification_note: str | None = None


class RegulatoryDocumentOut(CamelModel):
    id: UUID
    code: str
    title: str
    jurisdiction: str
    authority: str
    description: str | None = None
    official_source_url: str | None = None
    is_demo: bool
    source_id: UUID | None = None
    document_identifier: str | None = None
    document_type: DocumentType
    publication_date: datetime | None = None
    content_hash: str | None = None
    versions: list[RegulatoryVersionOut] = []
    created_at: datetime


class RegulatoryVersionOut(CamelModel):
    id: UUID
    regulation_id: UUID
    version_label: str
    status: RegulationVersionStatus
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    amendment_of_id: UUID | None = None
    source_document_ref: str | None = None
    is_demo: bool
    publication_date: datetime | None = None
    created_at: datetime


class VersionSelectionOut(CamelModel):
    """Outcome of deterministic effective-date version selection."""

    document_id: UUID
    requested_date: datetime
    status: VersionSelectionStatus
    version: RegulatoryVersionOut | None = None


class RequirementProvenanceOut(CamelModel):
    """Answer to "where did this requirement come from?"."""

    authority: str
    document_title: str
    document_identifier: str | None = None
    version_label: str
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    source_reference: str | None = None
    requirement_reference: str | None = None
    source_name: str | None = None
    source_verification_status: VerificationStatus | None = None
    canonical_url: str | None = None


class RegulatoryRequirementOut(CamelModel):
    id: UUID
    version_id: UUID
    rule_code: str
    title: str
    description: str
    requirement_type: RequirementType
    field_key: str | None = None
    expected_format: str | None = None
    mandatory: bool
    applicability_definition: dict[str, Any]
    source_reference: str | None = None
    status: RuleStatus
    is_demo: bool
    created_at: datetime


class RegulatoryRequirementDetailOut(RegulatoryRequirementOut):
    provenance: RequirementProvenanceOut
    version: RegulatoryVersionOut


class PaginatedRequirements(Paginated[RegulatoryRequirementOut]):
    pass


class CandidateRequirementOut(CamelModel):
    """A candidate requirement definition mapped to a detected field.

    Candidate association ONLY — applicability is not evaluated and no
    compliance conclusion exists here (Prompt 6's engine decides).
    """

    requirement_id: UUID
    rule_code: str
    title: str
    source_reference: str | None = None
    version_label: str
    effective_from: datetime | None = None
    source_verification_status: VerificationStatus | None = None


class FieldCandidateOut(CamelModel):
    field_id: UUID
    field_type: str
    field_value: str | None = None
    field_status: str
    candidates: list[CandidateRequirementOut]
    mapping_status: CandidateMappingStatus
    applicability_status: CandidateMappingStatus
    evaluation_status: CandidateMappingStatus


class FieldCandidatesOut(CamelModel):
    inspection_id: UUID
    context_date: datetime
    fields: list[FieldCandidateOut]
    # Constant, explicit boundary markers — never a compliance verdict.
    regulatory_evaluation: str = "AWAITING_REGULATORY_EVALUATION"


# --- Legacy (Prompt 1) schemas, kept for the demo rule flow -----------------


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
    versions: list[RegulatoryVersionOut] = []
