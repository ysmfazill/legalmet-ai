"""Citizen Mode + complaint routes (UI-02, extended UI-03).

Public surface (NO authentication — a citizen has no account):

    POST /citizen/scans                 screen one package photo (real pipeline)
    GET  /citizen/scans/{id}            re-read a scan by its uuid
    POST /citizen/reports               submit a suspected-issue complaint
    GET  /citizen/reports/{id}          read back a complaint + timeline
    POST /citizen/reports/{id}/respond  answer a pending information request

Department surface (JWT + RBAC — the existing architecture, unchanged roles):

    GET  /citizen/complaints            queue with REAL backend filtering
    GET  /citizen/complaints/stats      KPI counts from the database
    GET  /citizen/complaints/{id}       full complaint review detail
    POST /citizen/complaints/{id}/transition   ACCEPT/REJECT/REQUEST_INFO/…

Security posture:

* Only the five citizen operations above are anonymous. Everything else on
  the API (inspections, findings, review, audit, dashboards, regulations
  admin) still requires the existing JWT + RBAC — unchanged.
* Anonymous endpoints cannot list scans/reports (no enumeration) — a record
  is reachable only by its unguessable UUID.
* Complaint transitions require an authenticated operational role
  (INSPECTOR/SUPERVISOR/ADMIN); AUDITOR may read the queue but not act —
  mirroring the inspection write-role pattern exactly.
* Field extractors and OCR run in-process; the rule engine is never invoked
  through this surface, so no compliance verdict can be produced here.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep
from app.core.enums import UserRole
from app.core.errors import ForbiddenError, ValidationError
from app.db.session import get_db
from app.models import User
from app.schemas.citizen import (
    CitizenReportStatus,
    ComplaintEventOut,
    ComplaintLinkedInspectionOut,
    CitizenReportCreate,
    CitizenReportDetailOut,
    CitizenReportOut,
    CitizenScanOut,
    ComplaintAction,
    ComplaintDetailOut,
    ComplaintStatsOut,
    ComplaintSummaryOut,
    ComplaintTransitionRequest,
)
from app.services.citizen.service import CitizenService
from app.services.registry import Services

router = APIRouter(prefix="/citizen", tags=["citizen"])

# Complaint management write roles — identical to the inspection write roles
# (AUDITOR is read-only and must not act on complaints).
_COMPLAINT_WRITE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


def _citizen_service(services: Services = Depends(get_services_dep)) -> CitizenService:
    # Stateless adapter over the already-wired registry services.
    return CitizenService(services=services)


# ---------------------------------------------------------------------------
# Anonymous citizen surface
# ---------------------------------------------------------------------------


@router.post("/scans", response_model=CitizenScanOut, status_code=201)
async def create_scan(
    file: UploadFile = File(...),
    capture_source: str | None = Form(default=None),
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> CitizenScanOut:
    data = await file.read()
    scan = _service.screen_image(
        db,
        filename=file.filename or "package.jpg",
        declared_mime=file.content_type,
        data=data,
        capture_source=capture_source,
    )
    return _service.scan_out(scan)


@router.get("/scans/{scan_id}", response_model=CitizenScanOut)
def get_scan(
    scan_id: UUID,
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> CitizenScanOut:
    return _service.scan_out(_service.get_scan(db, scan_id))


@router.post("/reports", response_model=CitizenReportOut, status_code=201)
def create_report(
    payload: CitizenReportCreate,
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> CitizenReportOut:
    report = _service.submit_report(db, payload)
    return CitizenReportOut.model_validate(report)


@router.get("/reports/{report_id}", response_model=CitizenReportDetailOut)
def get_report(
    report_id: UUID,
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> CitizenReportDetailOut:
    """Complaint detail as the citizen sees it: status, the REAL recorded
    timeline, the pending information request, the linked inspection."""
    report = _service.get_report_detail(db, report_id)
    out = CitizenReportDetailOut.model_validate(report)
    out.pending_info_request = report.pending_info_request
    out.events = _event_outs(report)
    out.inspection = _linked_inspection(report)
    return out


@router.post("/reports/{report_id}/respond", response_model=CitizenReportDetailOut)
async def respond_to_report(
    report_id: UUID,
    message: str = Form(...),
    location: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> CitizenReportDetailOut:
    """Citizen answers a pending information request (appends evidence,
    returns the complaint to UNDER_REVIEW). Optional image attachment is
    validated and stored exactly like a scan."""
    image_bytes: bytes | None = None
    image_filename: str | None = None
    if file is not None and file.filename:
        image_bytes = await file.read()
        image_filename = file.filename
    report = _service.respond_to_info_request(
        db,
        report_id,
        message=message,
        location=location,
        image_bytes=image_bytes,
        image_filename=image_filename,
    )
    out = CitizenReportDetailOut.model_validate(report)
    out.pending_info_request = report.pending_info_request
    out.events = _event_outs(report)
    out.inspection = _linked_inspection(report)
    return out


# ---------------------------------------------------------------------------
# Department complaint management (authenticated + RBAC)
# ---------------------------------------------------------------------------


def _event_outs(report) -> list[ComplaintEventOut]:
    return [
        ComplaintEventOut(
            id=event.id,
            event=event.event,
            actor_type=event.actor_type,
            actor_name=event.actor.full_name if event.actor else None,
            note=event.note,
            created_at=event.created_at,
        )
        for event in report.events
    ]


def _linked_inspection(report) -> ComplaintLinkedInspectionOut | None:
    if report.inspection is None:
        return None
    return ComplaintLinkedInspectionOut(
        id=report.inspection.id,
        reference_no=report.inspection.reference_no,
        status=report.inspection.status,
    )


@router.get("/complaints", response_model=list[ComplaintSummaryOut])
def list_complaints(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="One status, or several as a comma-separated list (same enum values).",
    ),
    risk: str | None = Query(default=None),
    assigned: str | None = Query(default=None, pattern="^(ASSIGNED|UNASSIGNED)$"),
    inspection: str | None = Query(default=None, pattern="^(LINKED|UNLINKED)$"),
    evidence: str | None = Query(default=None, pattern="^(COMPLETE|PARTIAL|MINIMAL)$"),
    stale: bool = Query(default=False),
    location: str | None = Query(default=None, min_length=1),
    search: str | None = Query(default=None, min_length=1),
    _user: User = Depends(get_current_user),
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> list[ComplaintSummaryOut]:
    """Department complaint queue. Filtering happens in SQL — the client
    never filters a fixed array. UI-04: multi-status, inspection-link,
    evidence-band and stale filters (all real database constraints)."""
    statuses: list[str] | None = None
    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        known = {s.value for s in CitizenReportStatus}
        unknown = [s for s in statuses if s not in known]
        if unknown:
            raise ValidationError(
                f"Unknown complaint status filter: {', '.join(unknown)}."
            )
    reports = _service.list_complaints(
        db,
        statuses=statuses,
        risk=risk,
        assigned=assigned,
        inspection=inspection,
        evidence=evidence,
        stale=stale,
        location_query=location,
        search=search,
    )
    return [_service.complaint_summary(r) for r in reports]


@router.get("/complaints/stats", response_model=ComplaintStatsOut)
def complaint_stats(
    _user: User = Depends(get_current_user),
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> ComplaintStatsOut:
    return _service.complaint_stats(db)


@router.get("/complaints/inspectors", response_model=list[dict])
def list_assignable_inspectors(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Active users who may be assigned a complaint (same operational roles
    the inspection write path uses)."""
    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .where(User.role.in_(("INSPECTOR", "SUPERVISOR", "ADMIN")))
        .order_by(User.full_name)
    )
    users = db.execute(stmt).scalars().all()
    return [{"id": str(u.id), "fullName": u.full_name, "role": u.role} for u in users]


