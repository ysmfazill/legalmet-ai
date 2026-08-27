"""Audit + model-version schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import ModelServiceType
from app.schemas.base import CamelModel


class AuditEventOut(CamelModel):
    id: UUID
    inspection_id: UUID | None = None
    entity_type: str
    entity_id: UUID | None = None
    actor_id: UUID | None = None
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class ModelVersionOut(CamelModel):
    id: UUID
    service_type: ModelServiceType
    name: str
    version: str
    provider: str
    is_active: bool
    # ORM attribute is `meta`; exposed as `metadata` in the API.
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="meta")
    created_at: datetime
