"""Regulatory Knowledge System (structured, version-aware).

This models regulations as data — not as a folder of PDFs — with amendment
relationships and effective-date windows so the system can answer "which rule
version applies to this inspection context?".

Prompt 5 extends the Prompt 1 foundation into a full provenance hierarchy:

    RegulatorySource   (WHO published — authority + verification state)
      → Regulation     (the DOCUMENT — what the instrument is)
        → RegulationVersion (a dated, in-force-or-superseded text)
          → Rule       (one REQUIREMENT within that version)
            → RuleApplicability (structured applicability conditions)

IMPORTANT provenance rule: a requirement is only as authoritative as its
source's VerificationStatus. Rows seeded from real Legal Metrology material
that has not been verified against an official government publication carry
verification_status=UNVERIFIED — they are research-grade data, clearly
distinguishable from both VERIFIED authoritative data and from the fictional
DEMO dataset seeded by Prompt 1.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    DocumentType,
    RegulationVersionStatus,
    RuleStatus,
    SourceType,
    VerificationStatus,
)
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class RegulatorySource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The authoritative origin of regulatory content (top of the chain).

    ``verification_status`` expresses SOURCE confidence — how well the stored
    content is provenanced to an official publication. It is explicitly NOT an
    AI/OCR confidence and never a compliance signal. Only VERIFIED sources are
    eligible for production compliance evaluation (Prompt 6).
    """

    __tablename__ = "regulatory_sources"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(48), default=SourceType.OTHER.value, index=True, nullable=False
    )
    canonical_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    jurisdiction: Mapped[str] = mapped_column(String(120), default="IN", nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(24),
        default=VerificationStatus.UNVERIFIED.value,
        index=True,
        nullable=False,
    )
    # Free-text note recording how/when verification was (not) done. Part of
    # provenance: "where did this content come from?" must always be answerable.
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents = relationship(
        "Regulation", back_populates="source", cascade="all, delete-orphan"
    )


class Regulation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A regulatory DOCUMENT (e.g. one set of rules or an amending notification)."""

    __tablename__ = "regulations"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(120), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Prompt 5: document-level provenance -----------------------------------
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regulatory_sources.id", ondelete="SET NULL"), index=True, nullable=True
    )
    document_identifier: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # e.g. "G.S.R. 202(E)"
    document_type: Mapped[str] = mapped_column(
        String(48), default=DocumentType.OTHER.value, nullable=False
    )
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source = relationship("RegulatorySource", back_populates="documents")
    versions = relationship(
        "RegulationVersion", back_populates="regulation", cascade="all, delete-orphan"
    )


class RegulationVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A dated, supersession-aware VERSION of one document's requirements."""

    __tablename__ = "regulation_versions"

    regulation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regulations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=RegulationVersionStatus.DRAFT.value, index=True, nullable=False
    )
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Self-referential amendment chain: this version amends `amendment_of`.
    amendment_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regulation_versions.id", ondelete="SET NULL"), nullable=True
    )
    source_document_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Prompt 5: version-level provenance --------------------------------------
    # Date the amending instrument was published (distinct from effective_from,
    # the date it came into force).
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    regulation = relationship("Regulation", back_populates="versions")
    amendment_of = relationship("RegulationVersion", remote_side="RegulationVersion.id")
    rules = relationship("Rule", back_populates="version", cascade="all, delete-orphan")


class Rule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One REQUIREMENT belonging to a specific regulatory version."""

    __tablename__ = "rules"

    regulation_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regulation_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    requirement_summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Key resolving to a deterministic validator in the rule-engine registry.
    validation_logic_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=RuleStatus.ACTIVE.value, nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Prompt 5: requirement-level provenance + applicability -----------------
    requirement_type: Mapped[str] = mapped_column(
        String(32), default="DECLARATION", nullable=False
    )
    # Perception field key this requirement is checkable against (FieldType value).
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    expected_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Structured applicability definition (JSON) — see RuleApplicability for rows.
    applicability_definition: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict
    )
    # Citation into the source document, e.g. "Rule 6(1)(c)".
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    version = relationship("RegulationVersion", back_populates="rules")
    applicabilities = relationship(
        "RuleApplicability", back_populates="rule", cascade="all, delete-orphan"
    )


class RuleApplicability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured applicability condition for one requirement.

    Prompt 5 models applicability as DATA — commodity/category, package type,
    quantity band, sale context, jurisdiction — so Prompt 6's engine can
    evaluate applicability deterministically instead of assuming every
    declaration applies to every package.
    """

    __tablename__ = "rule_applicability"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_category: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    # Structured applicability condition. Shape:
    #   {"commodity": [...]|"*", "packageType": [...]|"*",
    #    "saleContext": "RETAIL"|"*", "fieldKey": "...", "params": {...}}
    condition_expression: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    rule = relationship("Rule", back_populates="applicabilities")
