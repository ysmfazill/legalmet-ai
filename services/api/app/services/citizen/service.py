"""Citizen Mode + complaint application service (UI-02, extended UI-03).

Anonymous SCAN → screen → REPORT orchestration, plus the department complaint
lifecycle. The anonymous half is a thin, minimal adapter over the SAME real
services the inspector pipeline uses:

* quality  → the real Pillow usability analyzer (deterministic pixels math)
* ocr      → the real OCR service (PaddleOCR when enabled)
* extractor → the real deterministic declaration-field extractor

The department half (UI-03) advances complaints through a controlled state
machine, records persistent history + audit events with the acting user, and
creates real linked inspections through the existing InspectionService.

What it deliberately does NOT do:

* No rule-engine evaluation. A citizen scan screens declarations for
  readability/presence only; regulatory evaluation needs an inspector
  context (category, rules in force) and stays inside the inspection flow.
* No compliance verdict, ever. The outcome vocabulary cannot express one.
* No auto-created inspection from a report — conversion is a human
  department decision (the CREATE_INSPECTION transition).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image as PILImage
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    AuditEventType,
    ExtractionStatus,
    ImageQualityGrade,
    ImageQualityStatus,
)
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import CitizenReport, CitizenReportEvent, CitizenScan, Inspection, User
from app.schemas.citizen import (
    CitizenDetectedField,
    CitizenQualitySummary,
    CitizenReportCreate,
    CitizenReportOut,
    CitizenScanOut,
    ComplaintAction,
    ComplaintStatsOut,
    ComplaintSummaryOut,
)
from app.schemas.inspection import CreateInspectionRequest
from app.services.interfaces import ImageQualityAnalyzer, OCRService
from app.services.perception.extract import DeterministicFieldExtractor
from app.services.registry import Services

# Plain-language labels for the citizen UI (field types are inspector jargon).
_FIELD_LABELS: dict[str, str] = {
    "PRODUCT_NAME": "Product name",
    "BRAND_NAME": "Brand",
    "MRP": "Maximum Retail Price (MRP)",
    "NET_QUANTITY": "Net quantity / weight",
    "GENERIC_NAME": "Generic / commodity name",
    "MANUFACTURER_DETAILS": "Manufacturer",
    "PACKER_DETAILS": "Packer",
    "IMPORTER_DETAILS": "Importer",
    "COUNTRY_OF_ORIGIN": "Country of origin",
    "ADDRESS": "Address",
    "DATE_OF_MANUFACTURE": "Date of manufacture",
    "DATE_OF_PACKING": "Date of packing",
    "BEST_BEFORE": "Best before",
    "EXPIRY_DATE": "Expiry date",
    "CONSUMER_CARE": "Consumer care details",
    "BATCH_NUMBER": "Batch / lot number",
    "DIMENSIONS": "Dimensions",
    "UNIT_SALE_PRICE": "Unit sale price",
}

# Readability grades that mean "not worth reading with OCR".
_UNUSABLE_GRADES = {ImageQualityGrade.REJECTED.value, ImageQualityGrade.POOR.value}
_DEGRADED_GRADES = {ImageQualityGrade.ACCEPTABLE.value}

# Core declarations a pre-packaged commodity is expected to carry (the same
# subset the anonymous screening policy checks).
_EXPECTED_DECLARATIONS = {"MRP", "NET_QUANTITY", "MANUFACTURER_DETAILS", "DATE_OF_MANUFACTURE"}

# ---------------------------------------------------------------------------
# UI-03 — the complaint state machine. THE single transition table: the
# service is the only writer of CitizenReport.status, and only along these
# edges. Anything not listed here is a 422, never a silent rewrite.
# ---------------------------------------------------------------------------
_TRANSITIONS: dict[ComplaintAction, dict[str, str]] = {
    ComplaintAction.START_REVIEW: {"SUBMITTED": "UNDER_REVIEW"},
    ComplaintAction.ACCEPT: {"UNDER_REVIEW": "ACCEPTED"},
    ComplaintAction.REJECT: {"UNDER_REVIEW": "REJECTED"},
    ComplaintAction.REQUEST_INFORMATION: {"UNDER_REVIEW": "REQUEST_INFORMATION"},
    ComplaintAction.ASSIGN: {"ACCEPTED": "ASSIGNED"},
    ComplaintAction.CREATE_INSPECTION: {
        "ACCEPTED": "INSPECTION_SCHEDULED",
        "ASSIGNED": "INSPECTION_SCHEDULED",
    },
    ComplaintAction.COMPLETE_INSPECTION: {"INSPECTION_SCHEDULED": "INSPECTION_COMPLETED"},
    ComplaintAction.RECORD_ACTION: {"INSPECTION_COMPLETED": "ACTION_TAKEN"},
    ComplaintAction.CLOSE: {
        "INSPECTION_COMPLETED": "CLOSED",
        "ACTION_TAKEN": "CLOSED",
    },
}

# Terminal states: no outgoing department transitions.
_TERMINAL_STATUSES = {"REJECTED", "CLOSED"}

# UI-04 — an open complaint older than this is flagged as needing attention.
STALE_COMPLAINT_DAYS = 14

# ---------------------------------------------------------------------------
# UI-04 — deterministic, explainable EVIDENCE COMPLETENESS (department
# dashboard). Each factor is a simple presence check over data the complaint
# row actually stores. The score says how complete the recorded evidence is —
# it is explicitly NOT a probability of violation, and it never will be.
# ---------------------------------------------------------------------------
EVIDENCE_FACTORS: tuple[tuple[str, int], ...] = (
    ("package image", 25),
    ("OCR extraction", 15),
    ("product details", 10),
    ("citizen description", 10),
    ("shop name", 10),
    ("issue location", 10),
    ("citizen follow-up response", 10),
    ("submission timestamp", 10),
)


def complaint_evidence_completeness(report: CitizenReport) -> int:
    """0–100 evidence-completeness score (fixed presence rules, see above)."""
    evidence = report.evidence or {}
    score = 0
    if evidence.get("imageUrl"):
        score += 25
    if evidence.get("detectedFields"):
        score += 15
    if (report.product or "").strip():
        score += 10
    if (report.description or "").strip():
        score += 10
    if (report.shop or "").strip():
        score += 10
    if (report.location or "").strip():
        score += 10
    if evidence.get("citizenFollowUps"):
        score += 10
    if report.created_at is not None:
        score += 10
    return score


def evidence_band(score: int) -> str:
    """COMPLETE ≥ 80, PARTIAL 50–79, MINIMAL < 50."""
    if score >= 80:
        return "COMPLETE"
    if score >= 50:
        return "PARTIAL"
    return "MINIMAL"


def effective_priority(report: CitizenReport) -> tuple[str | None, str | None]:
    """The complaint's triage priority: the OFFICIAL decision when the
    department set one, otherwise the deterministic SYSTEM SCREENING value.
    Returns (priority, source) — never a legal determination."""
    if report.official_priority:
        return report.official_priority, "OFFICIAL_DECISION"
    return report.screening_risk, "SYSTEM_SCREENING"

# Every action's audit event (department actor recorded; the citizen respond
# path has its own anonymous event).
_ACTION_AUDIT: dict[ComplaintAction, AuditEventType] = {
    ComplaintAction.START_REVIEW: AuditEventType.COMPLAINT_REVIEW_STARTED,
    ComplaintAction.ACCEPT: AuditEventType.COMPLAINT_ACCEPTED,
    ComplaintAction.REJECT: AuditEventType.COMPLAINT_REJECTED,
    ComplaintAction.REQUEST_INFORMATION: AuditEventType.COMPLAINT_INFO_REQUESTED,
    ComplaintAction.ASSIGN: AuditEventType.COMPLAINT_ASSIGNED,
    ComplaintAction.CREATE_INSPECTION: AuditEventType.COMPLAINT_INSPECTION_CREATED,
    ComplaintAction.COMPLETE_INSPECTION: AuditEventType.COMPLAINT_INSPECTION_COMPLETED,
    ComplaintAction.RECORD_ACTION: AuditEventType.COMPLAINT_ACTION_TAKEN,
    ComplaintAction.CLOSE: AuditEventType.COMPLAINT_CLOSED,
}

# Canonical display order the timeline uses for PENDING steps (completed
# steps come from real events only).
_TIMELINE_ORDER = [
    "SUBMITTED",
    "REVIEW_STARTED",
    "ACCEPTED",
    "INSPECTION_CREATED",
    "INSPECTION_COMPLETED",
    "CLOSED",
]


def _scan_reference() -> str:
    return f"CS-{uuid.uuid4().hex[:10].upper()}"


def _report_reference() -> str:
    # UI-03: the complaint reference shown to citizen and department alike.
    return f"CMP-{uuid.uuid4().hex[:10].upper()}"


def _screening_risk(scan: CitizenScan) -> str:
    """Deterministic SYSTEM SCREENING priority from the scan's real evidence.

    A fixed, explainable rule over what the pipeline actually extracted —
    never an AI score, never an official decision:

    * HIGH   — two or more expected declarations missing
    * MEDIUM — exactly one expected declaration missing, or the scan could
               not be read confidently (REVIEW_REQUIRED/INSUFFICIENT evidence)
    * LOW    — everything expected was read with adequate confidence
    """
    detected = {
        f.get("field_type")
        for f in (scan.detected_fields or [])
        if f.get("status") != "NOT_EXTRACTED"
    }
    missing = _EXPECTED_DECLARATIONS - detected
    if len(missing) >= 2:
        return "HIGH"
    if len(missing) == 1 or scan.outcome in ("REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"):
        return "MEDIUM"
    return "LOW"


class CitizenService:
    def __init__(
        self,
        *,
        services: Services,
    ) -> None:
        # Reuse the exact instances wired in the registry — never rebuild.
        # perception_ocr is the REAL engine (PaddleOCR when enabled) — the
        # demo mock OCR is never used for citizen scans.
        self._services = services
        self._quality: ImageQualityAnalyzer = services.intake_quality
        self._ocr: OCRService = services.perception_ocr
        self._extractor: DeterministicFieldExtractor = services.field_extractor
        self._storage = services.storage
        self._audit = services.audit
        # UI-03: complaint → real inspection creation goes through the SAME
        # InspectionService the inspector intake uses (never a second path).
        self._inspections = services.inspection

    # --- screening ---------------------------------------------------------

    def screen_image(
        self,
        db: Session,
        *,
        filename: str,
        declared_mime: str | None,
        data: bytes,
        capture_source: str | None = None,
    ) -> CitizenScan:
        """Run the REAL quality gate + OCR + extraction on an anonymous image."""
        if not data:
            raise ValidationError("No image data received.")
        sniffed = _sniff(
            data=data,
            filename=filename,
            declared_mime=declared_mime,
            max_size=self._services.settings.max_image_size,
        )

        reference = _scan_reference()
        storage_key = f"citizen/{reference.lower()}/{sniffed.ext}"

        # ---- REAL usability gate (same analyzer as intake) ----
        quality = self._quality.analyze(
            image_bytes=data,
            width=None,
            height=None,
            mime_type=sniffed.mime,
            seed=f"citizen-{reference.lower()}",
        )
        readable = (
            quality.grade is not None
            and quality.grade.value not in _UNUSABLE_GRADES
            and quality.status not in (ImageQualityStatus.INSUFFICIENT, ImageQualityStatus.UNKNOWN)
        )
        self._storage.save(key=storage_key, data=data, content_type=sniffed.mime)

        detected: list[CitizenDetectedField] = []
        ocr_text: list[dict] = []
        ocr_provider: str | None = None
        ocr_model: str | None = None
        outcome: str
        rationale: str | None = None

        if not readable:
            # Do NOT silently proceed after a real quality failure (UI-02 rule).
            outcome = "IMAGE_UNREADABLE"
            rationale = (
                "The photo is too blurry, dark or low-resolution for the system to "
                "read the label reliably. Please retake it with the label in focus."
            )
        else:
            # ---- REAL OCR (fatal → honest failure surfaced to the citizen) ----
            ocr_result = self._ocr.extract_text(
                image_bytes=data, storage_key=storage_key, seed=storage_key
            )
            ocr_provider = ocr_result.descriptor.provider
            ocr_model = f"{ocr_result.descriptor.name}/{ocr_result.descriptor.version}"
            ocr_text = [
                {
                    "text": line.text,
                    "confidence": round(line.confidence, 3),
                    "bbox": line.bbox.as_dict(),
                }
                for line in ocr_result.lines
            ]

            # ---- REAL deterministic declaration extraction ----
            candidates = self._extractor.extract(ocr=ocr_result)
            for candidate in candidates:
                if candidate.status == ExtractionStatus.NOT_EXTRACTED:
                    continue
                detected.append(
                    CitizenDetectedField(
                        field_type=candidate.field_type,
                        label=_FIELD_LABELS.get(candidate.field_type.value, candidate.field_type.value),
                        raw_text=candidate.raw_text,
                        normalized_value=candidate.normalized_value,
                        confidence=round(candidate.confidence, 3),
                        status=candidate.status,
                    )
                )

            detected, outcome, rationale = self._screen(detected, quality, ocr_result.mean_confidence)

        scan = CitizenScan(
            reference=reference,
            storage_key=storage_key,
            filename=filename or "package.jpg",
            quality_grade=quality.grade.value if quality.grade else None,
            quality_score=quality.score,
            quality_status=quality.status.value,
            quality_metrics=quality.metrics or None,
            outcome=outcome,
            outcome_rationale=rationale,
            detected_fields=[f.model_dump(by_alias=False) for f in detected],
            ocr_text=ocr_text or None,
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            is_live=True,
        )
        db.add(scan)
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.CITIZEN_SCAN_COMPLETED,
            entity_type="citizen_scan",
            entity_id=scan.id,
            payload={"reference": reference, "outcome": outcome},
        )
        db.commit()
        db.refresh(scan)
        return scan

    @staticmethod
    def _screen(
        detected: list[CitizenDetectedField], quality, mean_confidence: float
    ) -> tuple[list[CitizenDetectedField], str, str | None]:
        """Deterministic screening policy — presence/readability only.

        Policy (deliberately conservative, never a legal claim):
        * no usable OCR lines at all          -> INSUFFICIENT_EVIDENCE
        * any field only REVIEW_REQUIRED (low OCR confidence) -> REVIEW_REQUIRED
        * zero declarations found             -> INSUFFICIENT_EVIDENCE
        * any *required* declaration missing  -> POSSIBLE_ISSUE (missing info)
        * everything present & confident      -> NO_OBVIOUS_ISSUE
        """
        if not detected:
            return detected, "INSUFFICIENT_EVIDENCE", (
                "No declaration could be read from this image. Try a closer, "
                "steadier photo of the label area."
            )

        review_required = [f for f in detected if f.status == ExtractionStatus.REVIEW_REQUIRED]
        if review_required and len(review_required) == len(detected):
            return detected, "REVIEW_REQUIRED", (
                "The system found label information but could not read it "
                "confidently enough to screen. A steadier, brighter photo usually helps."
            )

        # Core declarations a pre-packaged commodity is expected to carry
        # (subset used for screening; the inspector engine checks the full set).
        _EXPECTED = {"MRP", "NET_QUANTITY", "MANUFACTURER_DETAILS", "DATE_OF_MANUFACTURE"}
        present = {f.field_type.value for f in detected}
        missing = _EXPECTED - present
        if missing:
            labels = ", ".join(sorted(_FIELD_LABELS.get(m, m) for m in missing))
            return detected, "POSSIBLE_ISSUE", (
                f"Some expected declarations were not found on the label: {labels}. "
                "This may mean they are missing, or the photo does not cover them."
            )

        return detected, "NO_OBVIOUS_ISSUE", (
            "We read the expected declarations from this image. This is an "
            "automated screening result, not an official determination."
        )

    # --- read ---------------------------------------------------------------

    def get_scan(self, db: Session, scan_id: uuid.UUID) -> CitizenScan:
        scan = db.get(CitizenScan, scan_id)
        if scan is None:
            raise NotFoundError("Scan not found.")
        return scan

    def scan_out(self, scan: CitizenScan) -> CitizenScanOut:
        readable = (
            scan.quality_grade is not None
            and scan.quality_grade not in _UNUSABLE_GRADES
        )
        return CitizenScanOut(
            id=scan.id,
            reference=scan.reference,
            filename=scan.filename,
            quality=CitizenQualitySummary(
                grade=scan.quality_grade,
                score=scan.quality_score,
                status=scan.quality_status,
                readable=readable,
            ),
            outcome=scan.outcome,
            outcome_rationale=scan.outcome_rationale,
            detected_fields=[
                CitizenDetectedField.model_validate(f) for f in (scan.detected_fields or [])
            ],
            ocr_provider=scan.ocr_provider,
            ocr_model=scan.ocr_model,
            image_url=self._storage.url(key=scan.storage_key),
            created_at=scan.created_at,
        )

    # --- reports (complaints) -------------------------------------------------

    def submit_report(
        self, db: Session, payload: CitizenReportCreate
    ) -> CitizenReport:
        scan = self.get_scan(db, payload.scan_id)
        report = CitizenReport(
            reference=_report_reference(),
            scan_id=scan.id,
            status="SUBMITTED",
            product=payload.product,
            shop=payload.shop,
            location=payload.location,
            issue=payload.issue,
            description=payload.description,
            reporter_name=payload.reporter_name,
            reporter_contact=payload.reporter_contact,
            screening_risk=_screening_risk(scan),
            evidence={
                "scanReference": scan.reference,
                "imageUrl": self._storage.url(key=scan.storage_key),
                "detectedFields": scan.detected_fields or [],
                "quality": {
                    "grade": scan.quality_grade,
                    "score": scan.quality_score,
                    "status": scan.quality_status,
                },
                "ocrProvider": scan.ocr_provider,
                "ocrModel": scan.ocr_model,
                "citizenFollowUps": [],
            },
            is_live=True,
        )
        db.add(report)
        db.flush()
        # UI-03: the SUBMITTED history row — the timeline's first real entry.
        db.add(
            CitizenReportEvent(
                report_id=report.id,
                event="SUBMITTED",
                actor_type="CITIZEN",
                note=payload.issue,
            )
        )
        self._audit.record(
            db,
            event_type=AuditEventType.CITIZEN_REPORT_SUBMITTED,
            entity_type="citizen_report",
            entity_id=report.id,
            payload={"reference": report.reference, "scanReference": scan.reference},
        )
        db.commit()
        db.refresh(report)
        return report

    def get_report(self, db: Session, report_id: uuid.UUID) -> CitizenReport:
        report = self._get_report_loaded(db, report_id)
        if report is None:
            raise NotFoundError("Report not found.")
        return report

    def list_reports(self, db: Session, *, limit: int = 50) -> list[CitizenReport]:
        stmt = (
            select(CitizenReport)
            .order_by(CitizenReport.created_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    # --- citizen: read own complaint + respond to an information request ----

    def get_report_detail(self, db: Session, report_id: uuid.UUID) -> CitizenReport:
        """Citizen-facing read: report + events + pending request + inspection."""
        report = self._get_report_loaded(db, report_id)
        if report is None:
            raise NotFoundError("Report not found.")
        return report

    def respond_to_info_request(
        self,
        db: Session,
        report_id: uuid.UUID,
        *,
        message: str,
        location: str | None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
    ) -> CitizenReport:
        """Citizen answers a pending INFORMATION REQUESTED complaint.

        Only valid while ``status == REQUEST_INFORMATION`` and a pending
        request exists. The response is APPENDED to the evidence (the original
        submit-time snapshot is never overwritten) and the complaint returns
        to UNDER_REVIEW — with history and audit recording both ends.
        """
        report = self._get_report_loaded(db, report_id)
        if report is None:
            raise NotFoundError("Report not found.")
        if report.status != "REQUEST_INFORMATION":
            raise ConflictError(
                "This complaint is not waiting for information from you "
                f"(current status: {report.status})."
            )
        if not (report.pending_info_request or "").strip():
            raise ConflictError("There is no pending information request on this complaint.")

        follow_up: dict = {
            "message": message.strip(),
            "location": location,
            "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if image_bytes:
            # Same anonymous sniff-and-store policy as scans: the response
            # image is validated, stored, and referenced — never inlined.
            sniffed = _sniff(
                data=image_bytes,
                filename=image_filename or "response.jpg",
                declared_mime=None,
                max_size=self._services.settings.max_image_size,
            )
            key = f"citizen/{report.reference.lower()}-response/{uuid.uuid4().hex[:8]}.{sniffed.ext}"
            self._storage.save(key=key, data=image_bytes, content_type=sniffed.mime)
            follow_up["imageUrl"] = self._storage.url(key=key)

        evidence = dict(report.evidence or {})
        follow_ups = list(evidence.get("citizenFollowUps") or [])
        follow_ups.append(follow_up)
        evidence["citizenFollowUps"] = follow_ups
        report.evidence = evidence

        report.status = "UNDER_REVIEW"
        report.pending_info_request = None
        db.add(
            CitizenReportEvent(
                report_id=report.id,
                event="INFORMATION_PROVIDED",
                actor_type="CITIZEN",
                note=message.strip()[:2000],
            )
        )
        self._audit.record(
            db,
            event_type=AuditEventType.CITIZEN_INFO_PROVIDED,
            entity_type="citizen_report",
            entity_id=report.id,
            payload={"reference": report.reference},
        )
        db.commit()
        db.refresh(report)
        return report

    # --- department: queue, detail, KPIs, transitions -------------------------

    def list_complaints(
        self,
        db: Session,
        *,
        statuses: list[str] | None = None,
        risk: str | None = None,
        assigned: str | None = None,
        inspection: str | None = None,
        evidence: str | None = None,
        stale: bool = False,
        location_query: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[CitizenReport]:
        """Department complaint queue — REAL backend filtering (no client-side
        filtering over a fixed array).

        UI-04 additions: ``statuses`` accepts several statuses at once (the
        KPI cards link to multi-status views — same enum, no second status
        system), ``inspection`` filters on the complaint→inspection link,
        ``evidence`` filters by the deterministic completeness band, and
        ``stale`` keeps only open complaints older than the attention
        threshold. Everything except the ``evidence`` band is applied in SQL;
        the band needs the evidence JSON, so it is computed for the already
        SQL-filtered rows before the limit is applied.
        """
        stmt = select(CitizenReport).options(
            selectinload(CitizenReport.inspector),
            selectinload(CitizenReport.inspection),
            selectinload(CitizenReport.events),
        )
        if statuses:
            stmt = stmt.where(CitizenReport.status.in_(tuple(statuses)))
        if risk:
            # A risk filter matches either the system screening value or the
            # official priority (both are triage signals).
            stmt = stmt.where(
                or_(CitizenReport.screening_risk == risk, CitizenReport.official_priority == risk)
            )
        if assigned == "UNASSIGNED":
            stmt = stmt.where(CitizenReport.assigned_inspector_id.is_(None))
        elif assigned == "ASSIGNED":
            stmt = stmt.where(CitizenReport.assigned_inspector_id.is_not(None))
        if inspection == "LINKED":
            stmt = stmt.where(CitizenReport.inspection_id.is_not(None))
        elif inspection == "UNLINKED":
            stmt = stmt.where(CitizenReport.inspection_id.is_(None))
        if stale:
            threshold = datetime.now() - timedelta(days=STALE_COMPLAINT_DAYS)
            stmt = stmt.where(
                CitizenReport.status.not_in(tuple(_TERMINAL_STATUSES)),
                CitizenReport.created_at < threshold,
            )
        if location_query:
            stmt = stmt.where(CitizenReport.location.ilike(f"%{location_query}%"))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    CitizenReport.reference.ilike(like),
                    CitizenReport.product.ilike(like),
                    CitizenReport.issue.ilike(like),
                    CitizenReport.location.ilike(like),
                )
            )
        stmt = stmt.order_by(CitizenReport.created_at.desc())
        if evidence in ("COMPLETE", "PARTIAL", "MINIMAL"):
            # Band filter: evaluate the SQL-filtered rows, then limit.
            rows = list(db.execute(stmt).scalars().all())
            return [r for r in rows if evidence_band(complaint_evidence_completeness(r)) == evidence][
                :limit
            ]
        return list(db.execute(stmt.limit(limit)).scalars().all())

    def complaint_stats(self, db: Session) -> ComplaintStatsOut:
        """Real COUNT(*) values per status — the department KPI area. Zero
        when the table is empty; never a fabricated number."""
        rows = db.execute(
            select(CitizenReport.status, func.count(CitizenReport.id)).group_by(
                CitizenReport.status
            )
        ).all()
        counts = {status: count for status, count in rows}
        unassigned_open = db.execute(
            select(func.count(CitizenReport.id)).where(
                CitizenReport.assigned_inspector_id.is_(None),
                CitizenReport.status.not_in(tuple(_TERMINAL_STATUSES)),
            )
        ).scalar_one()
        return ComplaintStatsOut(
            total=sum(counts.values()),
            submitted=counts.get("SUBMITTED", 0),
            under_review=counts.get("UNDER_REVIEW", 0),
            request_information=counts.get("REQUEST_INFORMATION", 0),
            accepted=counts.get("ACCEPTED", 0),
            assigned=counts.get("ASSIGNED", 0),
            inspection_pending=counts.get("INSPECTION_SCHEDULED", 0),
            inspection_completed=counts.get("INSPECTION_COMPLETED", 0),
            action_taken=counts.get("ACTION_TAKEN", 0),
            closed=counts.get("CLOSED", 0),
            rejected=counts.get("REJECTED", 0),
            unassigned_open=unassigned_open,
        )

    def transition(
        self,
        db: Session,
        report_id: uuid.UUID,
        *,
        action: ComplaintAction,
        actor: User,
        reason: str | None = None,
        inspector_id: uuid.UUID | None = None,
        official_priority: str | None = None,
    ) -> CitizenReport:
        """Apply ONE department action to a complaint.

        The state machine above is the only writer of ``status``; an illegal
        edge is a 422 Conflict — never a silent rewrite. Every action:

        * validates its required inputs (REJECT/REQUEST_INFORMATION need a
          reason; ASSIGN needs an existing inspector),
        * records a persistent CitizenReportEvent row (the timeline),
        * records an audit event WITH the acting user (provenance),
        * commits one transaction.
        """
        report = self._get_report_loaded(db, report_id)
        if report is None:
            raise NotFoundError("Complaint not found.")

        table = _TRANSITIONS.get(action)
        if table is None:
            raise ValidationError(f"Unknown complaint action: {action.value}")
        new_status = table.get(report.status)
        if new_status is None:
            allowed_from = ", ".join(sorted(table))
            raise ConflictError(
                f"Action {action.value} is not allowed from status {report.status} "
                f"(allowed from: {allowed_from or '—'})."
            )

        # ---- action-specific validation ----------------------------------
        if action in (ComplaintAction.REJECT, ComplaintAction.REQUEST_INFORMATION):
            if not (reason or "").strip():
                raise ValidationError(
                    f"A reason is required for {action.value.lower().replace('_', ' ')}."
                )

        target_inspector_id: uuid.UUID | None = None
        if action == ComplaintAction.ASSIGN:
            if inspector_id is None:
                raise ValidationError("Select an inspector to assign.")
            inspector = db.get(User, inspector_id)
            if inspector is None or not inspector.is_active:
                raise NotFoundError("Inspector not found or inactive.")
            if inspector.role not in ("INSPECTOR", "SUPERVISOR", "ADMIN"):
                raise ValidationError(
                    "Only INSPECTOR, SUPERVISOR or ADMIN users can be assigned."
                )
            target_inspector_id = inspector.id

        if action == ComplaintAction.CREATE_INSPECTION and report.inspection_id is not None:
            raise ConflictError("An inspection is already linked to this complaint.")

        if action == ComplaintAction.CREATE_INSPECTION:
            # UI-05 pre-flight: an inspection must carry verifiable context.
            # The complaint's fixed fields (product, issue) are non-null by
            # schema; the remaining context is the citizen evidence — at
            # least one of photo / description / follow-up responses must
            # exist, otherwise the officer should request information first.
            evidence = report.evidence or {}
            has_context = (
                bool(evidence.get("imageUrl"))
                or bool(evidence.get("citizenFollowUps"))
                or bool((report.description or "").strip())
            )
            if not has_context:
                raise ValidationError(
                    "Additional information required: the complaint has no verifiable "
                    "evidence to inspect — no photo, no citizen description and no "
                    "follow-up responses. Request information from the citizen before "
                    "creating a targeted inspection."
                )

        # ---- apply ---------------------------------------------------------
        report.status = new_status
        if official_priority:
            report.official_priority = official_priority
        if action == ComplaintAction.REQUEST_INFORMATION:
            report.pending_info_request = reason.strip()
        if action == ComplaintAction.ASSIGN:
            report.assigned_inspector_id = target_inspector_id

        created_inspection: Inspection | None = None
        if action == ComplaintAction.CREATE_INSPECTION:
            # The ONE complaint → inspection bridge: a real inspection via the
            # existing InspectionService, product/note prefilled from the
            # complaint, linked back on the complaint row. The complaint is
            # NOT marked inspected — only INSPECTION_COMPLETED (a later,
            # explicit department action) may do that.
            created_inspection = self._inspections.create_inspection(
                db,
                inspector_id=report.assigned_inspector_id or actor.id,
                request=CreateInspectionRequest(
                    product_name=report.product or "Unknown packaged commodity",
                    product_category="general",
                    note=(
                        f"Created from citizen complaint {report.reference} — "
                        f"{report.issue}"
                        + (f" ({report.location})" if report.location else "")
                    ),
                ),
            )
            report.inspection_id = created_inspection.id
            # create_inspection commits internally; re-attach and continue.
            db.add(report)

        db.add(
            CitizenReportEvent(
                report_id=report.id,
                event=_action_event_name(action),
                actor_type="DEPARTMENT",
                actor_id=actor.id,
                note=(reason.strip() if reason and reason.strip() else None),
            )
        )
        self._audit.record(
            db,
            event_type=_ACTION_AUDIT[action],
            entity_type="citizen_report",
            entity_id=report.id,
            actor_id=actor.id,
            inspection_id=report.inspection_id,
            payload={
                "reference": report.reference,
                "action": action.value,
                "fromStatus": _action_from_status(action, table, new_status),
                "toStatus": new_status,
                "inspectionReference": (
                    created_inspection.reference_no if created_inspection else None
                ),
            },
        )
        db.commit()
        db.refresh(report)
        return report

    # --- serializers -----------------------------------------------------------

    def complaint_summary(self, report: CitizenReport) -> ComplaintSummaryOut:
        """Department queue row (needs inspector/inspection loaded)."""
        return ComplaintSummaryOut(
            id=report.id,
            reference=report.reference,
            status=report.status,
            product=report.product,
            location=report.location,
            issue=report.issue,
            screening_risk=report.screening_risk,
            official_priority=report.official_priority,
            assigned_inspector_id=report.assigned_inspector_id,
            assigned_inspector_name=(
                report.inspector.full_name if report.inspector else None
            ),
            inspection_id=report.inspection_id,
            inspection_reference=(
                report.inspection.reference_no if report.inspection else None
            ),
            inspection_status=(
                report.inspection.status if report.inspection else None
            ),
            has_image_evidence=bool((report.evidence or {}).get("imageUrl")),
            evidence_completeness=complaint_evidence_completeness(report),
            pending_info_request=report.pending_info_request,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )

    def report_out(self, report: CitizenReport) -> CitizenReportOut:
        return CitizenReportOut.model_validate(report)

    # --- internals ---------------------------------------------------------------

    def _get_report_loaded(
        self, db: Session, report_id: uuid.UUID
    ) -> CitizenReport | None:
        stmt = (
            select(CitizenReport)
            .where(CitizenReport.id == report_id)
            .options(
                selectinload(CitizenReport.events).selectinload(CitizenReportEvent.actor),
                selectinload(CitizenReport.inspector),
                selectinload(CitizenReport.inspection),
                selectinload(CitizenReport.scan),
            )
        )
        return db.execute(stmt).scalar_one_or_none()


def _action_event_name(action: ComplaintAction) -> str:
    return {
        ComplaintAction.START_REVIEW: "REVIEW_STARTED",
        ComplaintAction.ACCEPT: "ACCEPTED",
        ComplaintAction.REJECT: "REJECTED",
        ComplaintAction.REQUEST_INFORMATION: "INFORMATION_REQUESTED",
        ComplaintAction.ASSIGN: "ASSIGNED",
        ComplaintAction.CREATE_INSPECTION: "INSPECTION_CREATED",
        ComplaintAction.COMPLETE_INSPECTION: "INSPECTION_COMPLETED",
        ComplaintAction.RECORD_ACTION: "ACTION_TAKEN",
        ComplaintAction.CLOSE: "CLOSED",
    }[action]


def _action_from_status(
    action: ComplaintAction, table: dict[str, str], new_status: str
) -> str | None:
    for from_status, to_status in table.items():
        if to_status == new_status:
            return from_status
    return None


# --- image sniffing (same policy as intake, standalone to stay anonymous) ----


class _Sniffed:
    __slots__ = ("mime", "ext")

    def __init__(self, mime: str, ext: str) -> None:
        self.mime = mime
        self.ext = ext


def _sniff(*, data: bytes, filename: str, declared_mime: str | None, max_size: int) -> _Sniffed:
    """Server-authoritative validation, same policy as inspector intake.

    Magic bytes + Pillow integrity probe (rejects truncated/corrupt files
    before any OCR cost) + upload size ceiling. JPEG/PNG/WebP only.
    """
    if not data:
        raise ValidationError("Uploaded file is empty.")
    if len(data) > max_size:
        raise ValidationError("Image is too large. Please upload a smaller photo.")

    # Magic-byte triage first for a clean, citizen-friendly message.
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        guess = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        guess = "image/jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        guess = "image/webp"
    else:
        raise ValidationError(
            "Unsupported image type. Please upload a JPEG, PNG or WebP photo of the package."
        )

    # Integrity probe: verify() raises on truncated/corrupt data.
    try:
        with PILImage.open(BytesIO(data)) as probe:
            probe.verify()
    except (OSError, ValueError, SyntaxError) as exc:
        raise ValidationError(
            "This file is not a valid image or is damaged. Please re-capture the photo."
        ) from exc

    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[guess]
    return _Sniffed(guess, ext)
