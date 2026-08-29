"""Deterministic compliance engine domain models (Prompt 6).

This module connects the two halves of the system:

    Prompt 4 (perception)   →  ExtractedField (what was SEEN on the package)
    Prompt 5 (regulatory)   →  Rule / RegulationVersion (what the LAW requires)

through a deterministic, explainable, version-aware compliance engine:

    ComplianceEvaluation  one engine run over an inspection (never overwritten)
      → EvaluationFinding  one requirement × one field, with explanation +
                          evidence + provenance, per evaluation
    ComplianceRule        the deterministic rule configuration attached to a
                          regulatory requirement (never invented — every rule
                          row must correspond to a Prompt 5 requirement)

LEGAL SAFETY: an evaluation is a SYSTEM-GENERATED DECISION-SUPPORT OUTPUT. It
is not, by itself, a legal enforcement determination. The inspector remains
responsible for the final enforcement decision. No model anywhere in this
module decides legality — every conclusion is produced by deterministic code
whose inputs (detected value, requirement, rule, version) are all recorded.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ApplicabilityOutcome,
    EngineFindingStatus,
    EvaluationStatus,
    FindingSeverity,
)
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One deterministic evaluation run over an inspection.

    Immutable-by-convention: re-evaluating creates a NEW row; historical
    evaluations are never overwritten, so a past inspection's result can always
    be reproduced exactly as it was produced (including the regulatory version
    and engine version used).
    """

    __tablename__ = "compliance_evaluations"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Optional image scope — null means the whole inspection (all packages).
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    # The regulatory version in force at the evaluation context date. Nullable:
    # null when the run failed before version resolution (e.g. no version in
    # force) — the failure code lives in `error`.
    regulatory_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regulation_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(48), default=EvaluationStatus.NOT_EVALUATED.value, index=True,
        nullable=False,
    )
    # Bumped whenever deterministic evaluation behaviour changes. Together with
    # the frozen inputs this makes every finding reproducible.
    engine_version: Mapped[str] = mapped_column(String(48), nullable=False)
    # Date the regulatory text was selected against (inspection context date).
    context_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Transparent COUNTS ONLY — never a percentage, never a "legal confidence".
    summary: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Structured failure: {"code": ComplianceErrorCode, "message": str, ...}.
    # Present only when status == FAILED.
    error: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Who triggered the evaluation (audit trail); the engine itself never acts.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    inspection = relationship("Inspection")
    regulatory_version = relationship("RegulationVersion")
    findings = relationship(
        "EvaluationFinding",
        back_populates="evaluation",
        cascade="all, delete-orphan",
        order_by="EvaluationFinding.created_at",
    )


class ComplianceRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A deterministic rule configuration bound to one regulatory requirement.

    The rule does not CREATE law — it encodes HOW to check one requirement that
    already exists in the Prompt 5 regulatory data. ``requirement_id`` always
    points at a Rule row; rule_code reuses the requirement's citation so the
    rule traces to the same source. Rules are versioned themselves
    (``rule_version``) and can be deactivated without deleting history.
    """

    __tablename__ = "compliance_rules"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # e.g. "LM-PC-2011-6.1(a):PRESENCE" — requirement citation + rule type.
    rule_code: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(48), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Deterministic configuration consumed by the rule-type evaluator, e.g.
    # {"units": ["g", "kg", ...]} for UNIT_MATCH. Free-form but validated by
    # the evaluator — unknown keys are ignored, never guessed from.
    configuration: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Rules are seeded only for real (non-demo) requirements.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    requirement = relationship("Rule")
    findings = relationship("EvaluationFinding", back_populates="rule")


class EvaluationFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One requirement evaluated against one detected field — system-generated.

    This is the Prompt 6 finding (distinct from the Prompt 1 demo
    ``ComplianceFinding`` which serves the demonstration flow). Every finding
    carries:

    * what was detected (``detected_value`` + ``extracted_field_id``),
    * what was expected (``expected_value`` + the requirement/rule references),
    * why the status was reached (``explanation`` — deterministic reasoning),
    * the evidence (field → region → OCR → image chain, never fabricated),
    * the provenance snapshot (``provenance`` — source/document/version frozen
      at evaluation time so later regulatory edits cannot rewrite history).

    NOT_DETECTED findings carry no extracted field (the absence of a detection
    is the finding) and their evidence records what was searched.
    """

    __tablename__ = "evaluation_findings"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_evaluations.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_rules.id", ondelete="SET NULL"), index=True, nullable=True
    )
    extracted_field_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extracted_fields.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Evidence region for the detected value, when a field was detected.
    evidence_region_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_regions.id", ondelete="SET NULL"), nullable=True
    )
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(32), default=EngineFindingStatus.NOT_EVALUATED.value, index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(16), default=FindingSeverity.UNKNOWN.value, nullable=False
    )
    # Deterministic applicability outcome recorded alongside the status so a
    # NOT_APPLICABLE finding always shows WHY it does not apply.
    applicability: Mapped[str] = mapped_column(
        String(16), default=ApplicabilityOutcome.UNKNOWN.value, nullable=False
    )
    # Raw/normalized values as evaluated — never repaired, never invented.
    detected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Deterministic, human-readable reasoning covering the seven explainability
    # questions (what was detected / expected / which requirement / which rule /
    # which version / why this status / what evidence).
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # Frozen provenance at evaluation time: requirement code+title, version
    # label, effective window, document identifier, source name, source
    # verification status, source reference.
    provenance: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Structured evaluation detail (rule outputs, evidence summary, absence
    # reason FIELD_NOT_FOUND vs FIELD_CONFIRMED_ABSENT, error codes…).
    detail: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    evaluation = relationship("ComplianceEvaluation", back_populates="findings")
    requirement = relationship("Rule")
    rule = relationship("ComplianceRule", back_populates="findings")
    extracted_field = relationship("ExtractedField")

    @property
    def inspection_id(self) -> uuid.UUID:
        """The inspection this finding belongs to (via its evaluation)."""
        return self.evaluation.inspection_id
