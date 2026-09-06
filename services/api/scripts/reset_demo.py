"""SAFE DEMO RESET — deterministic, idempotent demo-data reset.

Wipes all transactional/demo ACTIVITY while preserving everything the system
needs to run:

  PRESERVED (configuration / reference data)
    - users (demo login accounts)
    - regulatory sources, regulations, versions, rules, applicability
    - regulatory procedures (measurement-tolerance configuration)
    - deterministic compliance rules
    - model versions (engine registry)

  REMOVED (transactional / activity data)
    - inspections, packages, images (+ stored files), processing runs,
      OCR results, image regions, extracted fields
    - evaluations, findings (engine + legacy), evidence rows
    - field corrections, finding reviews + events, decisions
    - verification tasks / results / measurement evaluations
    - lots, lot packages, sampling runs, batch links
    - reports, report versions, report evidence
    - citizen scans / reports / events (+ stored files)
    - audit events
    - products (created per-inspection by the demo build)

Then re-seeds the intentional demo dataset through the REAL services (real
intake, REAL local OCR, real deterministic evaluation, real review + decision)
— by default ONE inspection, ``DEMO-FOOD`` (see ``SEED_DEMO_INSPECTION_REFS``).

Idempotent: running it twice leaves the same state (the seed skips references
that already exist). It never touches schema/migrations and never deletes
configuration rows.

Usage (backend stopped or running — SQLite tolerates both, but stopped is
cleanest because stored image files are also removed):

    cd services/api
    python -m scripts.reset_demo
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402

logger = get_logger("legalmet.reset_demo")

# Transactional tables, children before parents (FK-safe delete order).
# Configuration tables are deliberately absent — see the module docstring.
_TRANSACTIONAL_TABLES = [
    # reporting
    "report_evidence",
    "report_versions",
    "reports",
    # human-in-the-loop history
    "finding_review_events",
    "finding_reviews",
    "inspection_decisions",
    "field_corrections",
    # compliance results
    "evaluation_findings",
    "compliance_evaluations",
    "compliance_findings",  # legacy demo flow
    "evidence",  # legacy evidence rows
    # perception
    "extracted_fields",
    "ocr_text_results",
    "image_regions",
    "processing_runs",
    # physical verification + lots
    "measurement_evaluations",
    "verification_results",
    "verification_tasks",
    "sampling_runs",
    "lot_packages",
    "lots",
    "batch_inspections",
    "review_actions",
    # citizen activity
    "citizen_report_events",
    "citizen_reports",
    "citizen_scans",
    # intake
    "images",
    "packages",
    "inspections",
    "products",
    # audit trail of the removed activity
    "audit_events",
]

# Tables that must SURVIVE the reset — verified after the wipe as a guard
# against future edits to the delete list.
_PRESERVED_TABLES = [
    "users",
    "regulatory_sources",
    "regulations",
    "regulation_versions",
    "rules",
    "rule_applicability",
    "regulatory_procedures",
    "compliance_rules",
    "model_versions",
]


def _table_names(db) -> set[str]:
    rows = db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    ).fetchall()
    return {r[0] for r in rows}


def _wipe_storage(storage_dir: Path, removed: dict[str, int]) -> None:
    """Remove every stored file (inspection + citizen images). The storage
    layout is content-addressed under storage_dir; nothing preserved
    references it."""
    if storage_dir.is_dir():
        for child in storage_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        removed["_storage_files_removed"] = -1  # marker; directory itself kept


def _wipe_transactional(db: Session) -> dict[str, int]:
    """Delete every transactional table's rows, children before parents."""
    removed: dict[str, int] = {}
    with db.begin():
        tables = _table_names(db)  # inside the tx — querying auto-begins one
        overlap = set(_TRANSACTIONAL_TABLES) & set(_PRESERVED_TABLES)
        if overlap:  # pragma: no cover — guard against future edit mistakes
            raise RuntimeError(
                f"Reset list bug — tables both removed and preserved: {overlap}"
            )

        for table in _TRANSACTIONAL_TABLES:
            if table not in tables:
                continue
            result = db.execute(text(f"DELETE FROM {table}"))
            removed[table] = result.rowcount if result.rowcount is not None else 0
    return removed


def reset_demo_data(
    session_factory=None, settings: Settings | None = None
) -> dict[str, int]:
    """Wipe transactional data + stored files, then seed the demo dataset.

    ``session_factory`` / ``settings`` are injectable for the test suite; the
    CLI path uses the module engine and real settings.
    """
    settings = settings or get_settings()
    factory = session_factory or SessionLocal

    db = factory()
    try:
        removed = _wipe_transactional(db)
    finally:
        db.close()
    _wipe_storage(Path(settings.storage_dir), removed)

    logger.info("demo_reset_wiped", tables=len(removed))

    # Re-seed the intentional demo dataset through the REAL services.
    from app.db.demo_inspections_seed import seed_demo_inspections

    db = factory()
    try:
        results = seed_demo_inspections(db, references=settings.demo_inspection_ref_list)
    finally:
        db.close()
    logger.info("demo_reset_seeded", **results)
    return removed


def _verify_preserved(session_factory=None) -> None:
    factory = session_factory or SessionLocal
    db = factory()
    try:
        tables = _table_names(db)
        missing = [t for t in _PRESERVED_TABLES if t not in tables]
        if missing:  # pragma: no cover — schema corruption guard
            raise RuntimeError(f"Preserved tables missing after reset: {missing}")
        for t in ("users", "rules", "compliance_rules"):
            count = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
            if count == 0:
                raise RuntimeError(f"Preserved table {t} is empty after reset — aborting.")
    finally:
        db.close()


def main() -> None:
    configure_logging(get_settings())
    print("== METRASIGHT SAFE DEMO RESET ==")
    print("Preserves: users, regulatory data, compliance rules, procedures, model versions.")
    print("Removes:   inspections, evidence, findings, reports, complaints, audit, stored files.")
    removed = reset_demo_data()
    _verify_preserved()
    _ = engine.dispose()
    total_rows = sum(v for k, v in removed.items() if not k.startswith("_"))
    print(f"Wiped {len([k for k in removed if not k.startswith('_')])} tables "
          f"({total_rows} rows) and the stored image files.")
    print("Re-seeded the intentional demo dataset through the real pipeline "
          "(real intake + real OCR + real evaluation + real review).")
    print("Demo reset complete.")


if __name__ == "__main__":
    main()
