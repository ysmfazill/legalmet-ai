"""Structured logging via structlog.

Logs are emitted as human-readable lines in development and as JSON in
production (``LOG_JSON=true``). A per-request ``request_id`` (and, where
relevant, ``inspection_id`` / ``stage``) is bound into the context so a single
inspection can be traced end-to-end across processing stages.

Sensitive values (passwords, tokens, raw image bytes) are never logged.
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure stdlib logging + structlog processors once at startup."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if settings.log_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "legalmet") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


# Convenience re-exports for binding/unbinding request context.
bind_context = structlog.contextvars.bind_contextvars
unbind_context = structlog.contextvars.unbind_contextvars
clear_context = structlog.contextvars.clear_contextvars
