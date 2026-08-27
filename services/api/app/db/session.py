"""Database engine + session management.

The module-level ``engine`` / ``SessionLocal`` are used by the running app.
Tests build their own engine and override the ``get_db`` FastAPI dependency, so
nothing here couples the app to a specific database instance.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def make_engine(settings: Settings) -> Engine:
    connect_args: dict = {}
    if settings.is_sqlite:
        # Allow use across FastAPI's threadpool.
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


_settings = get_settings()
engine: Engine = make_engine(_settings)
SessionLocal: sessionmaker[Session] = make_session_factory(engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
