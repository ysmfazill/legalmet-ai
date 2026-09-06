"""Department Command Center aggregation service (UI-04).

One read-only pass that assembles everything the /department dashboard shows.
Design rules:

* **Server-side aggregation.** COUNT / GROUP BY happen in SQL (status, risk,
  date, location). The only Python-side work is over the bounded set of OPEN
  complaints (evidence completeness and effective priority need the evidence
  JSON, which SQL cannot aggregate) — a single query, no N+1.
* **Every number is real.** Zero when the database is empty; nothing is ever
  fabricated, interpolated or "demo-filled".
* **Triage language only.** Priorities are prioritization signals (the
  official decision when set, else the deterministic system screening);
  evidence completeness measures evidence, not violation likelihood. No
  output of this service can express a legal conclusion.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.base import utcnow
from app.models import (
    AuditEvent,
    CitizenReport,
    Lot,
    LotPackage,
    VerificationResult,
    VerificationTask,
)
from app.schemas.department import (
    AttentionItemOut,
    ComplaintTrendPointOut,
    DepartmentActivityOut,
    DepartmentDashboardOut,
    DepartmentKpisOut,
    DepartmentPipelineOut,
    EvidenceCompletenessOut,
    LocationRollupOut,
    PhysicalVerificationOut,
    PriorityComplaintOut,
)
from app.services.citizen.service import (
    STALE_COMPLAINT_DAYS,
    _TERMINAL_STATUSES,
    complaint_evidence_completeness,
    effective_priority,
    evidence_band,
)

# Complaint statuses that have passed through department hands at all
# (anything beyond a fresh SUBMITTED, including a REJECT decision).
_REVIEWED_STATUSES = {
    "UNDER_REVIEW",
    "REQUEST_INFORMATION",
    "REJECTED",
    "ACCEPTED",
    "ASSIGNED",
    "INSPECTION_SCHEDULED",
    "INSPECTION_COMPLETED",
    "ACTION_TAKEN",
    "CLOSED",
}
_ACCEPTED_STATUSES = {
    "ACCEPTED",
    "ASSIGNED",
    "INSPECTION_SCHEDULED",
    "INSPECTION_COMPLETED",
    "ACTION_TAKEN",
    "CLOSED",
}
_DECISION_STATUSES = {"ACTION_TAKEN", "CLOSED"}

# The department's own complaint operations, as recorded in the audit trail.
_ACTIVITY_EVENT_TYPES = (
    "COMPLAINT_REVIEW_STARTED",
    "COMPLAINT_ACCEPTED",
    "COMPLAINT_REJECTED",
    "COMPLAINT_INFO_REQUESTED",
    "COMPLAINT_ASSIGNED",
    "COMPLAINT_INSPECTION_CREATED",
    "COMPLAINT_INSPECTION_COMPLETED",
    "COMPLAINT_ACTION_TAKEN",
    "COMPLAINT_CLOSED",
)

_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Only columns needed for the open-complaint pass (keeps it one cheap query).
_OPEN_COMPLAINT_COLUMNS = (
    CitizenReport.id,
    CitizenReport.reference,
    CitizenReport.status,
    CitizenReport.product,
    CitizenReport.issue,
    CitizenReport.location,
    CitizenReport.shop,
    CitizenReport.description,
    CitizenReport.evidence,
    CitizenReport.screening_risk,
    CitizenReport.official_priority,
    CitizenReport.assigned_inspector_id,
    CitizenReport.inspection_id,
    CitizenReport.created_at,
)


class DepartmentDashboardService:
    """Stateless aggregator — instantiated per request, like CitizenService."""

    def dashboard(self, db: Session, *, window_days: int = 30) -> DepartmentDashboardOut:
        generated = utcnow()

        # ---- SQL aggregation: status distribution --------------------------
        status_rows = db.execute(
            select(CitizenReport.status, func.count(CitizenReport.id)).group_by(
                CitizenReport.status
            )
        ).all()
        counts = {status: count for status, count in status_rows}
        total = sum(counts.values())

        converted = db.execute(
            select(func.count(CitizenReport.id)).where(CitizenReport.inspection_id.is_not(None))
        ).scalar_one()

        # ---- trend: real created_at grouping, zero-filled ------------------
        window_start = (generated - timedelta(days=window_days - 1)).date()
        trend_rows = db.execute(
            select(
                func.date(CitizenReport.created_at).label("day"),
                func.count(CitizenReport.id),
            )
            .where(CitizenReport.created_at >= window_start)
            .group_by("day")
        ).all()
        by_day = {str(day): count for day, count in trend_rows}
        trend = [
            ComplaintTrendPointOut(
                date=(window_start + timedelta(days=i)).isoformat(),
                count=by_day.get((window_start + timedelta(days=i)).isoformat(), 0),
            )
            for i in range(window_days)
        ]
        window_complaints = sum(p.count for p in trend)

        # ---- the bounded open-complaint pass (triage signals) --------------
        open_rows = db.execute(
            select(*_OPEN_COMPLAINT_COLUMNS).where(
                CitizenReport.status.not_in(tuple(_TERMINAL_STATUSES))
            )
        ).all()

        risk_distribution = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNSET": 0}
        high_priority_open = 0
        incomplete_evidence_open = 0
        stale_open = 0
        completeness_scores: list[int] = []
        bands = {"COMPLETE": 0, "PARTIAL": 0, "MINIMAL": 0}
        stale_cutoff = generated - timedelta(days=STALE_COMPLAINT_DAYS)

        def _aware(value: datetime) -> datetime:
            # SQLite returns naive UTC timestamps; normalize before comparing
            # with the tz-aware `generated` clock.
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

        for row in open_rows:
            priority, _source = effective_priority(row)
            risk_distribution[priority or "UNSET"] += 1
            if priority == "HIGH":
                high_priority_open += 1
            score = complaint_evidence_completeness(row)
            completeness_scores.append(score)
            bands[evidence_band(score)] += 1
            if score < 50:
                incomplete_evidence_open += 1
            if row.created_at is not None and _aware(row.created_at) < stale_cutoff:
                stale_open += 1

        pending_review = sum(
            counts.get(s, 0) for s in ("SUBMITTED", "UNDER_REVIEW", "REQUEST_INFORMATION")
        )

        # ---- needs attention (every value computed above / in SQL) ---------
        needs_attention = [
            AttentionItemOut(
                kind="HIGH_PRIORITY_AWAITING_REVIEW",
                label="High-priority complaints awaiting review",
                description="Effective priority HIGH and still in submission or review.",
                count=high_priority_open,
                filters={"risk": "HIGH"},
            ),
            AttentionItemOut(
                kind="INCOMPLETE_EVIDENCE",
                label="Complaints with minimal evidence",
                description="Open complaints whose evidence completeness is below 50.",
                count=incomplete_evidence_open,
                filters={"evidence": "MINIMAL"},
            ),
            AttentionItemOut(
                kind="ACCEPTED_AWAITING_ASSIGNMENT",
                label="Accepted complaints awaiting assignment",
                description="Accepted for further review but no inspector assigned yet.",
                count=counts.get("ACCEPTED", 0),
                filters={"status": "ACCEPTED"},
            ),
            AttentionItemOut(
                kind="PENDING_BEYOND_THRESHOLD",
                label=f"Open longer than {STALE_COMPLAINT_DAYS} days",
                description="Still open although submitted more than two weeks ago.",
                count=stale_open,
                filters={"stale": "true"},
            ),
        ]

        # ---- priority queue (top open complaints by triage signal) ---------
        priority_rank = lambda row: (  # noqa: E731 — local, documented ordering
            _PRIORITY_RANK.get(effective_priority(row)[0] or "", 3),
            row.created_at or generated,
        )
        priority_queue = [
            PriorityComplaintOut(
                id=row.id,
                reference=row.reference,
                status=row.status,
                product=row.product,
                issue=row.issue,
                location=row.location,
                priority=effective_priority(row)[0],
                priority_source=effective_priority(row)[1],
                evidence_completeness=complaint_evidence_completeness(row),
                created_at=row.created_at,
            )
            for row in sorted(open_rows, key=priority_rank)[:8]
        ]

        # ---- locations (only where citizens actually reported one) ---------
        location_rows = db.execute(
            select(
                CitizenReport.location,
                func.count(CitizenReport.id),
                func.sum(
                    func.coalesce(CitizenReport.official_priority, CitizenReport.screening_risk)
                    == "HIGH"
                ),
                func.count(CitizenReport.inspection_id),
            )
            .where(CitizenReport.location.is_not(None))
            .group_by(CitizenReport.location)
            .order_by(func.count(CitizenReport.id).desc())
            .limit(8)
        ).all()
        locations = [
            LocationRollupOut(
                area=(area or "").strip(),
                complaints=count,
                high_priority=int(high or 0),
                inspections=int(linked or 0),
            )
            for area, count, high, linked in location_rows
            if (area or "").strip()
        ]

        # ---- recent activity: REAL audit events, department actors ----------
        activity_rows = db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "citizen_report",
                AuditEvent.event_type.in_(_ACTIVITY_EVENT_TYPES),
            )
            .options(selectinload(AuditEvent.actor))
            .order_by(AuditEvent.created_at.desc())
            .limit(12)
        ).scalars().all()
        recent_activity = [
            DepartmentActivityOut(
                id=event.id,
                event=event.event_type,
                actor_name=event.actor.full_name if event.actor else "Department",
                created_at=event.created_at,
                reference=(event.payload or {}).get("reference"),
                report_id=event.entity_id,
            )
            for event in activity_rows
        ]

        # ---- UI-07: physical verification workload (real SQL counts) -------
        _open_statuses = ("PENDING", "IN_PROGRESS")  # VerificationTaskStatus
        physical_verification = PhysicalVerificationOut(
            inspections_requiring_verification=db.execute(
                select(func.count(func.distinct(VerificationTask.inspection_id))).where(
                    VerificationTask.task_type == "MEASUREMENT",
                    VerificationTask.requirement_level == "REQUIRED",
                    VerificationTask.lot_package_id.is_(None),
                    VerificationTask.status.in_(_open_statuses),
                )
            ).scalar_one(),
            measurements_completed=db.execute(
                select(func.count(VerificationResult.id))
                .select_from(VerificationResult)
                .join(VerificationTask, VerificationTask.id == VerificationResult.task_id)
                .where(VerificationTask.task_type == "MEASUREMENT")
            ).scalar_one(),
            lots_under_verification=db.execute(
                select(func.count(Lot.id)).where(Lot.status == "IN_PROGRESS")
            ).scalar_one(),
            lots_awaiting_measurement=db.execute(
                select(func.count(func.distinct(Lot.id)))
                .select_from(Lot)
                .join(LotPackage, LotPackage.lot_id == Lot.id)
                .where(Lot.status == "IN_PROGRESS", LotPackage.status == "PENDING")
            ).scalar_one(),
            lots_completed=db.execute(
                select(func.count(Lot.id)).where(
                    Lot.status.in_(("COMPLIANT", "NON_COMPLIANT", "REQUIRES_REVIEW"))
                )
            ).scalar_one(),
        )

        return DepartmentDashboardOut(
            generated_at=generated,
            window_days=window_days,
            window_complaints=window_complaints,            kpis=DepartmentKpisOut(
                total_complaints=total,
                pending_review=pending_review,
                high_priority=high_priority_open,
                converted_to_inspection=converted,
                under_investigation=counts.get("INSPECTION_SCHEDULED", 0),
                resolved=counts.get("ACTION_TAKEN", 0) + counts.get("CLOSED", 0),
                rejected=counts.get("REJECTED", 0),
                unassigned_open=db.execute(
                    select(func.count(CitizenReport.id)).where(
                        CitizenReport.assigned_inspector_id.is_(None),
                        CitizenReport.status.not_in(tuple(_TERMINAL_STATUSES)),
                    )
                ).scalar_one(),
            ),
            status_distribution=counts,
            trend=trend,
            risk_distribution=risk_distribution,
            evidence=EvidenceCompletenessOut(
                average=(
                    round(sum(completeness_scores) / len(completeness_scores))
                    if completeness_scores
                    else 0
                ),
                scored=len(completeness_scores),
                complete=bands["COMPLETE"],
                partial=bands["PARTIAL"],
                minimal=bands["MINIMAL"],
            ),
            needs_attention=needs_attention,
            physical_verification=physical_verification,
            pipeline=DepartmentPipelineOut(
                citizen_reports=total,
                department_review=sum(counts.get(s, 0) for s in _REVIEWED_STATUSES),
                accepted=sum(counts.get(s, 0) for s in _ACCEPTED_STATUSES),
                inspection_assigned=db.execute(
                    select(func.count(CitizenReport.id)).where(
                        CitizenReport.assigned_inspector_id.is_not(None)
                    )
                ).scalar_one(),
                inspection_completed=counts.get("INSPECTION_COMPLETED", 0)
                + counts.get("ACTION_TAKEN", 0)
                + counts.get("CLOSED", 0),
                decision=sum(counts.get(s, 0) for s in _DECISION_STATUSES),
            ),
            locations=locations,
            recent_activity=recent_activity,
            priority_queue=priority_queue,
        )
