"""Structured application errors and error codes.

Every failure surfaced to a client is an :class:`AppError` (or is converted into
one by the global handler in ``app.main``). This guarantees a consistent,
structured JSON envelope::

    {"error": {"code": "IMAGE_TOO_LARGE", "message": "...", "details": {...},
               "requestId": "..."}}

Nothing "silently fails": handlers log and return a structured payload.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    # Input / media
    INVALID_IMAGE = "INVALID_IMAGE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # AuthN / AuthZ
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # Resources
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"

    # AI / perception services
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    VISION_UNAVAILABLE = "VISION_UNAVAILABLE"
    AI_SERVICE_UNAVAILABLE = "AI_SERVICE_UNAVAILABLE"
    # A requested language is not supported by the installed/tested OCR
    # configuration — returned instead of silently degrading recognition.
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"

    # Regulatory / rule engine
    NO_APPLICABLE_RULE = "NO_APPLICABLE_RULE"
    RULE_VERSION_CONFLICT = "RULE_VERSION_CONFLICT"
    REGULATORY_DATA_INVALID = "REGULATORY_DATA_INVALID"

    # Infrastructure
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for all application errors."""

    status_code: int = 400
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code.value, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        if request_id is not None:
            error["requestId"] = request_id
        return {"error": error}


# --- Concrete errors -------------------------------------------------------


class NotFoundError(AppError):
    status_code = 404
    code = ErrorCode.NOT_FOUND


class ValidationError(AppError):
    status_code = 422
    code = ErrorCode.VALIDATION_ERROR


class AuthError(AppError):
    status_code = 401
    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(AppError):
    status_code = 403
    code = ErrorCode.FORBIDDEN


class ConflictError(AppError):
    status_code = 409
    code = ErrorCode.CONFLICT


class InvalidImageError(AppError):
    status_code = 400
    code = ErrorCode.INVALID_IMAGE


class ImageTooLargeError(AppError):
    status_code = 413
    code = ErrorCode.IMAGE_TOO_LARGE


class UnsupportedFileError(AppError):
    status_code = 415
    code = ErrorCode.UNSUPPORTED_FILE


class ServiceUnavailableError(AppError):
    """AI/perception dependency unavailable (OCR, vision, LLM, ...)."""

    status_code = 503
    code = ErrorCode.AI_SERVICE_UNAVAILABLE


class NoApplicableRuleError(AppError):
    status_code = 422
    code = ErrorCode.NO_APPLICABLE_RULE


class RuleVersionConflictError(AppError):
    status_code = 409
    code = ErrorCode.RULE_VERSION_CONFLICT


class RegulatoryDataInvalidError(AppError):
    """Structural data-quality failure in regulatory seed/import (Prompt 5).

    Raised loudly — regulatory data is never silently repaired."""

    status_code = 422
    code = ErrorCode.REGULATORY_DATA_INVALID


class DatabaseError(AppError):
    status_code = 500
    code = ErrorCode.DATABASE_ERROR
