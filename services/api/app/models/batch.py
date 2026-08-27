"""Batch inspections — the container for batch/analytics intelligence."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BatchStatus
from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class BatchInspection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "batch_inspections"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=BatchStatus.OPEN.value, nullable=False, index=True
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Cached aggregate stats (recomputed by the analytics service).
    stats: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    inspections = relationship("Inspection", back_populates="batch")
