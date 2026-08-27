"""Inspector review actions (human-in-the-loop).

Every human decision is recorded as an immutable action row and appended to the
audit trail. Corrections captured here are structured so future model
improvement can learn from them.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class ReviewAction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "review_actions"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_findings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    # Present when action == CORRECT: the status the inspector asserts instead.
    corrected_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    finding = relationship("ComplianceFinding", back_populates="review_actions")
    reviewer = relationship("User")
