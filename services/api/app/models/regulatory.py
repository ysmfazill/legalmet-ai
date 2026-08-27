"""Regulatory Knowledge System (structured, version-aware).

This models regulations as data — not as a folder of PDFs — with amendment
relationships and effective-date windows so the system can answer "which rule
version applies to this inspection context?".

IMPORTANT: No verified Legal Metrology requirements are encoded here. Rows are
populated from clearly-labelled DEMO placeholders during the foundation phase
and will be replaced with verified data from official sources later.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RegulationVersionStatus, RuleStatus
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Regulation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "regulations"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(120), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    versions = relationship(
        "RegulationVersion", back_populates="regulation", cascade="all, delete-orphan"
    )


class RegulationVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
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

    regulation = relationship("Regulation", back_populates="versions")
    amendment_of = relationship("RegulationVersion", remote_side="RegulationVersion.id")
    rules = relationship("Rule", back_populates="version", cascade="all, delete-orphan")


class Rule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
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

    version = relationship("RegulationVersion", back_populates="rules")
    applicabilities = relationship(
        "RuleApplicability", back_populates="rule", cascade="all, delete-orphan"
    )


class RuleApplicability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rule_applicability"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_category: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    # Structured applicability condition (e.g. {"field": "net_quantity", "op": ...}).
    condition_expression: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    rule = relationship("Rule", back_populates="applicabilities")
