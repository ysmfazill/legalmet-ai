"""Reliable demo inspections (Prompt 9, Phase 18 — DEMO DATA).

Seeds three demo inspections — ``DEMO-FOOD``, ``DEMO-WATER``, ``DEMO-OIL`` —
each with the COMPLETE lifecycle, produced entirely through the REAL services:

    real synthetic label image → real intake + usability grade → REAL local
    OCR perception → real extracted fields → real deterministic compliance
    evaluation against the seeded (UNVERIFIED research-grade) requirements →
    inspector review of every finding → a final human decision → full audit.

Nothing is mocked and nothing is hard-coded: if the real OCR backend is
unavailable the seed stops after intake and says so in the startup log — it
NEVER silently falls back to a stub. The images are the committed synthetic
labels from ``app/db/demo_images/`` (locally rendered; no third-party
material), and every row is flagged ``is_demo=True`` so the UI can label it.

Idempotent: an inspection whose ``reference_no`` already exists is skipped,
so only the FIRST boot on a fresh database pays the real-OCR cost (engine
init + 3 inferences, roughly a minute on CPU). Disable with
``SEED_DEMO_INSPECTIONS=false``.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    CaptureSource,
    ImageType,
    InspectionDecisionType,
    UserRole,
)
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import Inspection, User
from app.schemas.inspection import CreateInspectionRequest
from app.services.registry import get_services

logger = get_logger(__name__)

_DEMO_DIR = Path(__file__).resolve().parent / "demo_images"

# (reference, image file, product name, category) — the three Phase 18 demos.
_DEMO_INSPECTIONS: list[tuple[str, str, str, str]] = [
    ("DEMO-FOOD", "demo-food.png", "SUNRISE Crunchy Masala (demo)", "food"),
    ("DEMO-WATER", "demo-water.png", "AQUAPURE Drinking Water (demo)", "beverages"),
    ("DEMO-OIL", "demo-oil.png", "GOLDLEAF Sunflower Oil (demo)", "food"),
]


def seed_demo_inspections(db: Session) -> dict[str, str]:
    """Create the three full-lifecycle demo inspections. Idempotent."""
    results: dict[str, str] = {}
    services = get_services()
    inspector = db.execute(
        select(User).where(User.role == UserRole.INSPECTOR.value)
    ).scalars().first()
    if inspector is None:
        logger.warning("demo_inspections_skipped", reason="no inspector user")
        return results

    for reference, image_file, product_name, category in _DEMO_INSPECTIONS:
        existing = db.execute(
            select(Inspection).where(Inspection.reference_no == reference)
        ).scalar_one_or_none()
        if existing is not None:
            results[reference] = "already-present"
            continue
        try:
            results[reference] = _seed_one(
                db, services, reference, image_file, product_name, category, inspector
            )
        except AppError as exc:
            # Real services raised a structured error — record it honestly.
            logger.warning(
                "demo_inspection_partial",
                reference=reference,
                code=str(exc.code.value) if exc.code else "ERROR",
            )
            results[reference] = f"partial: {exc.message}"
    logger.info("demo_inspections_seeded", **results)
    return results


def _seed_one(
    db: Session,
    services,
    reference: str,
    image_file: str,
    product_name: str,
    category: str,
    inspector: User,
) -> str:
    # 1. Inspection (real service) + demo marking + stable reference.
    inspection = services.inspection.create_inspection(
        db,
        inspector_id=inspector.id,
        request=CreateInspectionRequest(
            product_name=product_name,
            product_category=category,
            note="DEMO DATA — synthetic label, full lifecycle demo (Prompt 9 Phase 18).",
        ),
    )
    inspection.reference_no = reference
    inspection.is_demo = True
    db.add(inspection)
    db.commit()

    # 2. Real intake of the real synthetic label bytes.
    data = (_DEMO_DIR / image_file).read_bytes()
    image = services.intake.upload_image(
        db,
        inspection_id=inspection.id,
        filename=image_file,
        declared_mime="image/png",
        data=data,
        capture_source=CaptureSource.UPLOAD,
        image_type=ImageType.FRONT,
        actor_id=inspector.id,
    )
    # The services below re-load the inspection via selectinload but do NOT
    # populate_existing: an object already in this session's identity map
    # would keep its cached (pre-image) packages→images state and wrongly see
    # zero usable images. Each lifecycle step below therefore starts from a
    # clean view of the database. (The HTTP path never needs this — every
    # request gets a fresh session.)
    db.expire_all()

    # 3. REAL perception run (local PaddleOCR). Failure is loud, never mocked.
    runs = services.perception.start_for_inspection(
        db, inspection_id=inspection.id, actor_id=inspector.id
    )
    services.perception.execute_runs([run.id for run in runs])
    # execute_runs commits in its own sessions — expire so the evaluation and
    # review steps below read the runs/fields it just wrote, not stale state.
    db.expire_all()
    statuses = {run.status for run in runs}

    # 4. Real deterministic compliance evaluation.
    evaluation = services.compliance.evaluate_inspection(
        db, inspection_id=inspection.id, actor_id=inspector.id
    )
    db.expire_all()

    # 5. Inspector review: confirm every pending finding (real HITL service).
    findings = services.compliance.findings_for_inspection(db, inspection.id)
    violations = 0
    for finding in findings:
        try:
            services.hitl.review_finding(
                db,
                finding_id=finding.id,
                actor=inspector,
                action="CONFIRM",
                reason="Demo data — confirmed as part of the seeded full lifecycle.",
            )
            if finding.status not in ("COMPLIANT", "NOT_APPLICABLE"):
                violations += 1
        except AppError:
            # A finding already terminal / not confirmable — leave as-is; the
            # seeded review history stays exactly what the services produced.
            pass

    # 6. Final human decision through the real decision gate. The gate blocks
    # COMPLIANT while unresolved critical findings exist; if any remain, the
    # honest demo decision is REQUIRES_FURTHER_REVIEW.
    decision = (
        InspectionDecisionType.NON_COMPLIANT
        if violations
        else InspectionDecisionType.COMPLIANT
    )
    try:
        services.hitl.submit_decision(
            db,
            inspection_id=inspection.id,
            actor=inspector,
            decision=decision,
            reason=(
                f"DEMO DATA — seeded decision over {len(findings)} reviewed findings "
                f"({violations} non-compliant)."
                if violations
                else f"DEMO DATA — seeded decision over {len(findings)} reviewed findings."
            ),
            evaluation_id=evaluation.id,
        )
    except AppError as exc:
        logger.warning(
            "demo_decision_blocked",
            reference=reference,
            reason=exc.message,
        )
        decision = InspectionDecisionType.REQUIRES_FURTHER_REVIEW
        services.hitl.submit_decision(
            db,
            inspection_id=inspection.id,
            actor=inspector,
            decision=decision,
            reason=f"DEMO DATA — decision gate blocked: {exc.message}",
            evaluation_id=evaluation.id,
        )

    # No synthetic audit marker: every service call above already wrote the
    # REAL audit trail (inspection created, image uploaded, perception run,
    # evaluation, finding reviews, decision) — the demo set is identifiable by
    # reference_no and is_demo.
    db.commit()
    return (
        f"complete: runs={sorted(statuses)}, findings={len(findings)}, "
        f"decision={decision.value}, image={image.quality_grade}"
    )
