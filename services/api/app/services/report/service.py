"""Report & Evidence Pack service (UI-08).

THE CONTRACT: the report is a DEFENSABLE, TRACEABLE, VERSIONED,
EVIDENCE-BACKED, INSPECTOR-REVIEWED decision-support artifact.

    PACKAGE → EVIDENCE → FINDING → REGULATORY BASIS → VERIFICATION
    → INSPECTOR DECISION → REPORT → AUDIT TRAIL

Rules enforced HERE (never only in the frontend):

* creation — one live report per inspection; RBAC: INSPECTOR/SUPERVISOR/ADMIN.
* generation — builds an immutable snapshot from REAL records only. Source
  complaint evidence (citizen scan) and official inspection evidence are
  collected separately and labelled distinctly — never merged.
* finalization gate — REQUIRED evidence must be resolved AND an inspector
  decision must exist. RECOMMENDED evidence never blocks. Missing items are
  listed, never silently ignored.
* amendment — a new version with a mandatory reason; the previous finalized
  snapshot is preserved verbatim. Nothing is ever silently overwritten.
* exports — the snapshot (frozen at generation time) is the ONLY input to
  PDF/DOCX. A later data change can never rewrite an exported report's claims.
* every transition writes an append-only audit event with the acting human.

No content is ever fabricated: absent evaluation → "Regulatory evaluation
unavailable — manual review required."; absent measurement → manual-entry
notes; the report result is the inspector's decision or NOT_EVALUATED.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    AuditEventType,
    InspectionStatus,
    LotPackageStatus,
    ReportStatus,
    UserRole,
    VerificationLevel,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.base import utcnow
from app.models import (
    CitizenReport,
    ComplianceEvaluation,
    EvaluationFinding,
    ExtractedField,
    Inspection,
    InspectionDecision,
    Lot,
    LotPackage,
    Report,
    ReportEvidence,
    ReportVersion,
    User,
    VerificationResult,
    VerificationTask,
)
from app.services.audit.service import AuditService

# Roles that may create/generate/finalize/amend a report.
_REPORT_WRITE_ROLES = frozenset(
    {UserRole.INSPECTOR.value, UserRole.SUPERVISOR.value, UserRole.ADMIN.value}
)
# Roles that may read internal reports (a citizen has no account and no route).
_REPORT_READ_ROLES = frozenset(
    {
        UserRole.INSPECTOR.value,
        UserRole.SUPERVISOR.value,
        UserRole.ADMIN.value,
        UserRole.AUDITOR.value,
    }
)

MAX_EVIDENCE_ITEMS = 200  # manifest cap; exports note when the cap is hit


@dataclass(frozen=True)
class FinalizationGate:
    """Outcome of the finalization check — the ONLY finalization authority."""

    allowed: bool
    missing_required_evidence: list[str]
    missing_decision: bool
    missing_findings: bool
    recommended_open: int

    @property
    def blockers(self) -> list[str]:
        blockers = list(self.missing_required_evidence)
        if self.missing_decision:
            blockers.append(
                "No inspector decision recorded — the report cannot state a "
                "result without one."
            )
        return blockers


class ReportService:
    """Report lifecycle: create → generate → review → finalize → export → amend."""

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    # ------------------------------------------------------------------ reads

    def list_reports(
        self,
        db: Session,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        inspection_id: uuid.UUID | None = None,
        query: str | None = None,
    ) -> tuple[list[dict], int]:
        """Report Center rows + total. Real DB records only, newest first."""
        stmt = select(Report).options(selectinload(Report.versions))
        count_stmt = select(func.count()).select_from(Report)
        if status:
            stmt = stmt.where(Report.status == status)
            count_stmt = count_stmt.where(Report.status == status)
        if inspection_id:
            stmt = stmt.where(Report.inspection_id == inspection_id)
            count_stmt = count_stmt.where(Report.inspection_id == inspection_id)
        total = db.execute(count_stmt).scalar_one()
        rows = (
            db.execute(
                stmt.order_by(Report.updated_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        items = [self._summary_row(db, r) for r in rows]
        if query:
            q = query.strip().lower()
            items = [
                i
                for i in items
                if q in (i["inspection_reference"] or "").lower()
                or q in (i["product_name"] or "").lower()
                or q in (i["inspector_name"] or "").lower()
                or q in (i["result"] or "").lower()
                or q in (i["status"] or "").lower()
            ]
        return items, total

    def kpis(self, db: Session) -> dict:
        """Total / Draft / Finalized / Exported / Requires Review — real counts."""
        rows = db.execute(
            select(Report.status, func.count()).group_by(Report.status)
        ).all()
        by_status = {status: count for status, count in rows}
        requires_review = (
            db.execute(
                select(func.count())
                .select_from(Report)
                .where(Report.result == "REVIEW_REQUIRED")
            ).scalar_one()
            or 0
        )
        return {
            "total": sum(by_status.values()),
            "draft": by_status.get(ReportStatus.DRAFT.value, 0),
            "finalized": by_status.get(ReportStatus.FINALIZED.value, 0),
            "exported": by_status.get(ReportStatus.EXPORTED.value, 0),
            "under_review": by_status.get(ReportStatus.UNDER_REVIEW.value, 0),
            "amended": by_status.get(ReportStatus.AMENDED.value, 0),
            "requires_review": requires_review,
        }

    def get_report(self, db: Session, report_id: uuid.UUID) -> dict:
        """GET /reports/{id} — the full current read model."""
        report = self._get_report(db, report_id)
        return self._detail_row(db, report)

    def get_report_for_inspection(
        self, db: Session, inspection_id: uuid.UUID
    ) -> dict | None:
        report = self._report_of_inspection(db, inspection_id)
        return self._detail_row(db, report) if report else None

    def audit_events(self, db: Session, report_id: uuid.UUID) -> list[dict]:
        """The report's own lifecycle events, from the append-only trail."""
        report = self._get_report(db, report_id)
        events = self._audit.list_for_inspection(db, report.inspection_id)
        out: list[dict] = []
        for event in events:
            payload = event.payload or {}
            if str(payload.get("reportId", "")) != str(report.id):
                continue
            out.append(self._audit_row(db, event))
        return out

    # ------------------------------------------------------------- lifecycle

    def create_report(
        self, db: Session, *, inspection_id: uuid.UUID, actor: User, note: str | None = None
    ) -> Report:
        """POST /reports — one live report per inspection (DRAFT, v1)."""
        self._assert_write_role(actor)
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        existing = self._report_of_inspection(db, inspection_id)
        if existing is not None:
            raise ConflictError(
                "A report already exists for this inspection — open it to "
                "continue (reports are never duplicated)."
            )
        report = Report(
            inspection_id=inspection_id,
            version=1,
            status=ReportStatus.DRAFT.value,
            result="NOT_EVALUATED",
            created_by=actor.id,
        )
        db.add(report)
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.REPORT_CREATED,
            entity_type="report",
            entity_id=report.id,
            actor_id=actor.id,
            inspection_id=inspection_id,
            payload={
                "reportId": str(report.id),
                "actorRole": actor.role,
                "inspectionId": str(inspection_id),
                "note": note,
            },
        )
        db.commit()
        return report

    def generate_report(
        self, db: Session, *, report_id: uuid.UUID, actor: User, note: str | None = None
    ) -> ReportVersion:
        """POST /reports/{id}/generate — freeze a new immutable snapshot.

        Generation is allowed from any status (a DRAFT is first-reviewed; an
        AMENDED report is regenerated after findings changed). Each generation
        is a NEW version — the previous snapshot is never modified.
        """
        self._assert_write_role(actor)
        report = self._get_report(db, report_id)
        self._assert_actor_may_work(db, report.inspection_id, actor)

        # --- gather the REAL data ------------------------------------------------
        inspection = db.get(Inspection, report.inspection_id)
        evaluation = self._latest_evaluation(db, report.inspection_id)
        findings = list(evaluation.findings) if evaluation else []
        measurement_rows = self._measurement_rows(db, report.inspection_id)
        lot_rows = self._lot_rows(db, report.inspection_id)
        decision = self._latest_decision(db, report.inspection_id)
        source_complaint = self._source_complaint(db, report.inspection_id)
        completeness = self._completeness(db, report.inspection_id)

        next_version = self._next_version(db, report.id)
        snapshot = self._build_snapshot(
            db,
            inspection=inspection,
            evaluation=evaluation,
            findings=findings,
            measurements=measurement_rows,
            lots=lot_rows,
            decision=decision,
            source_complaint=source_complaint,
            completeness=completeness,
            report=report,
            version=next_version,
        )

        is_amendment = next_version > 1
        version_row = ReportVersion(
            report_id=report.id,
            version=next_version,
            snapshot=snapshot,
            reason=(
                "Amendment — findings changed after finalization"
                if is_amendment
                else "Initial generation"
            ),
            created_by=actor.id,
        )
        db.add(version_row)
        db.flush()

        # Evidence manifest — references to EXISTING records, ordered, E-00N.
        manifest = self._build_manifest(
            db, inspection_id=report.inspection_id, findings=findings
        )
        for sequence, item in enumerate(manifest, start=1):
            db.add(
                ReportEvidence(
                    report_version_id=version_row.id,
                    sequence=sequence,
                    evidence_type=item["evidence_type"],
                    evidence_id=item["evidence_id"],
                    label=item["label"],
                    detail=item.get("detail"),
                )
            )
        db.flush()

        report.version = next_version
        report.generated_at = utcnow()
        report.status = ReportStatus.UNDER_REVIEW.value
        report.result = snapshot["result"]
        db.flush()

        self._audit.record(
            db,
            event_type=(
                AuditEventType.REPORT_AMENDED
                if is_amendment
                else AuditEventType.REPORT_GENERATED
            ),
            entity_type="report",
            entity_id=report.id,
            actor_id=actor.id,
            inspection_id=report.inspection_id,
            payload={
                "reportId": str(report.id),
                "actorRole": actor.role,
                "version": next_version,
                "versionId": str(version_row.id),
                "result": snapshot["result"],
                "findingCount": len(findings),
                "evidenceCount": len(manifest),
                "note": note,
            },
        )
        db.commit()
        return version_row

    def review_report(
        self, db: Session, *, report_id: uuid.UUID, actor: User, note: str | None = None
    ) -> Report:
        """POST /reports/{id}/review — mark the human review of the content."""
        self._assert_write_role(actor)
        report = self._get_report(db, report_id)
        self._assert_actor_may_work(db, report.inspection_id, actor)
        if report.status == ReportStatus.DRAFT.value or not report.generated_at:
            raise ConflictError(
                "Report generation requires additional evidence — generate the "
                "report before reviewing it."
            )
        report.status = ReportStatus.UNDER_REVIEW.value
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.REPORT_REVIEWED,
            entity_type="report",
            entity_id=report.id,
            actor_id=actor.id,
            inspection_id=report.inspection_id,
            payload={
                "reportId": str(report.id),
                "actorRole": actor.role,
                "version": report.version,
                "note": note,
            },
        )
        db.commit()
        return report

    def finalize_report(
        self, db: Session, *, report_id: uuid.UUID, actor: User, note: str | None = None
    ) -> Report:
        """POST /reports/{id}/finalize — the finalization GATE lives here.

        Blocked while REQUIRED evidence is unresolved or no inspector decision
        exists. The block list is returned to the caller verbatim — the spec
        message: "Report cannot be finalized until required evidence is
        resolved."
        """
        self._assert_write_role(actor)
        report = self._get_report(db, report_id)
        self._assert_actor_may_work(db, report.inspection_id, actor)
        if not report.generated_at:
            raise ConflictError(
                "Report generation requires additional evidence — generate the "
                "report before finalizing it."
            )
        if report.status == ReportStatus.FINALIZED.value:
            raise ConflictError(
                "This report is already finalized — amend it to issue a new "
                "version."
            )

        gate = self.finalization_gate(db, report.id)
        if not gate.allowed:
            raise ConflictError(
                "Report cannot be finalized until required evidence is "
                "resolved. " + "; ".join(gate.blockers)
            )

        report.status = ReportStatus.FINALIZED.value
        report.finalized_at = utcnow()
        report.finalized_by = actor.id
        # UI-10: finalizing the report completes the inspection lifecycle —
        # COMPLETED was previously a terminal state no workflow ever wrote,
        # so decided+finalized inspections kept showing as mid-lifecycle.
        inspection = db.get(Inspection, report.inspection_id)
        if inspection is not None and inspection.status != InspectionStatus.ARCHIVED.value:
            inspection.status = InspectionStatus.COMPLETED.value
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.REPORT_FINALIZED,
            entity_type="report",
            entity_id=report.id,
            actor_id=actor.id,
            inspection_id=report.inspection_id,
            payload={
                "reportId": str(report.id),
                "actorRole": actor.role,
                "version": report.version,
                "result": report.result,
                "note": note,
            },
        )
        db.commit()
        return report

    def amend_report(
        self, db: Session, *, report_id: uuid.UUID, actor: User, reason: str
    ) -> ReportVersion:
        """POST /reports/{id}/amend — new version with a MANDATORY reason.

        The previous finalized version is preserved verbatim (nothing is ever
        overwritten). Internally: mark AMENDED, then regenerate.
        """
        self._assert_write_role(actor)
        report = self._get_report(db, report_id)
        self._assert_actor_may_work(db, report.inspection_id, actor)
        if not (reason and reason.strip()):
            raise ValidationError(
                "An amendment reason is mandatory — an unexplained amendment "
                "is never accepted."
            )
        if report.status not in (
            ReportStatus.FINALIZED.value,
            ReportStatus.EXPORTED.value,
            ReportStatus.AMENDED.value,
        ):
            raise ConflictError(
                "Only a finalized (or exported/amended) report can be amended — "
                "regenerate a draft instead."
            )
        report.status = ReportStatus.AMENDED.value
        report.amendment_reason = reason.strip()
        db.flush()

        version = self.generate_report(db, report_id=report.id, actor=actor, note=reason)
        # generate_report re-reads the row; keep the amendment reason exact.
        report.amendment_reason = reason.strip()
        report.status = ReportStatus.AMENDED.value
        db.flush()
        db.commit()
        return version

    def record_export(
        self,
        db: Session,
        *,
        report_id: uuid.UUID,
        actor: User,
        fmt: str,
        version_id: uuid.UUID,
    ) -> None:
        """Audited export bookkeeping (called by the export endpoints)."""
        report = self._get_report(db, report_id)
        if fmt not in ("pdf", "docx"):
            raise ValidationError(f"Unknown export format: {fmt}")
        if report.status == ReportStatus.FINALIZED.value:
            report.status = ReportStatus.EXPORTED.value
            db.flush()
        self._audit.record(
            db,
            event_type=(
                AuditEventType.REPORT_EXPORTED_PDF
                if fmt == "pdf"
                else AuditEventType.REPORT_EXPORTED_DOCX
            ),
            entity_type="report",
            entity_id=report.id,
            actor_id=actor.id,
            inspection_id=report.inspection_id,
            payload={
                "reportId": str(report.id),
                "actorRole": actor.role,
                "versionId": str(version_id),
                "version": report.version,
                "format": fmt,
            },
        )
        db.commit()

    # ------------------------------------------------------------------- gate

    def finalization_gate(self, db: Session, report_id: uuid.UUID) -> FinalizationGate:
        """The single finalization authority — also exposed for the UI."""
        report = self._get_report(db, report_id)
        completeness = self._completeness(db, report.inspection_id)
        decision = self._latest_decision(db, report.inspection_id)
        evaluation = self._latest_evaluation(db, report.inspection_id)
        missing_decision = decision is None
        missing_findings = evaluation is None
        gate = FinalizationGate(
            allowed=completeness["required_open"] == 0 and decision is not None,
            missing_required_evidence=completeness["blockers"],
            missing_decision=missing_decision,
            missing_findings=missing_findings,
            recommended_open=completeness["recommended_open"],
        )
        return gate

    # ----------------------------------------------------------- evidence pack

    def evidence_pack(self, db: Session, report_id: uuid.UUID) -> dict:
        """GET /reports/{id}/evidence-pack — the exportable evidence bundle."""
        report = self._get_report(db, report_id)
        version = self._current_version(db, report.id)
        if version is None:
            raise ConflictError(
                "Report generation requires additional evidence — no snapshot "
                "exists yet. Generate the report first."
            )
        completeness = self._completeness(db, report.inspection_id)
        items = [
            {
                "id": row.id,
                "ref": f"E-{row.sequence:03d}",
                "sequence": row.sequence,
                "evidence_type": row.evidence_type,
                "evidence_id": row.evidence_id,
                "label": row.label,
                "detail": row.detail,
            }
            for row in db.execute(
                select(ReportEvidence)
                .where(ReportEvidence.report_version_id == version.id)
                .order_by(ReportEvidence.sequence.asc())
            )
            .scalars()
        ]
        snapshot = version.snapshot or {}
        return {
            "pack_id": version.id,
            "report_id": report.id,
            "inspection_id": report.inspection_id,
            "report_version": report.version,
            "created_at": version.created_at,
            "evidence_count": len(items),
            "completeness": completeness,
            "items": items,
            "source_complaint": snapshot.get("sourceComplaint"),
            "decision": snapshot.get("decision"),
            "audit_events": self.audit_events(db, report.id),
        }

    # --------------------------------------------------------------- internals

    def _get_report(self, db: Session, report_id: uuid.UUID) -> Report:
        report = (
            db.execute(
                select(Report)
                .where(Report.id == report_id)
                .options(selectinload(Report.versions))
            )
            .scalars()
            .first()
        )
        if report is None:
            raise NotFoundError(f"Report not found: {report_id}")
        return report

    def _report_of_inspection(
        self, db: Session, inspection_id: uuid.UUID
    ) -> Report | None:
        return (
            db.execute(
                select(Report).where(Report.inspection_id == inspection_id)
            )
            .scalars()
            .first()
        )

    def _current_version(self, db: Session, report_id: uuid.UUID) -> ReportVersion | None:
        report = self._get_report(db, report_id)
        if not report.versions:
            return None
        return max(report.versions, key=lambda v: v.version)

    def _next_version(self, db: Session, report_id: uuid.UUID) -> int:
        row = db.execute(
            select(func.max(ReportVersion.version)).where(
                ReportVersion.report_id == report_id
            )
        ).scalar_one()
        return (row or 0) + 1

    def _latest_evaluation(
        self, db: Session, inspection_id: uuid.UUID
    ) -> ComplianceEvaluation | None:
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

    def _latest_decision(
        self, db: Session, inspection_id: uuid.UUID
    ) -> InspectionDecision | None:
        return (
            db.execute(
                select(InspectionDecision)
                .where(InspectionDecision.inspection_id == inspection_id)
                .order_by(InspectionDecision.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def _source_complaint(
        self, db: Session, inspection_id: uuid.UUID
    ) -> CitizenReport | None:
        return (
            db.execute(
                select(CitizenReport).where(CitizenReport.inspection_id == inspection_id)
            )
            .scalars()
            .first()
        )

    def _assert_write_role(self, actor: User) -> None:
        if actor.role not in _REPORT_WRITE_ROLES:
            raise ForbiddenError(
                "Only an inspector, supervisor or admin may manage reports."
            )

    def _assert_actor_may_work(
        self, db: Session, inspection_id: uuid.UUID, actor: User
    ) -> None:
        """Inspector assignment guard (mirrors the lots/verification layers)."""
        if actor.role in (UserRole.SUPERVISOR.value, UserRole.ADMIN.value):
            return
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        if inspection.inspector_id is not None and inspection.inspector_id != actor.id:
            raise ForbiddenError(
                "Only the assigned inspector (or a supervisor/admin) may work "
                "on this inspection's report."
            )

    # ------------------------------------------------------- snapshot building

    def _build_snapshot(
        self,
        db: Session,
        *,
        inspection: Inspection,
        evaluation: ComplianceEvaluation | None,
        findings: list[EvaluationFinding],
        measurements: list[dict],
        lots: list[dict],
        decision: InspectionDecision | None,
        source_complaint: CitizenReport | None,
        completeness: dict,
        report: Report,
        version: int,
    ) -> dict:
        """Freeze everything the report asserts — camelCase keys, real data only.

        The snapshot is the ONLY input to exports, so later data changes can
        never rewrite what an exported report claimed.
        """
        product_name = None
        product_category = None
        if inspection.product is not None:
            product_name = inspection.product.name
            product_category = inspection.product.category
        inspector = inspection.inspector
        decided_by_name = None
        if decision is not None:
            actor = db.get(User, decision.decided_by)
            decided_by_name = actor.full_name if actor else None

        result = decision.decision if decision is not None else "NOT_EVALUATED"

        regulatory_basis: list[dict] = []
        if evaluation is not None:
            version_label = None
            if evaluation.regulatory_version is not None:
                version_label = evaluation.regulatory_version.version_label
            regulatory_basis.append(
                {
                    "engineVersion": evaluation.engine_version,
                    "regulatoryVersionLabel": version_label,
                    "contextDate": evaluation.context_date.isoformat(),
                    "summary": evaluation.summary or {},
                    "status": evaluation.status,
                    "source": "OFFICIAL",
                }
            )
        else:
            regulatory_basis.append(
                {
                    "engineVersion": None,
                    "regulatoryVersionLabel": None,
                    "contextDate": None,
                    "summary": {},
                    "status": "NOT_EVALUATED",
                    "source": "OFFICIAL",
                    "note": "Regulatory evaluation unavailable — manual review required.",
                }
            )

        finding_rows = [self._finding_row(db, f) for f in findings]
        measurement_rows = [self._measurement_row_fields(m) for m in measurements]
        complaint_out = (
            self._complaint_fields(source_complaint) if source_complaint else None
        )

        return {
            "reportId": str(report.id),
            "inspectionId": str(inspection.id),
            "inspectionReference": inspection.reference_no,
            "version": version,
            "generatedAt": utcnow().isoformat(),
            "result": result,
            "inspection": {
                "reference": inspection.reference_no,
                "status": inspection.status,
                "date": inspection.created_at.isoformat()
                if inspection.created_at
                else None,
                "inspectorName": inspector.full_name if inspector else None,
                "inspectorId": str(inspection.inspector_id)
                if inspection.inspector_id
                else None,
                "productName": product_name,
                "productCategory": product_category,
                "completedAt": inspection.completed_at.isoformat()
                if inspection.completed_at
                else None,
                "note": inspection.note,
            },
            "sourceComplaint": complaint_out,
            "findings": finding_rows,
            "regulatoryBasis": regulatory_basis,
            "measurements": measurement_rows,
            "lots": lots,
            "decision": (
                {
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "decidedBy": str(decision.decided_by),
                    "decidedByName": decided_by_name,
                    "decidedAt": decision.decided_at.isoformat(),
                    "evaluationId": str(decision.evaluation_id)
                    if decision.evaluation_id
                    else None,
                }
                if decision is not None
                else None
            ),
            "completeness": completeness,
            "boundaryNote": (
                "Reports are decision-support artifacts generated from "
                "inspection evidence. They do not replace the authority of "
                "the authorized Legal Metrology inspector."
            ),
        }

    def _finding_row(self, db: Session, finding: EvaluationFinding) -> dict:
        """One finding frozen into the snapshot: engine status + human review.

        The report NEVER claims a violation merely because OCR confidence is
        low: the status comes from the deterministic engine, the review state
        from the human overlay, and both are shown.
        """
        from app.models import Image

        requirement = finding.requirement
        requirement_text = (
            getattr(requirement, "text", None) or getattr(requirement, "title", None)
        )
        rule_code = None
        rule_version_label = None
        if finding.rule is not None:
            rule_code = finding.rule.rule_code
            rule_version_label = str(finding.rule.rule_version)
        regulatory_version_label = None
        if finding.evaluation.regulatory_version is not None:
            regulatory_version_label = finding.evaluation.regulatory_version.version_label
        provenance = finding.provenance or {}

        # Evidence status: the frozen extracted-field perception outcome.
        evidence_status = "NOT_EVALUATED"
        if finding.extracted_field is not None:
            evidence_status = finding.extracted_field.status
        elif finding.status == "NOT_DETECTED":
            evidence_status = "ABSENT"

        # Source: citizen-scan image (SOURCE) vs official inspection image
        # (OFFICIAL) — distinct labels, never merged.
        source = "OFFICIAL"
        if finding.image_id is not None:
            img = db.get(Image, finding.image_id)
            if img is not None and img.is_demo:
                source = "SOURCE"

        return {
            "id": str(finding.id),
            "status": finding.status,
            "severity": finding.severity,
            "applicability": finding.applicability,
            "requirement": requirement_text,
            "requirementCode": provenance.get("requirementCode"),
            "ruleCode": rule_code,
            "ruleVersion": rule_version_label,
            "regulatoryVersionLabel": regulatory_version_label,
            "detectedValue": finding.detected_value,
            "expectedValue": finding.expected_value,
            "explanation": finding.explanation,
            "reviewState": finding.review_state,
            "evidenceStatus": evidence_status,
            "source": source,
            "provenance": {
                "sourceName": provenance.get("sourceName"),
                "verificationStatus": provenance.get("verificationStatus"),
                "documentIdentifier": provenance.get("documentIdentifier"),
                "effectiveWindow": provenance.get("effectiveWindow"),
            },
        }

    def _measurement_row_fields(self, m: dict) -> dict:
        """CamelCase one measurement-history row for the snapshot."""
        evaluation = m.get("evaluation") or {}
        observed = m.get("observed") or {}
        return {
            "measurementId": str(m["measurement_id"]),
            "anchor": (m.get("anchor") or {}).get("kind", "DECLARATION"),
            "declaredValue": m.get("declared_value"),
            "measuredValue": m.get("measured_value"),
            "unit": m.get("unit"),
            "observedDifference": observed.get("difference"),
            "observedPercent": observed.get("percentDifference"),
            "instrumentId": m.get("instrument_id"),
            "instrumentVerificationStatus": m.get("instrument_verification_status"),
            "recordedBy": str(m.get("recorded_by")),
            "recordedAt": m.get("recorded_at").isoformat()
            if m.get("recorded_at")
            else None,
            "evaluation": {
                "status": evaluation.get("status"),
                "outcome": evaluation.get("outcome"),
                "ruleCode": evaluation.get("ruleCode"),
            },
            "note": (
                "Manual measurement entry — instrument integration not "
                "available in prototype."
                if not m.get("instrument_id")
                else None
            ),
        }

    def _complaint_fields(self, complaint: CitizenReport) -> dict:
        return {
            "reference": complaint.reference,
            "status": complaint.status,
            "product": complaint.product,
            "location": complaint.location,
            "issue": complaint.issue,
            "description": complaint.description,
            "priority": complaint.official_priority or complaint.screening_risk,
            "submittedAt": complaint.created_at.isoformat(),
        }

    # -------------------------------------------------- completeness / history

    def _completeness(self, db: Session, inspection_id: uuid.UUID) -> dict:
        """Planner status distilled: REQUIRED vs RECOMMENDED, never conflated."""
        from app.models import Package

        required_total = (
            db.execute(
                select(func.count())
                .select_from(VerificationTask)
                .where(
                    VerificationTask.inspection_id == inspection_id,
                    VerificationTask.requirement_level
                    == VerificationLevel.REQUIRED.value,
                )
            ).scalar_one()
            or 0
        )
        required_open = 0
        recommended_open = 0
        blockers: list[str] = []
        rows = db.execute(
            select(VerificationTask)
            .where(
                VerificationTask.inspection_id == inspection_id,
                VerificationTask.status.in_(["PENDING", "IN_PROGRESS"]),
                VerificationTask.lot_package_id.is_(None),
            )
            .order_by(VerificationTask.created_at.asc())
        )
        for task in rows.scalars():
            if task.requirement_level == VerificationLevel.REQUIRED.value:
                required_open += 1
                blockers.append(
                    f"Required evidence unresolved: task {task.id} "
                    f"({task.task_type}) is {task.status}"
                )
            else:
                recommended_open += 1

        field_count = (
            db.execute(
                select(func.count())
                .select_from(ExtractedField)
                .join(Package, Package.id == ExtractedField.package_id)
                .where(Package.inspection_id == inspection_id)
            ).scalar_one()
            or 0
        )
        evaluation = self._latest_evaluation(db, inspection_id)
        finding_count = (
            db.execute(
                select(func.count())
                .select_from(EvaluationFinding)
                .where(EvaluationFinding.evaluation_id == evaluation.id)
            ).scalar_one()
            if evaluation
            else 0
        )
        return {
            "required_total": required_total,
            "required_open": required_open,
            "recommended_open": recommended_open,
            "evidence_items": field_count + finding_count + required_total,
            "finding_rows": finding_count,
            "counts": {
                "fields": field_count,
                "findings": finding_count,
                "requiredTasks": required_total,
                "openRequired": required_open,
                "openRecommended": recommended_open,
            },
            "blockers": blockers,
            "can_finalize": required_open == 0,
        }

    def _measurement_rows(self, db: Session, inspection_id: uuid.UUID) -> list[dict]:
        """Reuse the verification layer's measurement history (single source)."""
        from app.services.verification.service import VerificationService

        verification = VerificationService(self._audit)
        return verification.measurement_history(db, inspection_id)

    def _lot_rows(self, db: Session, inspection_id: uuid.UUID) -> list[dict]:
        """Lot intelligence summary rows, from the lot layer's own read model."""
        lots = list(
            db.execute(
                select(Lot)
                .where(Lot.inspection_id == inspection_id)
                .options(selectinload(Lot.packages))
                .order_by(Lot.created_at.asc())
            )
            .scalars()
        )
        out: list[dict] = []
        for lot in lots:
            sampled = sum(
                1 for p in lot.packages if p.status != LotPackageStatus.NOT_SAMPLED.value
            )
            measured = sum(
                1 for p in lot.packages if p.status == LotPackageStatus.MEASURED.value
            )
            sampling_label = (
                f"{sampled} of {lot.lot_size} packages sampled, {measured} "
                "measured — AI-assisted inspection recommendation when no "
                "statutory procedure applies"
            )
            out.append(
                {
                    "lotId": str(lot.id),
                    "label": lot.label,
                    "declaredValue": lot.declared_value,
                    "lotSize": lot.lot_size,
                    "sampled": sampled,
                    "measured": measured,
                    "decision": lot.decision,
                    "decisionReason": lot.decision_reason,
                    "samplingLabel": sampling_label,
                }
            )
        return out

    # ------------------------------------------------------- evidence manifest

    def _build_manifest(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        findings: list[EvaluationFinding],
    ) -> list[dict]:
        """Ordered references to EXISTING records — nothing is copied.

        Order: source complaint first, then official images, extracted
        fields, measurements, lots, findings. Stable E-00N identifiers are
        assigned by sequence at insert time.
        """
        from app.models import Image, Package

        manifest: list[dict] = []

        complaint = self._source_complaint(db, inspection_id)
        if complaint is not None:
            manifest.append(
                {
                    "evidence_type": "COMPLAINT",
                    "evidence_id": complaint.id,
                    "label": f"Source complaint {complaint.reference}",
                    "detail": {
                        "reference": complaint.reference,
                        "issue": complaint.issue,
                        "status": complaint.status,
                        "origin": "SOURCE",
                    },
                }
            )

        images = (
            db.execute(
                select(Image)
                .join(Package, Package.id == Image.package_id)
                .where(Package.inspection_id == inspection_id)
                .order_by(Image.created_at.asc())
            )
            .scalars()
            .all()
        )
        for image in images:
            manifest.append(
                {
                    "evidence_type": "IMAGE",
                    "evidence_id": image.id,
                    "label": f"Image {image.original_filename} ({image.image_type})",
                    "detail": {
                        "storageKey": image.storage_key,
                        "processedStorageKey": image.processed_storage_key,
                        "filename": image.original_filename,
                        "mimeType": image.mime_type,
                        "origin": "SOURCE" if image.is_demo else "OFFICIAL",
                    },
                }
            )

        fields = (
            db.execute(
                select(ExtractedField)
                .join(Package, Package.id == ExtractedField.package_id)
                .where(Package.inspection_id == inspection_id)
                .order_by(ExtractedField.created_at.asc())
            )
            .scalars()
            .all()
        )
        for field in fields:
            manifest.append(
                {
                    "evidence_type": "EXTRACTED_FIELD",
                    "evidence_id": field.id,
                    "label": f"Extracted field {field.field_type} ({field.status})",
                    "detail": {
                        "fieldType": field.field_type,
                        "status": field.status,
                        "rawText": field.raw_text,
                        "normalizedValue": field.normalized_value,
                        "confidence": field.confidence,
                        "imageId": str(field.image_id),
                    },
                }
            )

        tasks = (
            db.execute(
                select(VerificationTask)
                .where(
                    VerificationTask.inspection_id == inspection_id,
                    VerificationTask.task_type == "MEASUREMENT",
                )
                .options(selectinload(VerificationTask.results))
                .order_by(VerificationTask.created_at.asc())
            )
            .scalars()
            .all()
        )
        for task in tasks:
            for result in task.results:
                manifest.append(
                    {
                        "evidence_type": "MEASUREMENT",
                        "evidence_id": result.id,
                        "label": f"Measurement {result.measured_value} {result.unit or ''}".strip(),
                        "detail": {
                            "taskId": str(task.id),
                            "measuredValue": result.measured_value,
                            "unit": result.unit,
                            "instrumentId": result.instrument_id,
                            "recordedAt": result.recorded_at.isoformat(),
                        },
                    }
                )

        lots = list(
            db.execute(
                select(Lot)
                .where(Lot.inspection_id == inspection_id)
                .order_by(Lot.created_at.asc())
            )
            .scalars()
        )
        for lot in lots:
            manifest.append(
                {
                    "evidence_type": "LOT",
                    "evidence_id": lot.id,
                    "label": f"Lot {lot.label} ({lot.lot_size} packages)",
                    "detail": {
                        "declaredValue": lot.declared_value,
                        "lotSize": lot.lot_size,
                        "status": lot.status,
                        "decision": lot.decision,
                    },
                }
            )

        for finding in findings:
            manifest.append(
                {
                    "evidence_type": "FINDING",
                    "evidence_id": finding.id,
                    "label": f"Finding {finding.status} ({finding.severity})",
                    "detail": {
                        "status": finding.status,
                        "severity": finding.severity,
                        "ruleCode": finding.rule.rule_code if finding.rule else None,
                        "reviewState": finding.review_state,
                    },
                }
            )
        return manifest[:MAX_EVIDENCE_ITEMS]

    # ---------------------------------------------------------- summary rows

    def _summary_row(self, db: Session, report: Report) -> dict:
        inspection = db.get(Inspection, report.inspection_id)
        product_name = (
            inspection.product.name if inspection and inspection.product else None
        )
        inspector_name = (
            inspection.inspector.full_name
            if inspection and inspection.inspector
            else None
        )
        version = self._current_version(db, report.id)
        evidence_count = 0
        if version is not None:
            evidence_count = (
                db.execute(
                    select(func.count())
                    .select_from(ReportEvidence)
                    .where(ReportEvidence.report_version_id == version.id)
                ).scalar_one()
                or 0
            )
        return {
            "id": report.id,
            "inspection_id": report.inspection_id,
            "inspection_reference": inspection.reference_no if inspection else "",
            "product_name": product_name,
            "inspection_date": inspection.created_at if inspection else None,
            "inspector_name": inspector_name,
            "result": report.result,
            "status": report.status,
            "version": report.version,
            "evidence_count": evidence_count,
            "generated_at": report.generated_at,
            "finalized_at": report.finalized_at,
            "finalized_by": report.finalized_by,
            "amendment_reason": report.amendment_reason,
            "created_by": report.created_by,
            "updated_at": report.updated_at,
        }

    def _detail_row(self, db: Session, report: Report) -> dict:
        inspection = db.get(Inspection, report.inspection_id)
        summary = self._summary_row(db, report)
        creator = db.get(User, report.created_by)
        finalizer = db.get(User, report.finalized_by) if report.finalized_by else None
        complaint = self._source_complaint(db, report.inspection_id)
        completeness = self._completeness(db, report.inspection_id)
        versions = []
        for v in sorted(report.versions, key=lambda x: x.version):
            author = db.get(User, v.created_by)
            versions.append(
                {
                    "version": v.version,
                    "id": v.id,
                    "reason": v.reason,
                    "created_at": v.created_at,
                    "created_by": v.created_by,
                    "created_by_name": author.full_name if author else None,
                    "status_at_creation": None,
                }
            )
        current = self._current_version(db, report.id)
        snapshot = current.snapshot if current else None
        return {
            **summary,
            "product_category": inspection.product.category
            if inspection and inspection.product
            else None,
            "inspection_status": inspection.status if inspection else None,
            "inspector_id": inspection.inspector_id if inspection else None,
            "created_by_name": creator.full_name if creator else None,
            "finalized_by_name": finalizer.full_name if finalizer else None,
            "source_complaint": self._complaint_fields(complaint) if complaint else None,
            "evidence": completeness,
            "versions": versions,
            "snapshot": snapshot,
        }

    def _audit_row(self, db: Session, event) -> dict:
        actor = db.get(User, event.actor_id) if event.actor_id else None
        payload = event.payload or {}
        return {
            "id": event.id,
            "actor_id": event.actor_id,
            "actor_role": payload.get("actorRole"),
            "actor_name": actor.full_name if actor else None,
            "event_type": event.event_type,
            "report_id": payload.get("reportId"),
            "inspection_id": event.inspection_id,
            "payload": payload,
            "created_at": event.created_at,
        }

    # --------------------------------------------------------------- exports

    def current_version_snapshot(
        self, db: Session, report_id: uuid.UUID
    ) -> tuple[Report, ReportVersion]:
        """(report, version) for the export endpoints — snapshot is the input."""
        report = self._get_report(db, report_id)
        version = self._current_version(db, report.id)
        if version is None:
            raise ConflictError(
                "Report generation requires additional evidence — no snapshot "
                "exists yet. Generate the report first."
            )
        return report, version

    def evidence_bytes_for_image(
        self, db: Session, storage, evidence_detail: dict | None
    ) -> bytes | None:
        """Fetch image bytes from storage — processed derivative first.

        The storage key comes from the FROZEN manifest detail, and the
        StorageService interface is key-based (no user-controlled path is
        ever accepted here — the key was written by the intake layer).
        """
        if not evidence_detail:
            return None
        key = evidence_detail.get("processedStorageKey") or evidence_detail.get(
            "storageKey"
        )
        if not key or not isinstance(key, str):
            return None
        try:
            if not storage.exists(key=key):
                return None
            return storage.read(key=key)
        except Exception:  # noqa: BLE001 — a missing image is a fact, never fake
            return None
