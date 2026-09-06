"""Seed DEMO regulatory procedures for UI-07 development (NOT verified law).

Inserts, idempotently, a permissible-error (MEASUREMENT_TOLERANCE) procedure
bound to the ACTIVE regulation version, so the deterministic evaluation path
(WITHIN_TOLERANCE / EXCEEDS_TOLERANCE with a frozen rule code + version) is
visible in the local development browser.

HONESTY: the values are PLACEHOLDERS for development. The title and
source_reference say so explicitly. Replace with the verified Legal Metrology
procedure (Second Schedule, Legal Metrology (Packaged Commodities) Rules)
before any production use. The sampling procedure is deliberately NOT seeded
so the AI-recommended + inspector-confirmation flow stays visible in the
demo.

Usage:  python -m scripts.seed_demo_procedures
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.enums import (  # noqa: E402
    RegulationVersionStatus,
    RegulatoryProcedureKind,
)
from app.db.session import SessionLocal  # noqa: E402
from app.models import Regulation, RegulationVersion, RegulatoryProcedure  # noqa: E402

_DEMO_NOTE = (
    "DEMO CONFIGURATION for local development — placeholder value, NOT a "
    "verified legal tolerance. Replace with the Second Schedule (Legal "
    "Metrology (Packaged Commodities) Rules) permissible-error table before "
    "production use."
)

# Flat 4.5% placeholder — enough to demo WITHIN (492 vs 500 g = -1.6%) and
# EXCEEDS (470 vs 500 g = -6%) paths deterministically.
_CONFIG = {"permissibleError": {"type": "PERCENT", "value": "4.5"}}


def seed_demo_procedure() -> None:
    db = SessionLocal()
    try:
        version = db.execute(
            select(RegulationVersion)
            .join(Regulation, Regulation.id == RegulationVersion.regulation_id)
            .where(
                Regulation.is_demo.is_(False),
                RegulationVersion.status == RegulationVersionStatus.ACTIVE.value,
            )
            .order_by(Regulation.code.asc())
            .limit(1)
        ).scalar_one_or_none()
        if version is None:
            print("No active non-demo regulation version found — run the regulatory seed first.")
            return

        code = "DEMO-TOLERANCE-NET-QUANTITY"
        existing = db.execute(
            select(RegulatoryProcedure).where(RegulatoryProcedure.code == code)
        ).scalar_one_or_none()
        if existing is not None:
            existing.configuration = _CONFIG
            existing.active = True
            print(f"Updated existing demo procedure {code} on version {version.version_label}.")
        else:
            db.add(
                RegulatoryProcedure(
                    regulation_version_id=version.id,
                    kind=RegulatoryProcedureKind.MEASUREMENT_TOLERANCE.value,
                    code=code,
                    title=(
                        "[DEMO] Permissible error — net quantity of pre-packaged "
                        "goods (placeholder)"
                    ),
                    configuration=_CONFIG,
                    source_reference=_DEMO_NOTE,
                    active=True,
                    is_demo=False,
                )
            )
            print(f"Seeded demo procedure {code} on version {version.version_label}.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_procedure()
