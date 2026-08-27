"""Shared / generic schema helpers."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from app.schemas.base import CamelModel

T = TypeVar("T")


class Paginated(CamelModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(CamelModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
