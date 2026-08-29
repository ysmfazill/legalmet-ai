"""Compliance service — the read/orchestration seam used by the API layer.

The API routers stay thin: they authenticate, delegate here, and serialise.
All compliance logic lives in this package (never in a router, never in a
React component). Reads are transparent: the latest evaluation, its findings,
or an explicit NOT_EVALUATED when none exists.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import ComplianceEvaluation, EvaluationFinding, Inspection
from app.services.compliance.engine import ENGINE_VERSION, ComplianceEngine
from app.services.compliance.evaluators import registered_rule_types
from app.services.compliance.seed_rules import seed_compliance_rules

# Engine findings surfaced in the review queue: every status that requires an
# inspector's eye. COMPLIANT / NOT_APPLICABLE are informational and never queued.
REVIEW_QUEUE_STATUSES = (
    "REVIEW_REQUIRED",
    "NON_COMPLIANT",
    "NOT_DETECTED",
    "NOT_EVALUATED",
)

_RULE_TYPE_DESCRIPTIONS = {
    "PRESENCE": "The declaration must be present and readable.",
    "TEXT_MATCH": "The detected text must equal the configured text.",
    "TEXT_PATTERN": "The detected text must match a configured regular expression.",
    "NUMERIC_VALUE": "A deterministically parseable numeric value must be present.",
    "UNIT_MATCH": "The declared unit must be one of the accepted units.",
    "MRP_FORMAT": "The MRP must carry a parseable amount plus the 'inclusive of all "
                  "taxes' wording.",
    "DATE_FORMAT": "The date must match a recognized month/year (or full date) shape.",
    "CONTACT_FORMAT": "A telephone number and an e-mail address must both be present.",
    "DECLARATION_FORMAT": "A plain declaration of at least the configured length.",
    "FIELD_REQUIRED": "A mandatory declaration must be present.",
    "FIELD_NOT_REQUIRED": "The declaration must NOT carry this field.",
    "RANGE": "A numeric value must lie within the configured range.",
    "COMPARISON": "A numeric value must satisfy the configured comparison.",
}


class ComplianceService:
    """Read layer + engine front door for the compliance API."""

    def __init__(self, engine: ComplianceEngine) -> None:
        self._engine = engine

    # -- writes ---------------------------------------------------------------

    def evaluate_inspection(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> ComplianceEvaluation:
        """Run one evaluation — a NEW row; historical results are untouched."""
        return self._engine.evaluate(db, inspection_id=inspection_id, actor_id=actor_id)

    # -- reads ----------------------------------------------------------------

    def latest_evaluation(
        self, db: Session, inspection_id: uuid.UUID
    ) -> ComplianceEvaluation | None:
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Inspection not found: {inspection_id}")
        return (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id == inspection_id)
                .options(selectinload(ComplianceEvaluation.findings))
                .order_by(ComplianceEvaluation.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def get_evaluation(
        self, db: Session, evaluation_id: uuid.UUID
    ) -> ComplianceEvaluation:
        evaluation = (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.id == evaluation_id)
                .options(selectinload(ComplianceEvaluation.findings))
            )
            .scalars()
            .first()
        )
        if evaluation is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Evaluation not found: {evaluation_id}")
        return evaluation

    def findings_for_inspection(
        self, db: Session, inspection_id: uuid.UUID
    ) -> list[EvaluationFinding]:
        """Findings of the LATEST evaluation for an inspection (spec Phase 16)."""
        latest = self.latest_evaluation(db, inspection_id)
        if latest is None:
            return []
        return list(latest.findings)

    def get_finding(self, db: Session, finding_id: uuid.UUID) -> EvaluationFinding:
        finding = db.get(EvaluationFinding, finding_id)
        if finding is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Finding not found: {finding_id}")
        return finding

    def review_queue(
        self, db: Session, *, limit: int, offset: int
    ) -> tuple[list[EvaluationFinding], int]:
        """Engine findings awaiting an inspector decision (Phase 18).

        Only findings from the LATEST evaluation per inspection are queued —
        superseded evaluations never re-enter the queue. This is a read-only
        queue: it records "system finding — inspector decision pending" and
        nothing here approves or rejects anything (final approval is a later
        phase).
        """
        # Latest evaluation per inspection (deterministic: newest created_at).
        latest_sq = (
            select(
                ComplianceEvaluation.inspection_id,
                func.max(ComplianceEvaluation.created_at).label("max_created"),
            )
            .group_by(ComplianceEvaluation.inspection_id)
            .subquery()
        )
        latest_eval_ids = select(ComplianceEvaluation.id).join(
            latest_sq,
            (ComplianceEvaluation.inspection_id == latest_sq.c.inspection_id)
            & (ComplianceEvaluation.created_at == latest_sq.c.max_created),
        )
        base = select(EvaluationFinding).where(
            EvaluationFinding.evaluation_id.in_(latest_eval_ids),
            EvaluationFinding.status.in_(REVIEW_QUEUE_STATUSES),
        )
        total = (
            db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
        )
        items = list(
            db.execute(base.order_by(EvaluationFinding.created_at.desc())
                       .limit(limit).offset(offset))
            .scalars()
            .all()
        )
        return items, total

    # -- transparency -----------------------------------------------------------

    @staticmethod
    def engine_info() -> dict:
        return {
            "engineVersion": ENGINE_VERSION,
            "ruleTypes": [
                {"ruleType": t, "description": _RULE_TYPE_DESCRIPTIONS.get(t, "")}
                for t in registered_rule_types()
            ],
            "usesLlm": False,
        }

    @staticmethod
    def seed_rules(db: Session) -> dict:
        return seed_compliance_rules(db)
