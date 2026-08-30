"""PROMPT 9 Phase 9 — database integrity (integration-marked).

Guards the migration chain and the model/migration contract:

* full upgrade from scratch reaches a schema that matches the ORM models
  exactly (column-level) — catches columns that exist on models but were
  never added to a migration (the drift this test was written for: the dev
  database was built with ``create_all``, which masked two missing columns).
* the chain downgrades all the way back to base cleanly (every migration is
  reversible, not just the latest one).
* FK integrity: every FK relationship in the ORM metadata, materialised from
  a fresh migrated database, has an actual FK constraint in SQLite.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

API_DIR = Path(__file__).resolve().parents[1]


def _db_schema(path: str) -> dict[str, list[str]]:
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        tables = [
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%'"
            ).fetchall()
        ]
        return {
            t: sorted(r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall())
            for t in tables
        }
    finally:
        conn.close()


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory) -> str:
    """A database built purely by ``alembic upgrade head`` (no create_all)."""
    db_path = tmp_path_factory.mktemp("mig") / "drift.db"
    env = {
        **__import__("os").environ,
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return str(db_path)


@pytest.mark.integration
class TestMigrationChainIntegrity:
    def test_upgraded_schema_matches_models_exactly(self, migrated_db):
        """Column-level diff between ORM metadata and the migrated database
        must be EMPTY — otherwise a production DB provisioned via Alembic
        diverges from what the application expects."""
        model_schema = {
            t.name: sorted(c.name for c in t.columns) for t in Base.metadata.sorted_tables
        }
        db_schema = _db_schema(migrated_db)
        missing_tables = sorted(set(model_schema) - set(db_schema))
        extra_tables = sorted(set(db_schema) - set(model_schema))
        assert not missing_tables, f"tables missing from migrations: {missing_tables}"
        assert not extra_tables, f"tables not on the models: {extra_tables}"
        for table in sorted(model_schema):
            assert model_schema[table] == db_schema[table], (
                f"column drift on {table}: "
                f"model-only={sorted(set(model_schema[table]) - set(db_schema[table]))} "
                f"db-only={sorted(set(db_schema[table]) - set(model_schema[table]))}"
            )

    def test_full_chain_downgrades_to_base(self, tmp_path):
        """Every migration is reversible: downgrade base must succeed on a
        database that was upgraded to head."""
        db_path = tmp_path / "down.db"
        env = {
            **__import__("os").environ,
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        }
        up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=API_DIR, env=env, capture_output=True, text=True, timeout=300,
        )
        assert up.returncode == 0, up.stderr[-2000:]
        down = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=API_DIR, env=env, capture_output=True, text=True, timeout=300,
        )
        assert down.returncode == 0, down.stderr[-2000:]
        remaining = _db_schema(str(db_path))
        assert remaining == {}, f"tables survived downgrade: {sorted(remaining)}"

    def test_foreign_keys_materialise_in_sqlite(self, migrated_db):
        """Every relationship declared on the models must exist as a real FK
        constraint in the migrated database (catches silently-dropped FKs)."""
        model_fks: set[tuple[str, str]] = set()
        for table in Base.metadata.sorted_tables:
            for fk in table.foreign_keys:
                model_fks.add((table.name, fk.column.table.name))
        conn = sqlite3.connect(migrated_db)
        try:
            cur = conn.cursor()
            db_fks: set[tuple[str, str]] = set()
            for table in {t for t, _ in model_fks}:
                for row in cur.execute(f"PRAGMA foreign_key_list({table})").fetchall():
                    db_fks.add((table, row[2]))
        finally:
            conn.close()
        missing = model_fks - db_fks
        assert not missing, f"FK constraints missing from migrations: {sorted(missing)}"


@pytest.mark.integration
class TestHistoricalPreservation:
    def test_fk_check_clean_on_migrated_db(self, migrated_db):
        """PRAGMA foreign_key_check reports zero violations on a freshly
        migrated (empty) database — the baseline for the runtime guard."""
        conn = sqlite3.connect(migrated_db)
        try:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            conn.close()
        assert violations == []
