"""Lot intelligence schemas (UI-07).

LOT → PACKAGES → SAMPLE → MEASUREMENTS → REGULATORY EVALUATION → LOT RESULT.

Every read model carries the two honesty contracts of this layer:

* statistics are OBSERVED values computed from recorded measurements —
  never legal compliance results;
* a sampling run either references a CONFIGURED legal procedure (code +
  version) or is explicitly labelled AI-recommended with inspector
  confirmation — the system never claims a legally required sample it
  cannot cite.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import (
    LotPackageStatus,
    LotStatus,
    SamplingMethod,
    VerificationTaskStatus,
)
from app.schemas.base import CamelModel
from app.schemas.verification import MeasurementEvaluationOut

LOT_BOUNDARY_NOTE = (
    "Lot statistics are OBSERVED values computed from recorded measurements "
    "— they are not legal compliance results. The lot status changes only "
    "through an explicit inspector decision, gated on complete required "
    "evidence."
)


# ------------------------------------------------------------------ read out


class LotProgressOut(CamelModel):
    packages_total: int
    sampled: int
    measured: int
    remaining: int
    summary: str
    action: str | None = None


class LotSummaryOut(CamelModel):
    id: UUID
    label: str
    product_id: UUID | None = None
    declared_value: str
    lot_size: int
    location: str | None = None
    status: LotStatus
    decision: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    progress: LotProgressOut


class LotListOut(CamelModel):
    inspection_id: UUID
    lots: list[LotSummaryOut] = []
    boundary_note: str = LOT_BOUNDARY_NOTE


class LotPackageMeasurementOut(CamelModel):
    task_id: UUID
    task_status: VerificationTaskStatus
    latest_result: dict[str, Any] | None = None
    observed: dict[str, Any] | None = None
    evaluation: MeasurementEvaluationOut | None = None


class LotPackageOut(CamelModel):
    id: UUID
    label: str
    package_id: UUID | None = None
    position: int
    status: LotPackageStatus
    sampling_run_id: UUID | None = None
    measurement: LotPackageMeasurementOut | None = None


class SamplingRunOut(CamelModel):
    id: UUID
    sample_size: int
    selection_method: SamplingMethod
    procedure_code: str | None = None
    procedure_version_label: str | None = None
    is_ai_recommended: bool
    seed: str | None = None
    randomization: dict[str, Any] = {}
    created_by: UUID
    created_at: datetime


class SamplingProcedureOut(CamelModel):
    """The configured legal sampling procedure for the applicable version.

    None fields mean "not configured" — in which case any generated sample is
    AI-recommended and requires inspector confirmation, and the UI shows
    "Sampling procedure requires inspector confirmation."
    """

    code: str
    title: str
    sample_size: int | None = None
    method: str | None = None
    source_reference: str | None = None
    version_label: str | None = None


class LotStatisticsOut(CamelModel):
    """OBSERVED statistics — computed from measurement rows that exist."""

    sampled: int
    measured: int
    average_measured: str | None = None
    average_note: str | None = None
    observed_deficiencies: int
    exceeding_threshold: int
    evaluated: int
    note: str


class LotDetailOut(CamelModel):
    id: UUID
    inspection_id: UUID
    label: str
    product_id: UUID | None = None
    declared_value: str
    lot_size: int
    location: str | None = None
    notes: str | None = None
    status: LotStatus
    decision: str | None = None
    decision_reason: str | None = None
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    packages: list[LotPackageOut] = []
    sampling_runs: list[SamplingRunOut] = []
    sampling_procedure: SamplingProcedureOut | None = None
    statistics: LotStatisticsOut
    progress: LotProgressOut
    boundary_note: str = LOT_BOUNDARY_NOTE


# ---------------------------------------------------------------- write forms


class LotCreateRequest(CamelModel):
    """POST /inspections/{id}/lots.

    The declared quantity is stored verbatim and is immutable after creation.
    Package records are created positionally (one per lotSize).
    """

    label: str = Field(min_length=1, max_length=64)
    declared_value: str = Field(min_length=1, max_length=64)
    lot_size: int = Field(ge=1, le=10000)
    product_id: UUID | None = None
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)


class SampleGenerateRequest(CamelModel):
    """POST /lots/{id}/sample — draw one audited, reproducible sample.

    When a legal sampling procedure is configured it drives size/method and
    sampleSize is ignored. Otherwise the requested size is used and the run
    is AI-recommended — which requires confirmAiSample=true.
    """

    sample_size: int | None = Field(default=None, ge=1)
    selection_method: SamplingMethod = SamplingMethod.RANDOM
    seed: str | None = Field(default=None, max_length=64)
    confirm_ai_sample: bool = False


class LotDecisionRequest(CamelModel):
    """POST /lots/{id}/decision — the explicit lot result.

    COMPLIANT / NON_COMPLIANT / REQUIRES_REVIEW with a mandatory reason. The
    service blocks the submission while sampled packages still lack
    measurements ("Insufficient evidence").
    """

    decision: LotStatus
    reason: str = Field(min_length=3, max_length=4000)
