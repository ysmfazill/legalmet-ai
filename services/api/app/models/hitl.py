"""Human-in-the-loop review models (Prompt 8).

Three append-only tables record everything a human does on top of the frozen
system outputs:

    FieldCorrection       one inspector correction of one extracted field
                          (the ORIGINAL OCR/AI values are never touched —
                          they stay on ExtractedField verbatim)
    FindingReview         the human review state of ONE engine finding,
                          with its full transition history in
                          FindingReviewEvent (the state machine is enforced
                          in the service layer, never in the frontend)
    InspectionDecision    the FINAL human decision on an inspection — the
                          only place a legal conclusion exists. New decision
                          rows supersede (never overwrite) earlier ones.

AI ASSISTS. THE INSPECTOR DECIDES. No row in this module is created by the
deterministic engine or by any model — every row carries the acting human's
identity, role and (where required) reason.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import FindingReviewState, InspectionDecisionType
from app.db.base import Base, CreatedAtMixin, JSONType, UUIDPrimaryKeyMixin


class FieldCorrection(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One human correction of one extracted field — append-only history.

    The ORIGINAL AI output is preserved untouched on ExtractedField
    (raw_text / normalized_value / confidence / status); this row records the
    corrected value, who corrected it, when, and why. Each new correction is a
    NEW row — corrections are never updated or deleted — so the full
    before/after chain of an inspector's edits is always reproducible.

    ExtractedField.corrected_value / corrected_at are maintained as a
    convenience pointer to the LATEST correction only (see HitlService);
    corrected_by is resolved through that latest row.
    """

    __tablename__ = "field_corrections"

    extracted_field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_fields.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    # Which inspection this correction belongs to (denormalised from the
    # field's package for efficient audit/evidence-graph traversal).
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The acting human (never the engine, never a model).
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # BEFORE values — frozen copies of the field's AI output at correction
    # time (the originals also remain on ExtractedField, never overwritten).
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AFTER value.
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False)
    # Mandatory reason — an unexplained correction is never accepted.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # The evaluation whose finding triggered this correction, when the
    # correction came from the review workflow (null for direct workspace
    # corrections).
    triggered_by_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_evaluations.id", ondelete="SET NULL"), nullable=True
    )

    extracted_field = relationship("ExtractedField")
    corrected_by_user = relationship("User", foreign_keys=[corrected_by])


class FindingReview(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Human review state of ONE engine finding.

    Exactly one row per engine finding (unique constraint). The engine finding
    is a frozen system output; this row + its FindingReviewEvent history record
    the human verdict. The ``state`` column only ever changes through the
    backend-enforced state machine (see HitlService) — arbitrary transitions
    are rejected with 409 CONFLICT.
    """

    __tablename__ = "finding_reviews"
    __table_args__ = (
        UniqueConstraint("finding_id", name="uq_finding_reviews_finding_id"),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_findings.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    # Denormalised inspection for queue/graph traversal.
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(32), default=FindingReviewState.PENDING_REVIEW.value, index=True,
        nullable=False,
    )
    # The human who last acted on this review.
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last recorded reason (full history in FindingReviewEvent).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Link to the correction created for a CORRECTED review, if any.
    correction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("field_corrections.id", ondelete="SET NULL"), nullable=True
    )
    # Supervisor context for OVERRIDDEN / SUPERVISOR_REVIEWED events.
    escalated_to_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    finding = relationship(
        "EvaluationFinding", back_populates="review", uselist=False
    )
    reviewed_by_user = relationship("User", foreign_keys=[reviewed_by])
    events = relationship(
        "FindingReviewEvent",
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="FindingReviewEvent.created_at",
    )

    @property
    def evaluation_id(self) -> uuid.UUID | None:
        return self.finding.evaluation_id if self.finding else None


class FindingReviewEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One transition in a finding review's history — append-only.

    Every state change is recorded with its actor, role, previous state, new
    state and reason. The history is never rewritten.
    """

    __tablename__ = "finding_review_events"

    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("finding_reviews.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    review = relationship("FindingReview", back_populates="events")


class InspectionDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The FINAL human decision on one inspection — immutable history.

    A new decision never overwrites an old one: superseding happens by writing
    a NEW row whose ``supersedes_decision_id`` points at the row it replaces.
    The latest row (by created_at) is the current decision; the full chain
    preserves who decided what, when, why, and what changed.

    Only an authorised human (INSPECTOR/SUPERVISOR) may create these rows.
    The deterministic engine and every model are structurally excluded — there
    is no code path from the engine to this table.
    """

    __tablename__ = "inspection_decisions"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(
        String(48), default=InspectionDecisionType.NOT_EVALUATED.value, index=True,
        nullable=False,
    )
    # The acting human — never the engine.
    decided_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Mandatory for NON_COMPLIANT (and for superseding a prior decision).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The evaluation the decision is based on (frozen reference).
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_evaluations.id", ondelete="SET NULL"), nullable=True
    )
    # Decision chain: previous row this one supersedes (never a delete).
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inspection_decisions.id", ondelete="SET NULL"), nullable=True
    )
    # Structured context: counts of confirmed/rejected/overridden findings at
    # decision time, note, etc.
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    inspection = relationship("Inspection")
    decided_by_user = relationship("User", foreign_keys=[decided_by])
