"""Citizen Mode data model (UI-02, extended in UI-03).

Consumers scan a package without an account. Two tables:

``CitizenScan``  — one anonymous scan: stored image, REAL usability grade from
the Pillow analyzer, real OCR + deterministic declaration extraction results,
and a screening outcome. The outcome is an *automated screening* statement
only — never a Legal Metrology determination. Every scan keeps its evidence
so a later official review can trace what the system actually saw.

``CitizenReport`` — a citizen-submitted suspected issue referencing a scan.
In UI-03 this entity IS the complaint: a controlled status state machine
(SUBMITTED → … → CLOSED) advanced only by department users, a persistent
event history (``CitizenReportEvent``) the timeline reads, a deterministic
system-screening risk, and an optional linked inspection created by a
department decision (never automatically).

Honesty by construction:

* ``screening_risk`` is computed from the scan's real extraction evidence by
  a deterministic rule — it is a SYSTEM SCREENING signal, clearly distinct
  from ``official_priority``, which only a department decision may set.
* No status implies a legal violation. ACCEPTED means "accepted for further
  review"; the official determination lives in the inspection workflow.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONType, Base, CreatedAtMixin, UUIDPrimaryKeyMixin, utcnow


class CitizenScan(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "citizen_scans"

    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    processed_storage_key: Mapped[str | None] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # REAL usability grading (resolution/sharpness/contrast/exposure) — a
    # readability signal, never a compliance judgement.
    quality_grade: Mapped[str | None] = mapped_column(String(16))
    quality_score: Mapped[float | None] = mapped_column()
    quality_status: Mapped[str | None] = mapped_column(String(16))
    quality_metrics: Mapped[dict | None] = mapped_column(JSONType)
    # Screening outcome vocabulary (UI-02): NO_OBVIOUS_ISSUE, POSSIBLE_ISSUE,
    # REVIEW_REQUIRED, INSUFFICIENT_EVIDENCE, plus IMAGE_UNREADABLE.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome_rationale: Mapped[str | None] = mapped_column(Text)
    # Deterministic extraction evidence kept verbatim for official review.
    detected_fields: Mapped[list | None] = mapped_column(JSONType)
    ocr_text: Mapped[list | None] = mapped_column(JSONType)
    ocr_provider: Mapped[str | None] = mapped_column(String(64))
    ocr_model: Mapped[str | None] = mapped_column(String(64))
    # True when this scan was served by the real backend pipeline.
    is_live: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CitizenReport(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "citizen_reports"

    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citizen_scans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Controlled complaint lifecycle (UI-03 state machine, advanced only by
    # the service layer — never by arbitrary string writes).
    status: Mapped[str] = mapped_column(String(32), default="SUBMITTED", nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    shop: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    issue: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text)
    reporter_name: Mapped[str | None] = mapped_column(String(128))
    reporter_contact: Mapped[str | None] = mapped_column(String(128))
    # Snapshot of the scan evidence at submit time (fields, image refs).
    evidence: Mapped[dict | None] = mapped_column(JSONType)

    # --- UI-03 complaint workflow columns ---------------------------------
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    # Deterministic SYSTEM SCREENING priority computed from the scan's real
    # extraction evidence at submit time (LOW/MEDIUM/HIGH). Never an AI score,
    # never an official decision.
    screening_risk: Mapped[str | None] = mapped_column(String(16))
    # OFFICIAL priority — only a department transition may set it.
    official_priority: Mapped[str | None] = mapped_column(String(16))
    # The department's current pending request to the citizen (set on
    # REQUEST_INFORMATION, cleared when the citizen responds).
    pending_info_request: Mapped[str | None] = mapped_column(Text)
    assigned_inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # The inspection created FROM this complaint by a department decision.
    # The complaint is never auto-inspected; the link is explicit.
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inspections.id", ondelete="SET NULL"), index=True, nullable=True
    )
    is_live: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    scan = relationship("CitizenScan")
    inspector = relationship("User", foreign_keys=[assigned_inspector_id])
    inspection = relationship("Inspection", foreign_keys=[inspection_id])
    events = relationship(
        "CitizenReportEvent",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="CitizenReportEvent.created_at",
    )


class CitizenReportEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One immutable complaint-history entry — what the timeline displays.

    Only real recorded transitions land here; the UI renders pending future
    steps from the state machine, never fabricated events.
    """

    __tablename__ = "citizen_report_events"

    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("citizen_reports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Event kind: SUBMITTED, REVIEW_STARTED, REJECTED, INFORMATION_REQUESTED,
    # INFORMATION_PROVIDED, ACCEPTED, ASSIGNED, INSPECTION_CREATED,
    # INSPECTION_COMPLETED, ACTION_TAKEN, CLOSED.
    event: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Who acted: CITIZEN (anonymous) or DEPARTMENT (actor_id recorded).
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text)

    report = relationship("CitizenReport", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])
