"""Compliance findings and their evidence.

Invariant enforced by the services layer: **no finding exists without at least
one evidence row**. Evidence links a finding back to the concrete artifacts it
rests on (image, region, extracted field, rule reference, validation result),
which is what makes every finding answer the inspector's question: "Why?".
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ComplianceStatus, EvidenceType
from app.db.base import Base, CreatedAtMixin, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_findings"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rules.id", ondelete="SET NULL"), nullable=True
    )
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regulation_versions.id", ondelete="SET NULL"), nullable=True
    )
    field_type: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ComplianceStatus.REVIEW_REQUIRED.value, index=True, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    # Human decision overlay (set by the review service; never overwrites the
    # original machine `status`).
    review_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    inspection = relationship("Inspection", back_populates="findings")
    package = relationship("Package")
    rule = relationship("Rule")
    rule_version = relationship("RegulationVersion")
    model_version = relationship("ModelVersion")
    evidence = relationship(
        "Evidence", back_populates="finding", cascade="all, delete-orphan"
    )
    review_actions = relationship(
        "ReviewAction",
        back_populates="finding",
        cascade="all, delete-orphan",
        order_by="ReviewAction.created_at",
    )


class Evidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_findings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(
        String(32), default=EvidenceType.EXTRACTED_FIELD.value, nullable=False
    )
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    image_region_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_regions.id", ondelete="SET NULL"), nullable=True
    )
    extracted_field_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extracted_fields.id", ondelete="SET NULL"), nullable=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rules.id", ondelete="SET NULL"), nullable=True
    )
    # Free-form supporting payload (e.g. validator output, matched value).
    data: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    finding = relationship("ComplianceFinding", back_populates="evidence")
    image = relationship("Image")
    region = relationship("ImageRegion")
    extracted_field = relationship("ExtractedField")
    rule = relationship("Rule")
