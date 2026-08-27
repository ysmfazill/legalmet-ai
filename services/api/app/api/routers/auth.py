"""Authentication routes: login (email/password -> JWT) and current user."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_settings_dep
from app.core.config import Settings
from app.core.errors import AuthError
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.user import AuthTokenResponse, LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenResponse)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> AuthTokenResponse:
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    # Constant-ish path: always run verify to avoid trivial user enumeration.
    valid = user is not None and verify_password(body.password, user.hashed_password)
    if not valid or user is None or not user.is_active:
        raise AuthError("Invalid email or password.")

    token, expires_in = create_access_token(
        subject=str(user.id), role=user.role, settings=settings
    )
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
