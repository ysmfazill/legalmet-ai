"""Verification task models (UI-06 — Evidence Planner).

The layer that answers, per finding: "what evidence is still required before
an inspector can make a defensible decision?".

    VerificationTask   one concrete inspector action that closes an evidence
                       gap (a physical measurement, a field observation).
                       Created by an authorised human through the Evidence
                       Planner — NEVER auto-created by the engine.
    VerificationResult one recorded outcome of a task (append-only). For a
                       MEASUREMENT task this is a manual reading from an
                       appropriate Legal Metrology instrument, with instrument
                       metadata. Multiple results may be recorded; nothing is
                       ever overwritten.

LEGAL SAFETY: a recorded measurement is EVIDENCE, not a verdict. Nothing in
this module evaluates declared-vs-measured against a permissible-error rule —
the inspector weighs the recorded evidence and makes the final decision. The
system never converts a numeric difference into a violation.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    VerificationLevel,
    VerificationTaskStatus,
    VerificationTaskType,
)
from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VerificationTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verification_tasks"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Anchor A: the engine finding whose evidence gap this task closes.
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluation_findings.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Anchor B: the extracted declaration (pre-evaluation planner rows).
    extracted_field_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extracted_fields.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Anchor C (UI-07): a lot package — the unit a lot measurement verifies.
    # Lot-anchored tasks gate the LOT decision, not the inspection decision.
    lot_package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lot_packages.id", ondelete="CASCADE"), index=True, nullable=True
    )
    task_type: Mapped[str] = mapped_column(
        String(32), default=VerificationTaskType.MEASUREMENT.value, nullable=False
    )
    # REQUIRED tasks block a final decision while open; RECOMMENDED never do.
    requirement_level: Mapped[str] = mapped_column(
        String(16), default=VerificationLevel.REQUIRED.value, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=VerificationTaskStatus.PENDING.value, index=True, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    inspection = relationship("Inspection")
    finding = relationship("EvaluationFinding")
    extracted_field = relationship("ExtractedField")
    lot_package = relationship("LotPackage")
    created_by_user = relationship("User", foreign_keys=[created_by])
    results = relationship(
        "VerificationResult",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="VerificationResult.created_at",
    )

    @property
    def is_open(self) -> bool:
        return self.status in (
            VerificationTaskStatus.PENDING.value,
            VerificationTaskStatus.IN_PROGRESS.value,
        )

    @property
    def latest_result(self) -> "VerificationResult | None":
        return self.results[-1] if self.results else None


class VerificationResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One recorded verification outcome — append-only, never edited.

    For MEASUREMENT tasks: ``measured_value`` + ``unit`` are mandatory and the
    DECLARED value lives on the extracted field — the two are never merged.
    ``instrument_verification_status`` is recorded only when the inspector
    supplies it; absent means "not recorded", never "verified".
    """

    __tablename__ = "verification_results"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verification_tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measured_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    instrument_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    instrument_verification_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    task = relationship("VerificationTask", back_populates="results")
    recorded_by_user = relationship("User", foreign_keys=[recorded_by])
