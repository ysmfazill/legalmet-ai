"""Inspection lifecycle root + packages.

An inspection is the unit of work. It contains one or more packages; each
package carries the images that are analysed. This is the top of the Evidence
Graph:  inspection -> package -> image -> region -> field -> evidence -> finding.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import InspectionStatus, PackageStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Inspection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inspections"

    reference_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=InspectionStatus.CREATED.value, nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batch_inspections.id", ondelete="SET NULL"), index=True, nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Context date used for version-aware rule selection (defaults to created_at).
    context_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product = relationship("Product")
    inspector = relationship("User")
    batch = relationship("BatchInspection", back_populates="inspections")
    packages = relationship(
        "Package", back_populates="inspection", cascade="all, delete-orphan"
    )
    findings = relationship(
        "ComplianceFinding", back_populates="inspection", cascade="all, delete-orphan"
    )


class Package(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "packages"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=PackageStatus.CREATED.value, nullable=False
    )

    inspection = relationship("Inspection", back_populates="packages")
    product = relationship("Product")
    images = relationship("Image", back_populates="package", cascade="all, delete-orphan")
