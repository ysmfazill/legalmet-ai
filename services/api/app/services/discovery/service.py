"""UI-09 discovery service — global search, inspection history, product directory.

A pure READ layer over the EXISTING entities (Inspection, Product, Package,
Image, ExtractedField, ComplianceEvaluation/EvaluationFinding, ComplianceRule,
CitizenReport, Report, InspectionDecision, VerificationTask, AuditEvent, User).
No new tables, no duplicated entities, no writes.

Honesty contracts baked in (UI-09 §34):

* an inspection's "result" is the latest human decision when one exists, else
  the latest engine evaluation status, else NOT_EVALUATED — never a guess;
* a product's history is a HISTORICAL RECORD — it never claims current
  compliance;
* search results never expose citizen reporter names/contacts, internal
  notes, or storage keys (privacy §28).

All filtering and pagination happen server-side; the browser never loads the
database to search it (§29).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import FieldType, InspectionStatus
from app.models import (
    AuditEvent,
    CitizenReport,
    ComplianceEvaluation,
    EvaluationFinding,
    ExtractedField,
    Image,
    Inspection,
    InspectionDecision,
    Package,
    Product,
    Report,
    Rule,
    User,
    VerificationTask,
)
from app.schemas.discovery import (
    HistoryReportRef,
    InspectionHistoryItem,
    InspectionHistoryKpis,
    InspectionTimeline,
    ProductDeclaredField,
    ProductDetail,
    ProductEvidenceImage,
    ProductFindingHistory,
    ProductInspectionRef,
    ProductSummary,
    SearchComplaintHit,
    SearchEvidenceHit,
    SearchFindingHit,
    SearchInspectionHit,
    SearchProductHit,
    SearchReportHit,
    SearchResults,
    TimelineEvent,
)

# The source vocabulary (§7): complaint-originated vs direct inspection. The
# link is the existing CitizenReport.inspection_id — nothing new is stored.
SOURCE_COMPLAINT = "CITIZEN_COMPLAINT"
SOURCE_DIRECT = "DIRECT_INSPECTION"

# Terminal statuses — an inspection is "open" while not in one of these.
_CLOSED_STATUSES = (InspectionStatus.COMPLETED.value, InspectionStatus.ARCHIVED.value)

# Audit event type → (stage key, human label) for the inspection timeline.
_TIMELINE_STAGES: dict[str, tuple[str, str]] = {
    "INSPECTION_CREATED": ("INSPECTION_CREATED", "Inspection created"),
    "PACKAGE_CREATED": ("PACKAGE_CAPTURED", "Package captured"),
    "IMAGE_UPLOADED": ("PACKAGE_CAPTURED", "Package image captured"),
    "IMAGE_PREPARED": ("PACKAGE_CAPTURED", "Package image prepared"),
    "INSPECTION_READY": ("PACKAGE_CAPTURED", "Package ready for analysis"),
    "ANALYSIS_STARTED": ("OCR_PROCESSED", "Analysis started"),
    "PERCEPTION_STARTED": ("OCR_PROCESSED", "Perception started"),
    "PERCEPTION_COMPLETED": ("OCR_PROCESSED", "OCR processed"),
    "ANALYSIS_COMPLETED": ("FINDINGS_GENERATED", "Analysis completed"),
    "FINDING_CREATED": ("FINDINGS_GENERATED", "Finding generated"),
    "REVIEW_RECORDED": ("EVIDENCE_REVIEWED", "Evidence reviewed"),
    "INSPECTION_COMPLETED": ("INSPECTION_COMPLETED", "Inspection completed"),
    "INSPECTION_ASSIGNED": ("INSPECTION_ASSIGNED", "Inspector assigned"),
}

# Declaration fields shown on the product overview (only what the perception
# layer actually extracts — nothing invented).
_DECLARATION_FIELD_TYPES = (
    FieldType.BRAND_NAME.value,
    FieldType.MANUFACTURER_DETAILS.value,
    FieldType.PACKER_DETAILS.value,
    FieldType.IMPORTER_DETAILS.value,
    FieldType.MRP.value,
    FieldType.NET_QUANTITY.value,
    FieldType.COUNTRY_OF_ORIGIN.value,
    FieldType.CONSUMER_CARE.value,
    FieldType.GENERIC_NAME.value,
)


def _like(term: str) -> str:
    """Case-insensitive contains pattern (leading/trailing spaces trimmed)."""
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


def _is_uuid(term: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(term.strip())
    except (ValueError, AttributeError):
        return None


class DiscoveryService:
    # ------------------------------------------------------------ global search

    def search(self, db: Session, *, q: str, actor: User, limit: int = 5) -> SearchResults:
        """Server-side grouped search across the six spec categories.

        RBAC: any authenticated staff user (the same population that can
        already list inspections/complaints/reports). Citizen reporter PII
        (name/contact) is never selected (§28).
        """
        term = (q or "").strip()
        if len(term) < 2:
            return SearchResults(query=term or "")
        pattern = _like(term)
        term_uuid = _is_uuid(term)

        return SearchResults(
            query=term,
            inspections=self._search_inspections(db, pattern, term_uuid, limit),
            complaints=self._search_complaints(db, pattern, term_uuid, limit),
            products=self._search_products(db, pattern, limit),
            reports=self._search_reports(db, pattern, term_uuid, limit),
            findings=self._search_findings(db, pattern, term_uuid, limit),
            evidence=self._search_evidence(db, pattern, term_uuid, limit),
        )

    def _search_inspections(
        self, db: Session, pattern: str, term_uuid: uuid.UUID | None, limit: int
    ) -> list[SearchInspectionHit]:
        conditions = [
            func.lower(Inspection.reference_no).like(pattern, escape="\\"),
            func.lower(Product.name).like(pattern, escape="\\"),
        ]
        if term_uuid is not None:
            conditions.append(Inspection.id == term_uuid)
        rows = db.execute(
            select(Inspection)
            .join(Product, Inspection.product_id == Product.id, isouter=True)
            .where(or_(*conditions))
            .options(selectinload(Inspection.inspector))
            .order_by(Inspection.created_at.desc())
            .limit(limit)
        ).scalars().all()
        complaint_refs = self._complaint_refs_by_inspection(db, [i.id for i in rows])
        results = self._results_by_inspection(db, [i.id for i in rows])
        return [
            SearchInspectionHit(
                id=inspection.id,
                reference=inspection.reference_no,
                product_name=inspection.product.name if inspection.product else None,
                status=inspection.status,
                result=results.get(inspection.id, "NOT_EVALUATED"),
                inspector_name=(
                    inspection.inspector.full_name if inspection.inspector else None
                ),
                source=(
                    SOURCE_COMPLAINT
                    if inspection.id in complaint_refs
                    else SOURCE_DIRECT
                ),
                created_at=inspection.created_at,
            )
            for inspection in rows
        ]

    def _search_complaints(
        self, db: Session, pattern: str, term_uuid: uuid.UUID | None, limit: int
    ) -> list[SearchComplaintHit]:
        conditions = [
            func.lower(CitizenReport.reference).like(pattern, escape="\\"),
            func.lower(CitizenReport.product).like(pattern, escape="\\"),
            func.lower(CitizenReport.issue).like(pattern, escape="\\"),
            func.lower(func.coalesce(CitizenReport.shop, "")).like(pattern, escape="\\"),
            func.lower(func.coalesce(CitizenReport.location, "")).like(
                pattern, escape="\\"
            ),
        ]
        if term_uuid is not None:
            conditions.append(CitizenReport.id == term_uuid)
        rows = (
            db.execute(
                select(CitizenReport)
                .where(or_(*conditions))
                .order_by(CitizenReport.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        # Deliberately NOT selecting reporter_name / reporter_contact (§28).
        return [
            SearchComplaintHit(
                id=report.id,
                reference=report.reference,
                status=report.status,
                product=report.product,
                issue=report.issue[:120],
                location=report.location,
                inspection_id=report.inspection_id,
                created_at=report.created_at,
            )
            for report in rows
        ]

    def _search_products(self, db: Session, pattern: str, limit: int) -> list[SearchProductHit]:
        rows = (
            db.execute(
                select(Product)
                .where(
                    or_(
                        func.lower(Product.name).like(pattern, escape="\\"),
                        func.lower(Product.category).like(pattern, escape="\\"),
                        func.lower(func.coalesce(Product.gtin, "")).like(
                            pattern, escape="\\"
                        ),
                    )
                )
                .order_by(Product.name.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        if not rows:
            return []
        counts = self._inspection_counts_by_product(db, [p.id for p in rows])
        lasts = self._last_inspection_by_product(db, [p.id for p in rows])
        return [
            SearchProductHit(
                id=product.id,
                name=product.name,
                category=product.category,
                gtin=product.gtin,
                inspection_count=counts.get(product.id, 0),
                last_inspection_at=lasts.get(product.id),
            )
            for product in rows
        ]

    def _search_reports(
        self, db: Session, pattern: str, term_uuid: uuid.UUID | None, limit: int
    ) -> list[SearchReportHit]:
        conditions = [
            func.lower(Inspection.reference_no).like(pattern, escape="\\"),
            func.lower(func.coalesce(Product.name, "")).like(pattern, escape="\\"),
        ]
        if term_uuid is not None:
            conditions.append(Report.id == term_uuid)
        rows = (
            db.execute(
                select(Report)
                .join(Inspection, Report.inspection_id == Inspection.id)
                .join(Product, Inspection.product_id == Product.id, isouter=True)
                .where(or_(*conditions))
                .order_by(Report.updated_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            SearchReportHit(
                id=report.id,
                inspection_id=report.inspection_id,
                inspection_reference=report.inspection.reference_no,
                status=report.status,
                version=report.version,
                result=report.result,
            )
            for report in rows
        ]

    def _search_findings(
        self, db: Session, pattern: str, term_uuid: uuid.UUID | None, limit: int
    ) -> list[SearchFindingHit]:
        rows = db.execute(
            select(EvaluationFinding, ComplianceEvaluation, Inspection, Rule)
            .join(
                ComplianceEvaluation,
                EvaluationFinding.evaluation_id == ComplianceEvaluation.id,
            )
            .join(Inspection, ComplianceEvaluation.inspection_id == Inspection.id)
            .join(Rule, EvaluationFinding.requirement_id == Rule.id, isouter=True)
            .where(
                or_(
                    func.lower(func.coalesce(Rule.rule_code, "")).like(pattern, escape="\\"),
                    func.lower(func.coalesce(EvaluationFinding.detected_value, "")).like(
                        pattern, escape="\\"
                    ),
                    *(
                        [EvaluationFinding.id == term_uuid]
                        if term_uuid is not None
                        else []
                    ),
                )
            )
            .order_by(EvaluationFinding.created_at.desc())
            .limit(limit)
        ).all()
        return [
            SearchFindingHit(
                id=finding.id,
                inspection_id=inspection.id,
                inspection_reference=inspection.reference_no,
                rule_code=rule.rule_code if rule else None,
                status=finding.status,
                severity=finding.severity,
                detected_value=finding.detected_value,
                created_at=finding.created_at,
            )
            for finding, _evaluation, inspection, rule in rows
        ]

    def _search_evidence(
        self, db: Session, pattern: str, term_uuid: uuid.UUID | None, limit: int
    ) -> list[SearchEvidenceHit]:
        rows = db.execute(
            select(ExtractedField, Package, Inspection)
            .join(Package, ExtractedField.package_id == Package.id)
            .join(Inspection, Package.inspection_id == Inspection.id)
            .where(
                or_(
                    func.lower(ExtractedField.raw_text).like(pattern, escape="\\"),
                    func.lower(func.coalesce(ExtractedField.normalized_value, "")).like(
                        pattern, escape="\\"
                    ),
                    func.lower(ExtractedField.field_type).like(pattern, escape="\\"),
                    *(
                        [ExtractedField.id == term_uuid]
                        if term_uuid is not None
                        else []
                    ),
                )
            )
            .order_by(ExtractedField.created_at.desc())
            .limit(limit)
        ).all()
        return [
            SearchEvidenceHit(
                id=field.id,
                inspection_id=inspection.id,
                inspection_reference=inspection.reference_no,
                field_type=field.field_type,
                value=field.normalized_value or field.raw_text[:80],
                image_id=field.image_id,
                created_at=field.created_at,
            )
            for field, _package, inspection in rows
        ]

    # -------------------------------------------------------- inspection history

    def inspection_history(
        self,
        db: Session,
        *,
        q: str | None = None,
        status: str | None = None,
        result: str | None = None,
        source: str | None = None,
        inspector_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[InspectionHistoryItem], int, InspectionHistoryKpis]:
        """Filtered, paginated inspection history + KPIs — all server-side.

        The result filter needs the derived result per inspection (decision →
        evaluation → NOT_EVALUATED), so both maps are loaded once and the
        result filter + KPIs are computed in the service, never in the
        browser (§29).
        """
        base = select(Inspection).options(
            selectinload(Inspection.product),
            selectinload(Inspection.inspector),
        )
        term = (q or "").strip()
        if term:
            pattern = _like(term)
            term_uuid = _is_uuid(term)
            conditions = [
                func.lower(Inspection.reference_no).like(pattern, escape="\\"),
                func.lower(func.coalesce(Product.name, "")).like(pattern, escape="\\"),
            ]
            if term_uuid is not None:
                conditions.append(Inspection.id == term_uuid)
            base = base.join(Product, Inspection.product_id == Product.id, isouter=True).where(
                or_(*conditions)
            )
        if status:
            base = base.where(Inspection.status == status)
        if inspector_id is not None:
            base = base.where(Inspection.inspector_id == inspector_id)
        if product_id is not None:
            base = base.where(Inspection.product_id == product_id)
        if date_from is not None:
            base = base.where(Inspection.created_at >= date_from)
        if date_to is not None:
            base = base.where(Inspection.created_at <= date_to)

        all_rows = list(
            db.execute(base.order_by(Inspection.created_at.desc())).scalars().all()
        )

        # Derived context, loaded once for the candidate set.
        complaint_refs = self._complaint_refs_by_inspection(db, [i.id for i in all_rows])
        if source:
            wants_complaint = source == SOURCE_COMPLAINT
            all_rows = [
                i
                for i in all_rows
                # A DIRECT filter keeps only unlinked inspections, and vice
                # versa — the link is the existing CitizenReport FK.
                if (i.id in complaint_refs) == wants_complaint
            ]
        results = self._results_by_inspection(db, [i.id for i in all_rows])
        if result:
            all_rows = [i for i in all_rows if results.get(i.id) == result]

        reports = self._reports_by_inspection(db, [i.id for i in all_rows])
        page_rows = all_rows[offset : offset + limit]
        # Real establishment (complaint shop) + evidence counts for the page.
        shops = self._complaint_shops_by_inspection(db, [i.id for i in page_rows])
        image_counts = self._image_counts_by_inspection(db, [i.id for i in page_rows])

        items = [
            self._history_item(
                inspection,
                results.get(inspection.id, "NOT_EVALUATED"),
                reports.get(inspection.id),
                complaint_refs.get(inspection.id),
                establishment=shops.get(inspection.id),
                image_count=image_counts.get(inspection.id, 0),
            )
            for inspection in page_rows
        ]

        kpis = InspectionHistoryKpis(
            total=len(all_rows),
            compliant=sum(1 for i in all_rows if results.get(i.id) == "COMPLIANT"),
            non_compliant=sum(
                1 for i in all_rows if results.get(i.id) == "NON_COMPLIANT"
            ),
            review_required=sum(
                1 for i in all_rows if results.get(i.id) == "REVIEW_REQUIRED"
            ),
            open=sum(1 for i in all_rows if i.status not in _CLOSED_STATUSES),
        )
        return items, len(all_rows), kpis

    def inspection_timeline(self, db: Session, inspection_id: uuid.UUID) -> InspectionTimeline:
        """The real recorded chain for one inspection (§8) — audit events plus
        decision/evaluation/report facts. Events that never happened are
        simply absent; nothing is fabricated."""
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Inspection not found: {inspection_id}")

        events: list[TimelineEvent] = []
        actors = self._actor_names(db)

        # Inspection creation — the anchor event. Every inspection has one.
        events.append(
            TimelineEvent(
                stage="INSPECTION_CREATED",
                label="Inspection created",
                event_type="INSPECTION_CREATED",
                at=inspection.created_at,
                actor_name=actors.get(inspection.inspector_id),
            )
        )

        # Audit events for this inspection, deduplicated per stage so a
        # re-analysis does not paint the timeline three times.
        seen_stages: set[str] = set()
        audit_rows = (
            db.execute(
                select(AuditEvent)
                .where(
                    or_(
                        AuditEvent.inspection_id == inspection_id,
                        (AuditEvent.entity_id == inspection_id)
                        & (AuditEvent.entity_type == "inspection"),
                    )
                )
                .order_by(AuditEvent.created_at.asc())
            )
            .scalars()
            .all()
        )
        for event in audit_rows:
            mapping = _TIMELINE_STAGES.get(event.event_type)
            if mapping is None:
                continue
            stage, label = mapping
            if stage in seen_stages:
                continue
            seen_stages.add(stage)
            events.append(
                TimelineEvent(
                    stage=stage,
                    label=label,
                    event_type=event.event_type,
                    at=event.created_at,
                    actor_name=actors.get(event.actor_id),
                )
            )

        # Engine evaluation (deterministic, from the evaluation row itself).
        evaluation = self._latest_evaluation(db, inspection_id)
        if evaluation is not None and evaluation.completed_at is not None:
            events.append(
                TimelineEvent(
                    stage="FINDINGS_GENERATED",
                    label="Findings generated (engine evaluation)",
                    at=evaluation.completed_at,
                    detail=f"Engine {evaluation.engine_version} · "
                    f"{(evaluation.summary or {}).get('totalFindings', 0)} findings",
                )
            )

        # Human review of engine findings.
        review_row = db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.inspection_id == inspection_id,
                AuditEvent.event_type == "REVIEW_RECORDED",
            )
            .order_by(AuditEvent.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        if review_row is not None:
            events.append(
                TimelineEvent(
                    stage="EVIDENCE_REVIEWED",
                    label="Evidence reviewed",
                    event_type="REVIEW_RECORDED",
                    at=review_row.created_at,
                    actor_name=actors.get(review_row.actor_id),
                )
            )

        # Physical verification — the first recorded verification result.
        verification_first = db.execute(
            select(VerificationTask)
            .where(VerificationTask.inspection_id == inspection_id)
            .order_by(VerificationTask.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        if verification_first is not None:
            events.append(
                TimelineEvent(
                    stage="PHYSICAL_VERIFICATION",
                    label="Physical verification planned",
                    at=verification_first.created_at,
                    detail=f"{verification_first.task_type} task",
                )
            )

        # The final human decision.
        decision = self._latest_decision(db, inspection_id)
        if decision is not None:
            decider = actors.get(decision.decided_by)
            events.append(
                TimelineEvent(
                    stage="DECISION",
                    label="Decision recorded",
                    at=decision.decided_at,
                    actor_name=decider,
                    detail=decision.decision,
                    decision=decision.decision,
                )
            )

        # Report generation + finalization.
        report = db.execute(
            select(Report)
            .where(Report.inspection_id == inspection_id)
            .order_by(Report.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        if report is not None and report.generated_at is not None:
            events.append(
                TimelineEvent(
                    stage="REPORT_GENERATED",
                    label="Report generated",
                    at=report.generated_at,
                    report_id=report.id,
                    detail=f"v{report.version}",
                )
            )
            if report.finalized_at is not None:
                events.append(
                    TimelineEvent(
                        stage="REPORT_FINALIZED",
                        label="Report finalized",
                        at=report.finalized_at,
                        report_id=report.id,
                        actor_name=actors.get(report.finalized_by),
                    )
                )

        events.sort(key=lambda e: e.at)
        return InspectionTimeline(
            inspection_id=inspection.id,
            reference=inspection.reference_no,
            events=events,
        )

    # ------------------------------------------------------------ product directory

    def product_list(
        self, db: Session, *, q: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[ProductSummary], int]:
        term = (q or "").strip()
        base = select(Product)
        if term:
            pattern = _like(term)
            base = base.where(
                or_(
                    func.lower(Product.name).like(pattern, escape="\\"),
                    func.lower(Product.category).like(pattern, escape="\\"),
                    func.lower(func.coalesce(Product.gtin, "")).like(
                        pattern, escape="\\"
                    ),
                )
            )
        rows = list(
            db.execute(base.order_by(Product.name.asc())).scalars().all()
        )
        if not rows:
            return [], 0
        ids = [p.id for p in rows]
        counts = self._inspection_counts_by_product(db, ids)
        lasts = self._last_inspection_by_product(db, ids)
        findings = self._finding_counts_by_product(db, ids)
        results = self._latest_results_by_product(db, ids)
        summaries = [
            ProductSummary(
                id=product.id,
                name=product.name,
                category=product.category,
                gtin=product.gtin,
                inspection_count=counts.get(product.id, 0),
                finding_count=findings.get(product.id, 0),
                last_inspection_at=lasts.get(product.id),
                latest_result=results.get(product.id, "NOT_EVALUATED"),
            )
            for product in rows
        ]
        return summaries[offset : offset + limit], len(summaries)

    def product_detail(self, db: Session, product_id: uuid.UUID) -> ProductDetail:
        from app.core.errors import NotFoundError

        product = db.get(Product, product_id)
        if product is None:
            raise NotFoundError(f"Product not found: {product_id}")

        inspections = list(
            db.execute(
                select(Inspection)
                .where(Inspection.product_id == product_id)
                .options(selectinload(Inspection.inspector))
                .order_by(Inspection.created_at.desc())
            ).scalars().all()
        )
        inspection_ids = [i.id for i in inspections]
        results = self._results_by_inspection(db, inspection_ids)
        reports = self._reports_by_inspection(db, inspection_ids)
        complaint_refs = self._complaint_refs_by_inspection(db, inspection_ids)

        inspection_refs = [
            ProductInspectionRef(
                id=inspection.id,
                reference=inspection.reference_no,
                created_at=inspection.created_at,
                inspector_name=(
                    inspection.inspector.full_name if inspection.inspector else None
                ),
                result=results.get(inspection.id, "NOT_EVALUATED"),
                report=(
                    HistoryReportRef(
                        id=reports[inspection.id].id,
                        status=reports[inspection.id].status,
                        version=reports[inspection.id].version,
                    )
                    if inspection.id in reports
                    else None
                ),
                source=(
                    SOURCE_COMPLAINT
                    if inspection.id in complaint_refs
                    else SOURCE_DIRECT
                ),
            )
            for inspection in inspections
        ]

        declared = self._latest_declared_fields(db, product_id)
        findings_history = self._product_findings_history(db, inspection_ids)
        gallery = self._product_evidence_gallery(db, inspection_ids)
        findings_count = self._finding_counts_by_product(db, [product_id]).get(
            product_id, 0
        )
        last_inspection_at = inspections[0].created_at if inspections else None

        return ProductDetail(
            id=product.id,
            name=product.name,
            category=product.category,
            gtin=product.gtin,
            inspection_count=len(inspections),
            finding_count=findings_count,
            last_inspection_at=last_inspection_at,
            latest_result=results.get(inspections[0].id, "NOT_EVALUATED")
            if inspections
            else "NOT_EVALUATED",
            declared_fields=declared,
            inspections=inspection_refs,
            findings_history=findings_history,
            evidence_gallery=gallery,
        )

    # ------------------------------------------------------------- shared reads

    def _history_item(
        self,
        inspection: Inspection,
        result: str,
        report: Report | None,
        complaint_reference: str | None,
        *,
        establishment: str | None = None,
        image_count: int = 0,
    ) -> InspectionHistoryItem:
        return InspectionHistoryItem(
            id=inspection.id,
            reference=inspection.reference_no,
            created_at=inspection.created_at,
            product_name=inspection.product.name if inspection.product else None,
            product_category=inspection.product.category if inspection.product else None,
            inspector_name=(
                inspection.inspector.full_name if inspection.inspector else None
            ),
            establishment=establishment,
            source=SOURCE_COMPLAINT if complaint_reference else SOURCE_DIRECT,
            source_complaint_reference=complaint_reference,
            status=inspection.status,
            result=result,
            image_count=image_count,
            report=HistoryReportRef(
                id=report.id, status=report.status, version=report.version
            )
            if report
            else None,
        )

    def _results_by_inspection(self, db: Session, inspection_ids: list) -> dict:
        """Latest decision → else latest evaluation status → NOT_EVALUATED."""
        results: dict = {}
        if not inspection_ids:
            return results
        decisions = (
            db.execute(
                select(InspectionDecision)
                .where(InspectionDecision.inspection_id.in_(inspection_ids))
                .order_by(InspectionDecision.created_at.asc())
            )
            .scalars()
            .all()
        )
        for decision in decisions:  # asc order: the last write wins
            results[decision.inspection_id] = decision.decision
        evaluations = (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id.in_(inspection_ids))
                .order_by(ComplianceEvaluation.created_at.asc())
            )
            .scalars()
            .all()
        )
        for evaluation in evaluations:
            # Only fill inspections with no human decision — the human verdict
            # always outranks the engine's REVIEW_REQUIRED.
            if evaluation.inspection_id not in results:
                results[evaluation.inspection_id] = evaluation.status
        return results

    def _reports_by_inspection(self, db: Session, inspection_ids: list) -> dict:
        if not inspection_ids:
            return {}
        reports = (
            db.execute(
                select(Report)
                .where(Report.inspection_id.in_(inspection_ids))
                .order_by(Report.created_at.asc())
            )
            .scalars()
            .all()
        )
        return {report.inspection_id: report for report in reports}

    def _complaint_refs_by_inspection(self, db: Session, inspection_ids: list) -> dict:
        if not inspection_ids:
            return {}
        rows = db.execute(
            select(CitizenReport.inspection_id, CitizenReport.reference).where(
                CitizenReport.inspection_id.in_(inspection_ids)
            )
        ).all()
        return {inspection_id: reference for inspection_id, reference in rows}

    def _complaint_shops_by_inspection(self, db: Session, inspection_ids: list) -> dict:
        """Reported shop/establishment per linked inspection (§7). Real values
        from the citizen complaint; direct inspections stay absent."""
        if not inspection_ids:
            return {}
        rows = db.execute(
            select(CitizenReport.inspection_id, CitizenReport.shop).where(
                CitizenReport.inspection_id.in_(inspection_ids)
            )
        ).all()
        return {inspection_id: shop for inspection_id, shop in rows if shop}

    def _image_counts_by_inspection(self, db: Session, inspection_ids: list) -> dict:
        """Captured package images per inspection — the real evidence count.

        Images attach to their Package (Image.package_id), and packages belong
        to inspections (Package.inspection_id), so count through that join.
        """
        if not inspection_ids:
            return {}
        rows = db.execute(
            select(Package.inspection_id, func.count(Image.id))
            .join(Image, Image.package_id == Package.id)
            .where(Package.inspection_id.in_(inspection_ids))
            .group_by(Package.inspection_id)
        ).all()
        return {inspection_id: count for inspection_id, count in rows}

    def _inspection_counts_by_product(self, db: Session, product_ids: list) -> dict:
        if not product_ids:
            return {}
        rows = db.execute(
            select(Inspection.product_id, func.count())
            .where(Inspection.product_id.in_(product_ids))
            .group_by(Inspection.product_id)
        ).all()
        return {product_id: count for product_id, count in rows}

    def _last_inspection_by_product(self, db: Session, product_ids: list) -> dict:
        if not product_ids:
            return {}
        rows = db.execute(
            select(Inspection.product_id, func.max(Inspection.created_at))
            .where(Inspection.product_id.in_(product_ids))
            .group_by(Inspection.product_id)
        ).all()
        return {product_id: last for product_id, last in rows}

    def _finding_counts_by_product(self, db: Session, product_ids: list) -> dict:
        """Engine findings per product (via the product's evaluations)."""
        if not product_ids:
            return {}
        rows = db.execute(
            select(Inspection.product_id, func.count(EvaluationFinding.id))
            .select_from(Inspection)
            .join(
                ComplianceEvaluation,
                ComplianceEvaluation.inspection_id == Inspection.id,
            )
            .join(
                EvaluationFinding,
                EvaluationFinding.evaluation_id == ComplianceEvaluation.id,
            )
            .where(Inspection.product_id.in_(product_ids))
            .group_by(Inspection.product_id)
        ).all()
        return {product_id: count for product_id, count in rows}

    def _latest_results_by_product(self, db: Session, product_ids: list) -> dict:
        """Result of each product's most recent inspection."""
        if not product_ids:
            return {}
        latest = (
            db.execute(
                select(Inspection.product_id, Inspection.id, Inspection.created_at)
                .where(Inspection.product_id.in_(product_ids))
                .order_by(Inspection.product_id, Inspection.created_at.desc())
            )
            .all()
        )
        latest_by_product: dict = {}
        for product_id, inspection_id, _created in latest:
            # ordered desc per product: the first row per product is latest
            latest_by_product.setdefault(product_id, inspection_id)
        if not latest_by_product:
            return {}
        results = self._results_by_inspection(db, list(latest_by_product.values()))
        return {
            product_id: results.get(inspection_id, "NOT_EVALUATED")
            for product_id, inspection_id in latest_by_product.items()
        }

    def _latest_declared_fields(
        self, db: Session, product_id: uuid.UUID
    ) -> list[ProductDeclaredField]:
        """The newest detection per declaration field type — what the package
        ACTUALLY declared, as extracted (never invented)."""
        rows = db.execute(
            select(ExtractedField, Inspection)
            .join(Package, ExtractedField.package_id == Package.id)
            .join(Inspection, Package.inspection_id == Inspection.id)
            .where(
                Inspection.product_id == product_id,
                ExtractedField.field_type.in_(_DECLARATION_FIELD_TYPES),
            )
            .order_by(ExtractedField.created_at.desc())
        ).all()
        latest: dict[str, tuple] = {}
        for field, inspection in rows:
            if field.field_type not in latest:  # desc order keeps the newest
                latest[field.field_type] = (field, inspection)
        return [
            ProductDeclaredField(
                field_type=field.field_type,
                raw_text=field.raw_text,
                normalized_value=field.normalized_value,
                unit=field.unit,
                inspection_id=inspection.id,
                inspection_reference=inspection.reference_no,
                detected_at=field.created_at,
            )
            for field, inspection in latest.values()
        ]

    def _product_findings_history(
        self, db: Session, inspection_ids: list
    ) -> list[ProductFindingHistory]:
        """Recurring engine findings grouped by rule — a historical record."""
        if not inspection_ids:
            return []
        rows = db.execute(
            select(
                EvaluationFinding,
                ComplianceEvaluation.inspection_id.label("inspection_id"),
                Rule.rule_code,
                Rule.title,
            )
            .join(
                ComplianceEvaluation,
                EvaluationFinding.evaluation_id == ComplianceEvaluation.id,
            )
            .join(Rule, EvaluationFinding.requirement_id == Rule.id, isouter=True)
            .where(ComplianceEvaluation.inspection_id.in_(inspection_ids))
        ).all()
        grouped: dict[str, dict] = {}
        for finding, inspection_id, rule_code, title in rows:
            key = rule_code or f"field:{finding.extracted_field_id or finding.id}"
            entry = grouped.setdefault(
                key,
                {
                    "rule_code": rule_code,
                    "label": title or rule_code or "Requirement",
                    "inspections": set(),
                    "count": 0,
                    "review": 0,
                    "non_compliant": 0,
                },
            )
            entry["inspections"].add(inspection_id)
            entry["count"] += 1
            if finding.status == "REVIEW_REQUIRED":
                entry["review"] += 1
            if finding.status == "NON_COMPLIANT":
                entry["non_compliant"] += 1
        return [
            ProductFindingHistory(
                rule_code=entry["rule_code"],
                label=entry["label"],
                occurrence_count=entry["count"],
                inspection_count=len(entry["inspections"]),
                review_required_count=entry["review"],
                non_compliant_count=entry["non_compliant"],
            )
            for entry in sorted(
                grouped.values(), key=lambda e: e["count"], reverse=True
            )
        ]

    def _product_evidence_gallery(
        self, db: Session, inspection_ids: list
    ) -> list[ProductEvidenceImage]:
        if not inspection_ids:
            return []
        rows = db.execute(
            select(Image, Inspection)
            .join(Package, Image.package_id == Package.id)
            .join(Inspection, Package.inspection_id == Inspection.id)
            .where(Inspection.id.in_(inspection_ids))
            .order_by(Inspection.created_at.desc(), Image.created_at.asc())
        ).all()
        gallery: list[ProductEvidenceImage] = []
        for image, inspection in rows:
            field_types = [
                ft
                for (ft,) in db.execute(
                    select(ExtractedField.field_type)
                    .where(ExtractedField.image_id == image.id)
                    .distinct()
                ).all()
            ]
            gallery.append(
                ProductEvidenceImage(
                    id=image.id,
                    inspection_id=inspection.id,
                    inspection_reference=inspection.reference_no,
                    image_type=image.image_type,
                    original_filename=image.original_filename,
                    created_at=image.created_at,
                    field_types=field_types,
                )
            )
        return gallery

    def _latest_evaluation(
        self, db: Session, inspection_id: uuid.UUID
    ) -> ComplianceEvaluation | None:
        return (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id == inspection_id)
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

    def _actor_names(self, db: Session) -> dict:
        rows = db.execute(select(User.id, User.full_name)).all()
        return {user_id: name for user_id, name in rows}
