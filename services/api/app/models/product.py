"""Products / commodities being inspected."""
from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # Expected declaration profile (list of FieldType values) — a perception
    # hint for the category, NOT a legal requirement.
    declaration_profile: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
