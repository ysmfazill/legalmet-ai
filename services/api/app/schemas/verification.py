"""Evidence Planner + verification schemas (UI-06).

The evidence plan answers, per finding/declaration: what was detected, which
requirement was evaluated, what evidence supports it, what is MISSING, and
which inspector verification closes the gap. Verification tasks/results are
human actions — the engine never creates or fills them.

Every payload carries the declared-vs-measured boundary: a measurement is
EVIDENCE recorded by an authorised human from an appropriate instrument; it
is never automatically evaluated into a compliance verdict.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import (
    ApplicabilityOutcome,
    EngineFindingStatus,
    EvidenceItemStatus,
    EvidenceRequirementKind,
    FindingReviewState,
    FindingSeverity,
    VerificationLevel,
    VerificationTaskStatus,
    VerificationTaskType,
)
from app.schemas.base import CamelModel

VERIFICATION_BOUNDARY_NOTE = (
    "METRASIGHT reads declared values; it cannot measure physical contents. "
    "A verification task is closed only by an authorised inspector recording "
    "evidence (e.g. a manual reading from an appropriate Legal Metrology "
    "instrument). A recorded measurement is evidence for the inspector's "
    "decision — the system never converts a declared-vs-measured difference "
    "into an automatic violation."
)


# --------------------------------------------------------------------- results


class VerificationResultOut(CamelModel):
    id: UUID
    task_id: UUID
    recorded_by: UUID
    recorded_by_name: str | None = None
    recorded_at: datetime
    measured_value: float | None = None
    unit: str | None = None
    observation: str | None = None
    instrument_id: str | None = None
    instrument_verification_status: str | None = None
    notes: str | None = None
    created_at: datetime


class VerificationTaskOut(CamelModel):
    id: UUID
    inspection_id: UUID
    finding_id: UUID | None = None
    extracted_field_id: UUID | None = None
    lot_package_id: UUID | None = None
    task_type: VerificationTaskType
    requirement_level: VerificationLevel
    reason: str
    status: VerificationTaskStatus
    created_by: UUID
    created_by_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_reason: str | None = None
    results: list[VerificationResultOut] = []
    created_at: datetime
    boundary_note: str = VERIFICATION_BOUNDARY_NOTE


class VerificationListOut(CamelModel):
    inspection_id: UUID
    tasks: list[VerificationTaskOut] = []
    boundary_note: str = VERIFICATION_BOUNDARY_NOTE


# ----------------------------------------------------------------- write forms


class VerificationCreateRequest(CamelModel):
    """POST /inspections/{id}/verifications — create one verification task.

    Anchor: the engine finding whose gap this closes, and/or the extracted
    declaration (pre-evaluation rows), or a lot package (a lot measurement
    that gates the LOT decision, not the inspection decision). The
    requirement level defaults by type (MEASUREMENT → REQUIRED,
    INSPECTOR_OBSERVATION → RECOMMENDED) and may be overridden by the
    creating human.
    """

    finding_id: UUID | None = None
    field_id: UUID | None = None
    lot_package_id: UUID | None = None
    type: VerificationTaskType = VerificationTaskType.MEASUREMENT
    reason: str = Field(min_length=3, max_length=2000)
    requirement_level: VerificationLevel | None = None


class VerificationResultRequest(CamelModel):
    """POST /verifications/{task_id}/result — record one verification outcome.

    MEASUREMENT tasks require ``measured_value`` (> 0) and ``unit``. The
    instrument verification status is recorded only when supplied — an absent
    value means "not recorded", never "verified".
    """

    measured_value: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=32)
    observation: str | None = Field(default=None, max_length=4000)
    instrument_id: str | None = Field(default=None, max_length=128)
    instrument_verification_status: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=4000)


class VerificationCancelRequest(CamelModel):
    reason: str = Field(min_length=3, max_length=2000)


# ---------------------------------------------------------------- evidence plan


class EvidenceItemOut(CamelModel):
    """One concrete piece of evidence behind a plan row (real or absent)."""

    kind: EvidenceRequirementKind
    status: EvidenceItemStatus
    label: str
    detail: str | None = None


class EvidenceGapOut(CamelModel):
    """One OPEN evidence gap and the verification that closes it."""

    kind: EvidenceRequirementKind
    reason: str
    required: bool
    default_level: VerificationLevel
    task_id: UUID | None = None
    task_status: VerificationTaskStatus | None = None


class MeasurementEvaluationOut(CamelModel):
    """The frozen regulatory evaluation of ONE recorded measurement.

    status EVALUATED → outcome WITHIN_TOLERANCE/EXCEEDS_TOLERANCE under the
    rule code + version recorded here. status UNAVAILABLE → no permissible
    error configured; detail carries the reason and "Inspector review
    required." Historical rows keep the rule version they were evaluated
    under — later rule updates never rewrite them.
    """

    id: UUID
    status: str
    outcome: str | None = None
    rule_code: str | None = None
    rule_version_id: UUID | None = None
    provenance: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    evaluated_at: datetime


class PlanVerificationRefOut(CamelModel):
    """The verification task attached to a plan row (its live state)."""

    id: UUID
    task_type: VerificationTaskType
    status: VerificationTaskStatus
    requirement_level: VerificationLevel
    reason: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    observed: dict[str, Any] | None = None
    evaluation: MeasurementEvaluationOut | None = None
    latest_result: VerificationResultOut | None = None


class EvidencePlanItemOut(CamelModel):
    """One row of the Evidence Planner — a finding or a bare declaration."""

    finding_id: UUID | None = None
    field_id: UUID | None = None
    title: str
    declared_value: str | None = None
    unit: str | None = None
    confidence: float | None = None
    requirement_code: str | None = None
    requirement_title: str | None = None
    rule_code: str | None = None
    version_label: str | None = None
    finding_status: EngineFindingStatus | None = None
    severity: FindingSeverity | None = None
    applicability: ApplicabilityOutcome | None = None
    review_state: FindingReviewState | None = None
    evidence: list[EvidenceItemOut] = []
    gaps: list[EvidenceGapOut] = []
    status: EvidenceItemStatus
    summary: str
    verification: PlanVerificationRefOut | None = None


class EvidencePlanCountsOut(CamelModel):
    total: int = 0
    available: int = 0
    requiring_verification: int = 0
    verified: int = 0
    rejected: int = 0
    not_applicable: int = 0
    open_required_tasks: int = 0


class EvidencePlanOut(CamelModel):
    inspection_id: UUID
    items: list[EvidencePlanItemOut] = []
    counts: EvidencePlanCountsOut
    boundary_note: str = VERIFICATION_BOUNDARY_NOTE
    payload: dict[str, Any] = {}


# --------------------------------------------------------- measurement history




class MeasurementAnchorOut(CamelModel):
    kind: str
    finding_id: UUID | None = None
    extracted_field_id: UUID | None = None
    lot_package_id: UUID | None = None


class MeasurementHistoryRowOut(CamelModel):
    """One recorded measurement — append-only, never editable.

    A correction is a NEW row (a new task result) plus an audit event; the
    original row always remains exactly as recorded.
    """

    measurement_id: UUID
    task_id: UUID
    task_status: VerificationTaskStatus
    anchor: MeasurementAnchorOut
    declared_value: str | None = None
    measured_value: float | None = None
    unit: str | None = None
    observed: dict[str, Any] | None = None
    instrument_id: str | None = None
    instrument_verification_status: str | None = None
    recorded_by: UUID
    recorded_by_name: str | None = None
    recorded_at: datetime
    observation: str | None = None
    notes: str | None = None
    evaluation: MeasurementEvaluationOut | None = None


class MeasurementHistoryOut(CamelModel):
    inspection_id: UUID
    measurements: list[MeasurementHistoryRowOut] = []
    boundary_note: str = (
        "Measurement history is append-only: rows are never edited or "
        "deleted. A correction is a new recorded measurement plus an audit "
        "event. An absent instrument verification status means 'not "
        "recorded' — never 'verified'."
    )