@router.get("/complaints/{report_id}", response_model=ComplaintDetailOut)
def get_complaint(
    report_id: UUID,
    _user: User = Depends(get_current_user),
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> ComplaintDetailOut:
    """Full complaint review detail for the department."""
    report = _service.get_report_detail(db, report_id)
    summary = _service.complaint_summary(report)
    detail = ComplaintDetailOut(
        **summary.model_dump(),
        shop=report.shop,
        description=report.description,
        reporter_name=report.reporter_name,
        reporter_contact=report.reporter_contact,
        evidence=report.evidence,
        events=_event_outs(report),
    )
    detail.inspection = _linked_inspection(report)
    return detail


@router.post(
    "/complaints/{report_id}/transition", response_model=ComplaintDetailOut
)
def transition_complaint(
    report_id: UUID,
    body: ComplaintTransitionRequest,
    user: User = Depends(get_current_user),
    _service: CitizenService = Depends(_citizen_service),
    db: Session = Depends(get_db),
) -> ComplaintDetailOut:
    """Apply one department action to a complaint.

    RBAC: operational roles only — the dependency below raises 403 for
    AUDITOR, exactly like the inspection write paths.
    """
    allowed = {r.value for r in _COMPLAINT_WRITE_ROLES}
    if user.role not in allowed:
        raise ForbiddenError(
            "You do not have permission to act on complaints "
            f"(role {user.role} is read-only here)."
        )
    report = _service.transition(
        db,
        report_id,
        action=body.action,
        actor=user,
        reason=body.reason,
        inspector_id=body.inspector_id,
        official_priority=body.official_priority,
    )
    loaded = _service.get_report_detail(db, report_id)
    summary = _service.complaint_summary(loaded)
    detail = ComplaintDetailOut(
        **summary.model_dump(),
        shop=loaded.shop,
        description=loaded.description,
        reporter_name=loaded.reporter_name,
        reporter_contact=loaded.reporter_contact,
        evidence=loaded.evidence,
        events=_event_outs(loaded),
    )
    detail.inspection = _linked_inspection(loaded)
    return detail
