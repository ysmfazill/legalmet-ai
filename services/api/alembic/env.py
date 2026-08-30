"""Alembic migration environment for METRASIGHT.

Design notes:

* The database URL comes from application settings (an environment variable),
  never from ``alembic.ini`` — secrets stay out of source control and
  migrations always target the configured database.
* ``target_metadata`` is the ORM ``Base.metadata``. Importing ``app.models``
  registers every table, so ``--autogenerate`` sees the full schema.
* ``render_as_batch=True`` enables SQLite-safe "batch" ALTERs, so the same
  migrations apply on the zero-config SQLite dev database and on PostgreSQL.
"""
from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.db.base import Base

config = context.config

# Inject the runtime database URL from settings (env-driven).
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_sqlite() -> bool:
    return _settings.database_url.startswith("sqlite")


def _render_item(type_, obj, autogen_context) -> str | bool:
    """Render our portable ``JSONType`` columns with fully-qualified names.

    Alembic's default autogenerate renders the JSONB variant's ``astext_type``
    as a bare ``Text()`` without importing it, which breaks the migration. We
    emit the full, qualified variant so the same migration keeps ``JSONB`` on
    PostgreSQL and plain ``JSON`` elsewhere, with no missing imports.
    """
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    if type_ == "type" and isinstance(obj, (sa.JSON, JSONB)):
        autogen_context.imports.add("import sqlalchemy as sa")
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return (
            "sa.JSON().with_variant("
            "postgresql.JSONB(astext_type=sa.Text()), 'postgresql')"
        )
    return False


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection."""
    context.configure(
        url=_settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=_render_item,
        render_as_batch=_is_sqlite(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_item=_render_item,
            render_as_batch=_is_sqlite(),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
