"""Schema bootstrap helpers.

For dev/test we materialise the schema directly from the ORM models via
``create_all`` (zero-config, works on SQLite). For production, Alembic
migrations are the source of truth — see ``alembic/`` and docs/architecture.md.
"""
from __future__ import annotations

from sqlalchemy.engine import Engine

# Importing the models package registers every table on ``Base.metadata``.
import app.models  # noqa: F401
from app.db.base import Base


def create_all(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def drop_all(engine: Engine) -> None:
    Base.metadata.drop_all(bind=engine)
