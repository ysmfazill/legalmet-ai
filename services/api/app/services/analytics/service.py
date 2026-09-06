"""Analytics service — inspection intelligence.

Aggregates findings/inspections into the dashboard summary, surfaces recurring
violation patterns (the seed of "batch inspection intelligence"), and computes
per-batch statistics. All figures are derived from stored findings; nothing
here makes a legal judgement.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    InspectionStatus,
    VerificationLevel,
    VerificationTaskStatus,
    VerificationTaskType,
)
from app.db.base import utcnow
from app.models import (
    AuditEvent,
    BatchInspection,
    CitizenReport,
    ComplianceEvaluation,
    ComplianceFinding,
    EvaluationFinding,
    Inspection,
    InspectionDecision,
    Product,
    Report,
    Rule,
    VerificationTask,
)
from app.schemas.analytics import (
    BatchStats,
    ComplaintPipeline,
    ComplaintPipelineStage,
    DashboardSummary,
    EvidenceQualityMetrics,
    FindingCategorySlice,
    InspectionStatusBreakdown,
    LocationIntelligence,
    LocationSlice,
    OperationalAnalytics,
    OperationalKpis,
    OutcomeSlice,
    RecurringViolation,
    RepeatFindingPattern,
    ReportAnalytics,
    TrendPoint,
)
from app.schemas.inspection import FindingCounts, InspectionSummaryOut

_STATUS_TO_FIELD = {
    # Engine finding statuses (EvaluationFinding, latest evaluation per
    # inspection) — the production UI path. The legacy /analyze demo path
    # writes ComplianceFinding rows instead; its statuses are mapped in
    # _LEGACY_STATUS_TO_FIELD below and the counts union both tables
    # (mutually exclusive per inspection, so no double-counting).
    "COMPLIANT": "compliant",
    # Missing mandatory declaration (NOT_DETECTED) is a violation signal,
    # same pill as engine NON_COMPLIANT.
    "NON_COMPLIANT": "potential_violation",
    "NOT_DETECTED": "potential_violation",
    "REVIEW_REQUIRED": "review_required",
    "NOT_EVALUATED": "review_required",
    "NOT_APPLICABLE": "not_applicable",
}


class AnalyticsService:
    # --- Finding counts ----------------------------------------------------

    @staticmethod
    def _latest_evaluation_ids(
        db: Session, inspection_ids: list[UUID] | None = None
    ) -> list:
        """IDs of the LATEST evaluation per inspection (deterministic: newest
        created_at) — superseded evaluations are never double-counted."""
        latest_sq = (
            select(
                ComplianceEvaluation.inspection_id,
                func.max(ComplianceEvaluation.created_at).label("max_created"),
            )
            .group_by(ComplianceEvaluation.inspection_id)
            .subquery()
        )
        stmt = select(ComplianceEvaluation.id).join(
            latest_sq,
            (ComplianceEvaluation.inspection_id == latest_sq.c.inspection_id)
            & (ComplianceEvaluation.created_at == latest_sq.c.max_created),
        )
        if inspection_ids is not None:
            stmt = stmt.where(ComplianceEvaluation.inspection_id.in_(inspection_ids))
        return list(db.execute(stmt).scalars().all())

    def finding_counts(self, db: Session, *, inspection_id: UUID | None = None) -> FindingCounts:
        """Finding counts for an inspection (or all inspections when omitted).

        Counts BOTH pipelines' findings: the deterministic engine
        (EvaluationFinding, latest evaluation per inspection — what the real
        UI flow produces) and the legacy demo analyze path (ComplianceFinding).
        The two are mutually exclusive per inspection, so the union never
        double-counts.
        """
        counts = FindingCounts()
        ids = self._latest_evaluation_ids(
            db, [inspection_id] if inspection_id is not None else None
        )
        if ids:
            stmt = select(EvaluationFinding.status, func.count()).where(
                EvaluationFinding.evaluation_id.in_(ids)
            )
            stmt = stmt.group_by(EvaluationFinding.status)
            counts = self._counts_from_rows(db.execute(stmt).all())
        legacy_stmt = select(ComplianceFinding.status, func.count()).group_by(
            ComplianceFinding.status
        )
        if inspection_id is not None:
            legacy_stmt = legacy_stmt.where(ComplianceFinding.inspection_id == inspection_id)
        legacy = self._legacy_counts_from_rows(db.execute(legacy_stmt).all())
        return self._merge_counts(counts, legacy)

    def finding_counts_for_inspections(
        self, db: Session, inspection_ids: list[UUID]
    ) -> dict[UUID, FindingCounts]:
        result: dict[UUID, FindingCounts] = {iid: FindingCounts() for iid in inspection_ids}
        if not inspection_ids:
            return result
        # Engine findings: evaluation_id -> inspection_id, count per evaluation.
        eval_rows = db.execute(
            select(ComplianceEvaluation.id, ComplianceEvaluation.inspection_id).where(
                ComplianceEvaluation.id.in_(self._latest_evaluation_ids(db, inspection_ids))
            )
        ).all()
        eval_to_insp = {eid: iid for eid, iid in eval_rows}
        grouped: dict[UUID, list] = {iid: [] for iid in inspection_ids}
        if eval_to_insp:
            rows = db.execute(
                select(EvaluationFinding.evaluation_id, EvaluationFinding.status, func.count())
                .where(EvaluationFinding.evaluation_id.in_(list(eval_to_insp)))
                .group_by(EvaluationFinding.evaluation_id, EvaluationFinding.status)
            ).all()
            for evaluation_id, status, count in rows:
                iid = eval_to_insp.get(evaluation_id)
                if iid is not None:
                    grouped.setdefault(iid, []).append((status, count))
        for iid, rows in grouped.items():
            result[iid] = self._counts_from_rows(rows)
        # Legacy demo-path findings (mutually exclusive with engine findings).
        legacy_rows = db.execute(
            select(
                ComplianceFinding.inspection_id,
                ComplianceFinding.status,
                func.count(),
            )
            .where(ComplianceFinding.inspection_id.in_(inspection_ids))
            .group_by(ComplianceFinding.inspection_id, ComplianceFinding.status)
        ).all()
        legacy_grouped: dict[UUID, list] = {}
        for inspection_id, status, count in legacy_rows:
            legacy_grouped.setdefault(inspection_id, []).append((status, count))
        for iid, rows in legacy_grouped.items():
            merged = self._merge_counts(
                result.get(iid) or FindingCounts(),
                self._legacy_counts_from_rows(rows),
            )
            result[iid] = merged
        return result

    # Legacy analyze-path status vocabulary → FindingCounts fields.
    _LEGACY_STATUS_TO_FIELD = {
        "COMPLIANT": "compliant",
        "POTENTIAL_VIOLATION": "potential_violation",
        "REVIEW_REQUIRED": "review_required",
        "NOT_APPLICABLE": "not_applicable",
        "LOW_CONFIDENCE": "low_confidence",
        "IMAGE_QUALITY_INSUFFICIENT": "image_quality_insufficient",
    }

    @classmethod
    def _legacy_counts_from_rows(cls, rows: list) -> FindingCounts:
        counts = FindingCounts()
        for status, count in rows:
            field_name = cls._LEGACY_STATUS_TO_FIELD.get(status)
            if field_name is not None:
                setattr(counts, field_name, count)
            counts.total += count
        return counts

    @staticmethod
    def _merge_counts(a: FindingCounts, b: FindingCounts) -> FindingCounts:
        merged = FindingCounts()
        for field in (
            "total",
            "compliant",
            "potential_violation",
            "review_required",
            "not_applicable",
            "low_confidence",
            "image_quality_insufficient",
        ):
            setattr(merged, field, getattr(a, field) + getattr(b, field))
        return merged

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
        """Rules that keep failing across inspections — from the LIVE engine
        findings (latest evaluation per inspection)."""
        eval_ids = self._latest_evaluation_ids(db)
        if not eval_ids:
            return []
        stmt = (
            select(
                Rule.field_key,
                EvaluationFinding.requirement_id,
                func.count().label("cnt"),
                func.count(func.distinct(ComplianceEvaluation.inspection_id)).label("insp"),
            )
            .select_from(EvaluationFinding)
            .join(ComplianceEvaluation, EvaluationFinding.evaluation_id == ComplianceEvaluation.id)
            .join(Rule, EvaluationFinding.requirement_id == Rule.id)
            .where(
                EvaluationFinding.evaluation_id.in_(eval_ids),
                # Missing mandatory declarations count as violation signals.
                EvaluationFinding.status.in_(("NON_COMPLIANT", "NOT_DETECTED")),
            )
            .group_by(Rule.field_key, EvaluationFinding.requirement_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = db.execute(stmt).all()

        rule_ids = [r.requirement_id for r in rows if r.requirement_id is not None]
        rule_codes: dict[UUID, str] = {}
        if rule_ids:
            for rule in db.execute(select(Rule).where(Rule.id.in_(rule_ids))).scalars().all():
                rule_codes[rule.id] = rule.rule_code

        return [
            RecurringViolation(
                field_type=row.field_key,
                rule_id=row.requirement_id,
                rule_code=rule_codes.get(row.requirement_id),
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
            # Live engine findings (latest evaluation per inspection), mapped
            # onto the legacy status vocabulary the schema exposes.
            legacy_key = {
                "COMPLIANT": "COMPLIANT",
                "NON_COMPLIANT": "POTENTIAL_VIOLATION",
                "NOT_DETECTED": "POTENTIAL_VIOLATION",
                "REVIEW_REQUIRED": "REVIEW_REQUIRED",
                "NOT_EVALUATED": "REVIEW_REQUIRED",
                "NOT_APPLICABLE": "NOT_APPLICABLE",
            }
            eval_ids = self._latest_evaluation_ids(db, inspection_ids)
            if eval_ids:
                rows = db.execute(
                    select(EvaluationFinding.status, func.count())
                    .where(EvaluationFinding.evaluation_id.in_(eval_ids))
                    .group_by(EvaluationFinding.status)
                ).all()
                for status, count in rows:
                    key = legacy_key.get(status, status)
                    by_status[key] = by_status.get(key, 0) + count

        stats = BatchStats(
            total=len(inspection_ids),
            by_status=by_status,
            review_required=by_status.get("REVIEW_REQUIRED", 0),
            potential_violations=by_status.get("POTENTIAL_VIOLATION", 0),
        )
        # Cache onto the batch row (serialised with enum values as keys).
        batch.total_count = len(inspection_ids)
        batch.stats = stats.model_dump(mode="json", by_alias=True)
        db.flush()
        return stats

    # --- UI-09: operational intelligence ------------------------------------

    _GRANULARITY_SQL = {
        "day": "%Y-%m-%d",
        "week": "%Y-%W",
        "month": "%Y-%m",
    }

    def operational(
        self,
        db: Session,
        *,
        granularity: str = "month",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> OperationalAnalytics:
        """The /analytics operational view (UI-09 §12–§23).

        Every number is a COUNT over stored rows. Rates are None (rendered
        N/A) when their denominator is zero — a 0% would be a fabricated
        statistic (§34).
        """
        results = self._results_by_inspection_all(db)
        inspections = list(db.execute(select(Inspection)).scalars().all())
        if date_from is not None:
            inspections = [i for i in inspections if i.created_at >= date_from]
        if date_to is not None:
            inspections = [i for i in inspections if i.created_at <= date_to]

        # Complaint-led inspections (the existing CitizenReport FK is the only
        # truth for "came from a complaint").
        complaint_links = {
            row[0]
            for row in db.execute(select(CitizenReport.inspection_id)).all()
            if row[0] is not None
        }

        decided = [
            i for i in inspections if results.get(i.id) in ("COMPLIANT", "NON_COMPLIANT")
        ]
        compliant = sum(1 for i in decided if results[i.id] == "COMPLIANT")
        non_compliant = sum(1 for i in decided if results[i.id] == "NON_COMPLIANT")
        review_required = sum(
            1 for i in inspections if results.get(i.id) == "REVIEW_REQUIRED"
        )
        open_count = sum(
            1
            for i in inspections
            if i.status
            not in (InspectionStatus.COMPLETED.value, InspectionStatus.ARCHIVED.value)
        )
        complaint_led = sum(1 for i in inspections if i.id in complaint_links)

        # Evidence quality (the Evidence Planner, §17).
        evidence_quality = self._evidence_quality(db)

        kpis = OperationalKpis(
            total_inspections=len(inspections),
            complaint_led_inspections=complaint_led,
            decided_inspections=len(decided),
            compliance_rate=(compliant / len(decided)) if decided else None,
            non_compliance_rate=(non_compliant / len(decided)) if decided else None,
            review_required=review_required,
            open_inspections=open_count,
            average_evidence_completeness=evidence_quality.average_evidence_completeness,
        )

        outcome_counts: dict[str, int] = {}
        for inspection in inspections:
            key = results.get(inspection.id, "NOT_EVALUATED")
            outcome_counts[key] = outcome_counts.get(key, 0) + 1
        outcome_total = len(inspections)
        outcomes = [
            OutcomeSlice(
                result=key,
                count=count,
                percentage=(count / outcome_total) if outcome_total else None,
            )
            for key, count in sorted(
                outcome_counts.items(), key=lambda kv: kv[1], reverse=True
            )
        ]

        return OperationalAnalytics(
            kpis=kpis,
            trend=self._inspection_trend(db, granularity, date_from, date_to),
            granularity=granularity if granularity in self._GRANULARITY_SQL else "month",
            outcomes=outcomes,
            complaint_pipeline=self._complaint_pipeline(db, complaint_links),
            evidence_quality=evidence_quality,
            finding_categories=self._finding_categories(db, limit=8),
            repeat_findings=self._repeat_findings(db, limit=8),
            locations=self._location_intelligence(db),
            reports=self._report_analytics(db),
            data_note=(
                "Limited data — analytics are based on available inspection records."
                if len(inspections) < 10
                else None
            ),
            generated_at=utcnow(),
        )

    def _results_by_inspection_all(self, db: Session) -> dict:
        """Latest decision → else latest evaluation status → NOT_EVALUATED,
        for every inspection (same derivation rule as the history page)."""
        results: dict = {}
        for decision in (
            db.execute(
                select(InspectionDecision).order_by(InspectionDecision.created_at.asc())
            )
            .scalars()
            .all()
        ):
            results[decision.inspection_id] = decision.decision
        for evaluation in (
            db.execute(
                select(ComplianceEvaluation).order_by(ComplianceEvaluation.created_at.asc())
            )
            .scalars()
            .all()
        ):
            if evaluation.inspection_id not in results:
                results[evaluation.inspection_id] = evaluation.status
        return results

    def _inspection_trend(
        self,
        db: Session,
        granularity: str,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[TrendPoint]:
        fmt = self._GRANULARITY_SQL.get(granularity, self._GRANULARITY_SQL["month"])
        stmt = select(
            func.strftime(fmt, Inspection.created_at).label("period"),
            func.count().label("count"),
        ).group_by("period")
        if date_from is not None:
            stmt = stmt.where(Inspection.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Inspection.created_at <= date_to)
        rows = db.execute(stmt.order_by("period")).all()
        return [TrendPoint(period=period or "unknown", count=count) for period, count in rows]

    def _complaint_pipeline(self, db: Session, complaint_links: set) -> ComplaintPipeline:
        """Citizen Complaint → Reviewed → Accepted → Converted → Completed →
        Finding generated. Real counts from the complaint state machine (§16)."""
        total = db.execute(select(func.count()).select_from(CitizenReport)).scalar_one()
        by_status = dict(
            db.execute(
                select(CitizenReport.status, func.count()).group_by(CitizenReport.status)
            ).all()
        )
        reviewed = total - by_status.get("SUBMITTED", 0)
        # Accepted-or-later: every post-acceptance status in the state machine.
        accepted_or_later = sum(
            count
            for status, count in by_status.items()
            if status
            in (
                "ACCEPTED",
                "ASSIGNED",
                "INSPECTION_SCHEDULED",
                "INSPECTION_COMPLETED",
                "ACTION_TAKEN",
                "CLOSED",
            )
        )
        converted = db.execute(
            select(func.count())
            .select_from(CitizenReport)
            .where(CitizenReport.inspection_id.isnot(None))
        ).scalar_one()
        complaint_inspection_ids = complaint_links
        completed = (
            db.execute(
                select(func.count())
                .select_from(Inspection)
                .where(
                    Inspection.id.in_(complaint_inspection_ids),
                    Inspection.status == InspectionStatus.COMPLETED.value,
                )
            ).scalar_one()
            if complaint_inspection_ids
            else 0
        )
        findings_generated = (
            db.execute(
                select(func.count())
                .select_from(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id.in_(complaint_inspection_ids))
            ).scalar_one()
            if complaint_inspection_ids
            else 0
        )
        stages = [
            ComplaintPipelineStage(
                stage="COMPLAINTS", label="Citizen complaints", count=total
            ),
            ComplaintPipelineStage(
                stage="REVIEWED", label="Department reviewed", count=reviewed
            ),
            ComplaintPipelineStage(
                stage="ACCEPTED", label="Accepted", count=accepted_or_later
            ),
            ComplaintPipelineStage(
                stage="INSPECTIONS", label="Converted to inspection", count=converted
            ),
            ComplaintPipelineStage(
                stage="COMPLETED", label="Inspection completed", count=completed
            ),
            ComplaintPipelineStage(
                stage="FINDINGS", label="Finding generated", count=findings_generated
            ),
        ]
        return ComplaintPipeline(
            stages=stages,
            conversion_rate=(converted / total) if total else None,
        )

    def _evidence_quality(self, db: Session) -> EvidenceQualityMetrics:
        """Evidence Planner aggregates (§17) — REQUIRED vs RECOMMENDED never
        conflated; RECOMMENDED never counts as missing."""
        required_rows = db.execute(
            select(
                VerificationTask.inspection_id,
                func.count().label("total"),
                func.sum(
                    case(
                        (
                            VerificationTask.status.in_(
                                (
                                    VerificationTaskStatus.PENDING.value,
                                    VerificationTaskStatus.IN_PROGRESS.value,
                                )
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("open"),
            )
            .where(VerificationTask.requirement_level == VerificationLevel.REQUIRED.value)
            .group_by(VerificationTask.inspection_id)
        ).all()
        inspections_with_planner = len(required_rows)
        completeness_values: list[float] = []
        missing_required = 0
        incomplete = 0
        for _inspection_id, total, open_count in required_rows:
            total = total or 0
            open_count = int(open_count or 0)
            missing_required += open_count
            if open_count > 0:
                incomplete += 1
            if total > 0:
                completeness_values.append((total - open_count) / total)

        measurements_pending = db.execute(
            select(func.count())
            .select_from(VerificationTask)
            .where(
                VerificationTask.task_type == VerificationTaskType.MEASUREMENT.value,
                VerificationTask.status.in_(
                    (
                        VerificationTaskStatus.PENDING.value,
                        VerificationTaskStatus.IN_PROGRESS.value,
                    )
                ),
            )
        ).scalar_one()

        # Reports blocked by the finalization gate: GENERATED but not
        # finalized, and either required evidence is still open or no human
        # decision exists (UI-08 gate, evaluated here for analytics).
        open_required_by_inspection = {
            inspection_id: int(open_count or 0)
            for inspection_id, _total, open_count in required_rows
        }
        decided_inspections = {
            row[0]
            for row in db.execute(select(InspectionDecision.inspection_id)).all()
        }
        reports = list(db.execute(select(Report)).scalars().all())
        blocked = 0
        for report in reports:
            if report.finalized_at is not None or report.generated_at is None:
                continue
            if open_required_by_inspection.get(report.inspection_id, 0) > 0:
                blocked += 1
            elif report.inspection_id not in decided_inspections:
                blocked += 1

        return EvidenceQualityMetrics(
            inspections_with_planner=inspections_with_planner,
            average_evidence_completeness=(
                sum(completeness_values) / len(completeness_values)
                if completeness_values
                else None
            ),
            incomplete_inspections=incomplete,
            missing_required_evidence=missing_required,
            measurements_pending=measurements_pending,
            reports_blocked_by_evidence=blocked,
        )

    def _finding_categories(self, db: Session, *, limit: int) -> list[FindingCategorySlice]:
        """Top engine-finding requirement categories — codes + titles that
        EXIST in the regulatory rule system (§18), never invented groupings."""
        rows = db.execute(
            select(
                Rule.rule_code,
                Rule.title,
                func.count().label("cnt"),
                func.count(func.distinct(ComplianceEvaluation.inspection_id)).label("insp"),
            )
            .select_from(EvaluationFinding)
            .join(
                ComplianceEvaluation,
                EvaluationFinding.evaluation_id == ComplianceEvaluation.id,
            )
            .join(Rule, EvaluationFinding.requirement_id == Rule.id, isouter=True)
            .group_by(Rule.rule_code, Rule.title)
            .order_by(func.count().desc())
            .limit(limit)
        ).all()
        total = db.execute(select(func.count()).select_from(EvaluationFinding)).scalar_one()
        return [
            FindingCategorySlice(
                rule_code=rule_code or "—",
                label=title or rule_code or "Requirement",
                count=count,
                inspection_count=insp,
                percentage=(count / total) if total else None,
            )
            for rule_code, title, count, insp in rows
        ]

    def _repeat_findings(self, db: Session, *, limit: int) -> list[RepeatFindingPattern]:
        """Engine findings recurring across inspections of the same product —
        neutral wording: a repeated INSPECTION finding, never a violator label
        (§21)."""
        rows = db.execute(
            select(
                Product.name,
                Rule.rule_code,
                Rule.title,
                func.count().label("cnt"),
                func.count(func.distinct(ComplianceEvaluation.inspection_id)).label("insp"),
            )
            .select_from(EvaluationFinding)
            .join(
                ComplianceEvaluation,
                EvaluationFinding.evaluation_id == ComplianceEvaluation.id,
            )
            .join(Inspection, ComplianceEvaluation.inspection_id == Inspection.id)
            .join(Product, Inspection.product_id == Product.id, isouter=True)
            .join(Rule, EvaluationFinding.requirement_id == Rule.id, isouter=True)
            .group_by(Product.name, Rule.rule_code, Rule.title)
            .having(func.count(func.distinct(ComplianceEvaluation.inspection_id)) >= 2)
            .order_by(func.count().desc())
            .limit(limit)
        ).all()
        return [
            RepeatFindingPattern(
                product_name=name or "Unknown product",
                rule_code=rule_code or "—",
                label=title or rule_code or "Requirement",
                inspection_count=insp,
                occurrence_count=cnt,
            )
            for name, rule_code, title, cnt, insp in rows
        ]

    def _location_intelligence(self, db: Session) -> LocationIntelligence:
        """From REAL complaint locations only (§19) — no GPS, no fake map.
        Insufficient data → the honest empty state."""
        rows = db.execute(
            select(CitizenReport.location, func.count())
            .where(CitizenReport.location.isnot(None), CitizenReport.location != "")
            .group_by(CitizenReport.location)
        ).all()
        if not rows:
            return LocationIntelligence(
                locations=[],
                sufficient=False,
                note="Location intelligence will appear as inspection locations accumulate.",
            )
        locations: list[LocationSlice] = []
        for location, complaint_count in rows:
            inspection_count = db.execute(
                select(func.count())
                .select_from(Inspection)
                .join(CitizenReport, CitizenReport.inspection_id == Inspection.id)
                .where(CitizenReport.location == location)
            ).scalar_one()
            finding_count = db.execute(
                select(func.count())
                .select_from(EvaluationFinding)
                .join(
                    ComplianceEvaluation,
                    EvaluationFinding.evaluation_id == ComplianceEvaluation.id,
                )
                .join(
                    CitizenReport,
                    CitizenReport.inspection_id == ComplianceEvaluation.inspection_id,
                )
                .where(CitizenReport.location == location)
            ).scalar_one()
            locations.append(
                LocationSlice(
                    location=location,
                    complaint_count=complaint_count,
                    inspection_count=inspection_count,
                    finding_count=finding_count,
                )
            )
        locations.sort(key=lambda s: s.complaint_count, reverse=True)
        return LocationIntelligence(locations=locations, sufficient=True)

    def _report_analytics(self, db: Session) -> ReportAnalytics:
        """Report lifecycle counts from the report records + the append-only
        audit trail (§23)."""
        reports = list(db.execute(select(Report)).scalars().all())
        event_counts = dict(
            db.execute(
                select(AuditEvent.event_type, func.count()).group_by(AuditEvent.event_type)
            ).all()
        )
        return ReportAnalytics(
            generated=len([r for r in reports if r.generated_at is not None]),
            finalized=len([r for r in reports if r.finalized_at is not None]),
            amended=len([r for r in reports if r.status == "AMENDED"]),
            pdf_exports=event_counts.get("REPORT_EXPORTED_PDF", 0),
            docx_exports=event_counts.get("REPORT_EXPORTED_DOCX", 0),
        )
