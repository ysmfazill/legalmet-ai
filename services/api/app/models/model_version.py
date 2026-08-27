"""Model/service version provenance.

Records which OCR / vision / classifier / rule-engine implementation produced a
given extraction or finding, so every result is attributable and reproducible.
"""
from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"

    service_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Attribute is ``meta`` because ``metadata`` is reserved by SQLAlchemy's
    # declarative base; serialised as ``metadata`` in the API schema.
    meta: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
