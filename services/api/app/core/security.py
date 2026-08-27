"""Password hashing (bcrypt) and JWT access tokens (PyJWT).

Kept dependency-light and provider-agnostic: hashing and token signing are
plain functions so they can be swapped later (e.g. Argon2, an external identity
provider) without touching call sites.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings
from app.core.errors import AuthError

# bcrypt hard limit: only the first 72 bytes are significant.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    subject: str,
    role: str,
    settings: Settings,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)``.

    ``subject`` is the user id. ``role`` is embedded for coarse authorization.
    """
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expire_minutes * 60


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid access token.") from exc
