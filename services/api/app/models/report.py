"""Report & evidence pack data model (UI-08).

A report is a *versioned, decision-support snapshot* of one inspection —
never the authority. The final legal authority remains the authorized Legal
Metrology inspector whose decision is recorded in the inspection workflow.

Three tables, all append-only in spirit:

``Report``       — one live report record per inspection (the pointer to the
                   current version). The lifecycle is
                   DRAFT → UNDER_REVIEW → FINALIZED → EXPORTED, with AMENDED
                   reachable when a finalized report's findings change and a
                   new version is created (the previous version is preserved
                   verbatim — never silently overwritten).
``ReportVersion`` — one immutable snapshot per generation. The snapshot JSON
                   freezes everything the report asserts (summary, findings,
                   regulatory basis, measurements, lots, decision, evidence
                   references) at generation time, so a later data change can
                   never rewrite what an exported report claimed.
``ReportEvidence`` — the ordered evidence manifest of one version: stable
                   per-item identifiers (E-001, E-002, …) referencing EXISTING
                   records (images, regions, fields, measurements, lots) by id.
                   Nothing is copied — provenance is preserved by reference.

Honesty by construction:

* the report result is the inspector's recorded decision, or
  NOT_EVALUATED while none exists — the report never invents a result;
* ``finalized_at``/``finalized_by`` are only ever set by the gated
  finalization path (missing required evidence blocks it);
* every lifecycle transition writes an append-only audit event.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONType, Base, CreatedAtMixin, UUIDPrimaryKeyMixin, utcnow


class Report(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reports"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # The current version pointer (mirrors max(ReportVersion.version)).
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False, index=True)
    # The inspector's recorded decision frozen into the current version, or
    # NOT_EVALUATED while no decision exists. Never a report-side invention.
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_EVALUATED")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Mandatory whenever a new version supersedes a FINALIZED one.
    amendment_reason: Mapped[Text | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    inspection = relationship("Inspection")
    versions = relationship(
        "ReportVersion",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportVersion.version",
    )


class ReportVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One immutable generation snapshot — the source of every export."""

    __tablename__ = "report_versions"

    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Frozen full snapshot JSON (camelCase keys, ready for serialization).
    snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)
    # Why this version exists (amendment reason, or "initial generation").
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    report = relationship("Report", back_populates="versions")
    evidence_items = relationship(
        "ReportEvidence",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="ReportEvidence.sequence",
    )


class ReportEvidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One evidence-manifest entry of one version, by REFERENCE.

    ``evidence_type`` ∈ {IMAGE, IMAGE_REGION, EXTRACTED_FIELD, MEASUREMENT,
    LOT, COMPLAINT, FINDING}. The referenced record id is preserved verbatim;
    ``sequence`` yields the stable E-00N identifier shown in the UI/exports.
    """

    __tablename__ = "report_evidence"

    report_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    # Caption provenance: image filename, field label, lot label… (read at
    # generation time and frozen; never user-controlled HTML).
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail: Mapped[dict | None] = mapped_column(JSONType)

    version = relationship("ReportVersion", back_populates="evidence_items")
