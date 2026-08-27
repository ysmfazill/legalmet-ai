"""Analytics service — inspection intelligence.

Aggregates findings/inspections into the dashboard summary, surfaces recurring
violation patterns (the seed of "batch inspection intelligence"), and computes
per-batch statistics. All figures are derived from stored findings; nothing
here makes a legal judgement.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ComplianceStatus
from app.db.base import utcnow
from app.models import BatchInspection, ComplianceFinding, Inspection, Rule
from app.schemas.analytics import (
    BatchStats,
    DashboardSummary,
    InspectionStatusBreakdown,
    RecurringViolation,
)
from app.schemas.inspection import FindingCounts, InspectionSummaryOut

_STATUS_TO_FIELD = {
    ComplianceStatus.COMPLIANT.value: "compliant",
    ComplianceStatus.POTENTIAL_VIOLATION.value: "potential_violation",
    ComplianceStatus.REVIEW_REQUIRED.value: "review_required",
    ComplianceStatus.NOT_APPLICABLE.value: "not_applicable",
    ComplianceStatus.LOW_CONFIDENCE.value: "low_confidence",
    ComplianceStatus.IMAGE_QUALITY_INSUFFICIENT.value: "image_quality_insufficient",
}


class AnalyticsService:
    # --- Finding counts ----------------------------------------------------

    def finding_counts(self, db: Session, *, inspection_id: UUID | None = None) -> FindingCounts:
        stmt = select(ComplianceFinding.status, func.count()).group_by(ComplianceFinding.status)
        if inspection_id is not None:
            stmt = stmt.where(ComplianceFinding.inspection_id == inspection_id)
        return self._counts_from_rows(db.execute(stmt).all())

    def finding_counts_for_inspections(
        self, db: Session, inspection_ids: list[UUID]
    ) -> dict[UUID, FindingCounts]:
        result: dict[UUID, FindingCounts] = {iid: FindingCounts() for iid in inspection_ids}
        if not inspection_ids:
            return result
        stmt = (
            select(ComplianceFinding.inspection_id, ComplianceFinding.status, func.count())
            .where(ComplianceFinding.inspection_id.in_(inspection_ids))
            .group_by(ComplianceFinding.inspection_id, ComplianceFinding.status)
        )
        grouped: dict[UUID, list] = {iid: [] for iid in inspection_ids}
        for inspection_id, status, count in db.execute(stmt).all():
            grouped.setdefault(inspection_id, []).append((status, count))
        for iid, rows in grouped.items():
            result[iid] = self._counts_from_rows(rows)
        return result

    @staticmethod
    def _counts_from_rows(rows: list) -> FindingCounts:
        counts = FindingCounts()
        for status, count in rows:
            field_name = _STATUS_TO_FIELD.get(status)
            if field_name is not None:
                setattr(counts, field_name, count)
            counts.total += count
        return counts

    # --- Dashboard ---------------------------------------------------------

    def dashboard_summary(self, db: Session, *, recent_limit: int = 8) -> DashboardSummary:
        status_rows = db.execute(
            select(Inspection.status, func.count()).group_by(Inspection.status)
        ).all()
        breakdown = InspectionStatusBreakdown(
            total=sum(count for _, count in status_rows),
            by_status={status: count for status, count in status_rows},
        )

        overall = self.finding_counts(db)

        recent = list(
            db.execute(
                select(Inspection).order_by(Inspection.created_at.desc()).limit(recent_limit)
            ).scalars().all()
        )
        counts_by_inspection = self.finding_counts_for_inspections(db, [i.id for i in recent])
        recent_out: list[InspectionSummaryOut] = []
        for inspection in recent:
            summary = InspectionSummaryOut.model_validate(inspection)
            summary.finding_counts = counts_by_inspection.get(inspection.id)
            recent_out.append(summary)

        return DashboardSummary(
            inspections=breakdown,
            findings=overall,
            recent_inspections=recent_out,
            recurring_violations=self.recurring_violations(db),
            generated_at=utcnow(),
        )

    def recurring_violations(self, db: Session, *, limit: int = 10) -> list[RecurringViolation]:
        stmt = (
            select(
                ComplianceFinding.field_type,
                ComplianceFinding.rule_id,
                func.count().label("cnt"),
                func.count(func.distinct(ComplianceFinding.inspection_id)).label("insp"),
            )
            .where(ComplianceFinding.status == ComplianceStatus.POTENTIAL_VIOLATION.value)
            .group_by(ComplianceFinding.field_type, ComplianceFinding.rule_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = db.execute(stmt).all()

        rule_ids = [r.rule_id for r in rows if r.rule_id is not None]
        rule_codes: dict[UUID, str] = {}
        if rule_ids:
            for rule in db.execute(select(Rule).where(Rule.id.in_(rule_ids))).scalars().all():
                rule_codes[rule.id] = rule.rule_code

        return [
            RecurringViolation(
                field_type=row.field_type,
                rule_id=row.rule_id,
                rule_code=rule_codes.get(row.rule_id),
                count=row.cnt,
                affected_inspections=row.insp,
            )
            for row in rows
        ]

    # --- Batch -------------------------------------------------------------

    def compute_batch_stats(self, db: Session, batch: BatchInspection) -> BatchStats:
        inspection_ids = list(
            db.execute(
                select(Inspection.id).where(Inspection.batch_id == batch.id)
            ).scalars().all()
        )
        by_status: dict[str, int] = {}
        if inspection_ids:
            rows = db.execute(
                select(ComplianceFinding.status, func.count())
                .where(ComplianceFinding.inspection_id.in_(inspection_ids))
                .group_by(ComplianceFinding.status)
            ).all()
            by_status = {status: count for status, count in rows}

        stats = BatchStats(
            total=len(inspection_ids),
            by_status=by_status,
            review_required=by_status.get(ComplianceStatus.REVIEW_REQUIRED.value, 0),
            potential_violations=by_status.get(ComplianceStatus.POTENTIAL_VIOLATION.value, 0),
        )
        # Cache onto the batch row (serialised with enum values as keys).
        batch.total_count = len(inspection_ids)
        batch.stats = stats.model_dump(mode="json", by_alias=True)
        db.flush()
        return stats
