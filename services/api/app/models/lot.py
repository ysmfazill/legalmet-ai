"""Lot intelligence models (UI-07).

A LOT is the unit of physical verification when an inspector must work with
multiple packages systematically instead of one scanned package:

    Lot            the lot context of one inspection
      → LotPackage one package record belonging to the lot
      → SamplingRun one audited, reproducible draw of a sample from the lot

Physical measurements of lot packages are NOT stored here — they reuse the
UI-06 verification machinery (``VerificationTask`` anchored to a
``LotPackage`` + append-only ``VerificationResult``), so validation, RBAC,
audit and append-only semantics exist exactly once.

LEGAL SAFETY: nothing in this module decides anything. Lot statistics are
OBSERVED values computed from recorded measurements; the lot status only
changes through an explicit inspector decision that the service gates on
complete required evidence.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    LotPackageStatus,
    LotStatus,
    MeasurementEvaluationStatus,
    MeasurementOutcome,
    RegulatoryProcedureKind,
    SamplingMethod,
)
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Lot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One lot under physical verification within an inspection."""

    __tablename__ = "lots"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Human-readable lot identifier, e.g. "LOT-0007" (inspector-supplied).
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    # The DECLARED quantity of the lot's packages, exactly as declared (the
    # string is preserved verbatim; e.g. "500 g"). Immutable after creation:
    # it is the reference the measured values are compared against.
    declared_value: Mapped[str] = mapped_column(String(64), nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=LotStatus.IN_PROGRESS.value, index=True, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Lot decision (explicit inspector submission only — never automatic).
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    inspection = relationship("Inspection")
    product = relationship("Product")
    packages = relationship(
        "LotPackage", back_populates="lot", cascade="all, delete-orphan"
    )
    sampling_runs = relationship(
        "SamplingRun", back_populates="lot", cascade="all, delete-orphan"
    )


class LotPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One package record inside a lot.

    ``status`` is derived from the sampling + measurement state and maintained
    by the lot service (NOT_SAMPLED → PENDING when sampled → MEASURED when a
    measurement is recorded).
    """

    __tablename__ = "lot_packages"

    lot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    # Optional link to a real intake Package when one exists for this unit.
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(24), default=LotPackageStatus.NOT_SAMPLED.value, index=True,
        nullable=False,
    )
    sampling_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sampling_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    lot = relationship("Lot", back_populates="packages")
    sampling_run = relationship("SamplingRun", back_populates="packages")


class SamplingRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One audited, reproducible draw of a sample from a lot.

    The selected packages persist as LotPackage rows (status PENDING) — the
    sample is never regenerated on read. ``seed`` + ``randomization`` make the
    draw reproducible for audit.

    HONESTY: when no configured legal sampling procedure exists, the run is
    explicitly labelled ``is_ai_recommended`` — a recommendation, never a
    legal requirement. When a configured procedure drove the size/method,
    ``procedure_code`` references it.
    """

    __tablename__ = "sampling_runs"

    lot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_method: Mapped[str] = mapped_column(
        String(24), default=SamplingMethod.RANDOM.value, nullable=False
    )
    # Configured legal procedure reference (rule code + version label), when
    # one existed; None means the size/method was NOT legally configured.
    procedure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    procedure_version_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_ai_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    randomization: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    lot = relationship("Lot", back_populates="sampling_runs")
    packages = relationship("LotPackage", back_populates="sampling_run")


class MeasurementEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One deterministic declared-vs-measured regulatory evaluation (UI-07).

    Frozen at recording time: the rule code, the regulation version and the
    computed inputs are stored on this row so a later rule update can never
    rewrite what an earlier measurement was evaluated against.

    When no permissible-error procedure is configured for the applicable
    version, ``status`` is UNAVAILABLE with the reason in ``detail`` — the
    system never guesses a tolerance.
    """

    __tablename__ = "measurement_evaluations"

    verification_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verification_results.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default=MeasurementEvaluationStatus.UNAVAILABLE.value,
        index=True, nullable=False,
    )
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regulation_versions.id", ondelete="SET NULL"), nullable=True
    )
    # Frozen provenance (version label, effective window, source reference).
    provenance: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Inputs + result: declared, measured, normalized values, difference,
    # tolerance applied (or the unavailability reason).
    detail: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    verification_result = relationship("VerificationResult")
    rule_version = relationship("RegulationVersion")


class RegulatoryProcedure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned regulatory procedure that governs physical verification.

    Distinct from ``ComplianceRule`` (which checks DECLARED data): procedures
    here govern PHYSICAL work — the permissible error applied to a
    declared-vs-measured difference, and the legal sampling method for lots.
    Bound to a RegulationVersion so historical evaluations keep the procedure
    they were evaluated under.

    The configuration is free-form JSON consumed deterministically by the
    measurement evaluator / sampling service — e.g.
    ``{"permissibleError": {"type": "PERCENT", "value": "4.5"}}`` or
    ``{"sampleSize": 80, "method": "RANDOM"}``. Nothing is invented at
    evaluation time: a missing or malformed configuration is surfaced as
    UNAVAILABLE, never defaulted.
    """

    __tablename__ = "regulatory_procedures"

    regulation_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regulation_versions.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    regulation_version = relationship("RegulationVersion")
