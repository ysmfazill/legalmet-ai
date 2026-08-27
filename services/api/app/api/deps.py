"""FastAPI dependencies: authentication, RBAC, pagination, service injection.

These are the only place request-scoped auth/authorization is enforced, so
routers stay thin. Services are injected from the registry (the DI seam), which
keeps handlers decoupled from concrete implementations.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import UserRole
from app.core.errors import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.registry import Services, get_services

_bearer = HTTPBearer(auto_error=False)


def get_settings_dep() -> Settings:
    return get_settings()


def get_services_dep() -> Services:
    return get_services()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication required.")
    payload = decode_access_token(credentials.credentials, settings)
    subject = payload.get("sub")
    user: User | None = None
    if subject:
        try:
            user = db.get(User, uuid.UUID(str(subject)))
        except ValueError as exc:
            raise AuthError("Invalid token subject.") from exc
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive.")
    return user


def require_role(*roles: UserRole):
    """Dependency factory enforcing that the current user holds one of ``roles``."""
    allowed = {r.value for r in roles}

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise ForbiddenError("You do not have permission to perform this action.")
        return user

    return _checker


@dataclass
class Pagination:
    page: int
    page_size: int

    @property
    def limit(self) -> int:
        return self.page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)
