"""Product schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.enums import FieldType
from app.schemas.base import CamelModel


class ProductOut(CamelModel):
    id: UUID
    name: str
    category: str
    gtin: str | None = None
    declaration_profile: list[FieldType] | None = None
    is_demo: bool
    created_at: datetime
