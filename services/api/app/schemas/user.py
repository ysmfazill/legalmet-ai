"""User + auth schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.core.enums import UserRole
from app.schemas.base import CamelModel


class UserOut(CamelModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginRequest(CamelModel):
    email: str
    password: str = Field(min_length=1)


class AuthTokenResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# EmailStr is imported to document intent; kept optional to avoid a hard
# dependency on email-validator during the foundation phase.
__all__ = ["UserOut", "LoginRequest", "AuthTokenResponse", "EmailStr"]
