"""Report routes (UI-08).

Thin by design: authenticate → enforce role → delegate to ReportService →
serialise. The finalization gate, versioning rules and honesty contracts live
in the service layer — never only in the frontend.

Endpoints:

    POST /reports                          create (one live report/inspection)
    GET  /reports                          Report Center list + KPIs
    GET  /reports/kpis                     dashboard counts (real records)
    GET  /reports/{id}                     full detail (snapshot + versions)
    POST /reports/{id}/generate            freeze a new snapshot version
    POST /reports/{id}/review              record the human review
    POST /reports/{id}/finalize            the gated finalization
    POST /reports/{id}/amend               new version (reason mandatory)
    GET  /reports/{id}/evidence-pack       the evidence bundle (E-00N manifest)
    GET  /reports/{id}/export/pdf          real PDF (reportlab)
    GET  /reports/{id}/export/docx         real DOCX (python-docx)
    GET  /reports/{id}/audit               report lifecycle events

Authorization: INSPECTOR/SUPERVISOR/ADMIN write (assignment-guarded in the
service); INSPECTOR/SUPERVISOR/ADMIN/AUDITOR read. A citizen has no account
and no route — internal reports are never exposed publicly.
"""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination, require_role
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import User
from app.schemas.report import (
    ReportAmendRequest,
    ReportAuditOut,
    ReportCreateRequest,
    ReportDetailOut,
    ReportEvidencePackOut,
    ReportFinalizeRequest,
    ReportGenerateRequest,
    ReportKpisOut,
    ReportListOut,
    ReportSummaryOut,
)
from app.services.registry import Services
from app.services.report.service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

_REPORT_WRITE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)
_REPORT_READ_ROLES = (
    UserRole.INSPECTOR,
    UserRole.SUPERVISOR,
    UserRole.ADMIN,
    UserRole.AUDITOR,
)

# Export filenames are built from sanitized tokens only — no user-controlled
# path component is ever accepted (path-traversal guard, spec §30).
_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")


def _filename(reference: str, version: int, ext: str) -> str:
    token = _SAFE_TOKEN.sub("-", reference or "report").strip("-")[:60] or "report"
    return f"metrasight-report-{token}-v{version}.{ext}"


@router.post("", response_model=ReportDetailOut, status_code=201)
def create_report(
    body: ReportCreateRequest,
    user: User = Depends(require_role(*_REPORT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportDetailOut:
    report = services.reports.create_report(
        db, inspection_id=body.inspection_id, actor=user, note=body.note
    )
    return ReportDetailOut.model_validate(
        services.reports.get_report(db, report.id)
    )


@router.get("", response_model=ReportListOut)
def list_reports(
    status: str | None = Query(default=None),
    inspection_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    pg: Pagination = Depends(pagination),
    _user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportListOut:
    items, total = services.reports.list_reports(
        db,
        limit=pg.limit,
        offset=pg.offset,
        status=status,
        inspection_id=inspection_id,
        query=q,
    )
    return ReportListOut(
        items=[ReportSummaryOut.model_validate(i) for i in items],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


@router.get("/kpis", response_model=ReportKpisOut)
def report_kpis(
    _user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportKpisOut:
    return ReportKpisOut.model_validate(services.reports.kpis(db))


@router.get("/{report_id}", response_model=ReportDetailOut)
def get_report(
    report_id: UUID,
    _user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportDetailOut:
    return ReportDetailOut.model_validate(
        services.reports.get_report(db, report_id)
    )


@router.post("/{report_id}/generate", response_model=ReportDetailOut)
def generate_report(
    report_id: UUID,
    body: ReportGenerateRequest | None = None,
    user: User = Depends(require_role(*_REPORT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportDetailOut:
    services.reports.generate_report(
        db, report_id=report_id, actor=user, note=(body.note if body else None)
    )
    return ReportDetailOut.model_validate(
        services.reports.get_report(db, report_id)
    )


@router.post("/{report_id}/review", response_model=ReportDetailOut)
def review_report(
    report_id: UUID,
    body: ReportGenerateRequest | None = None,
    user: User = Depends(require_role(*_REPORT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportDetailOut:
    services.reports.review_report(
        db, report_id=report_id, actor=user, note=(body.note if body else None)
    )
    return ReportDetailOut.model_validate(
        services.reports.get_report(db, report_id)
    )


@router.post("/{report_id}/finalize", response_model=ReportDetailOut)
def finalize_report(
    report_id: UUID,
    body: ReportFinalizeRequest | None = None,
    user: User = Depends(require_role(*_REPORT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportDetailOut:
    services.reports.finalize_report(
        db, report_id=report_id, actor=user, note=(body.note if body else None)
    )
    return ReportDetailOut.model_validate(
        services.reports.get_report(db, report_id)
    )


@router.post("/{report_id}/amend", response_model=ReportDetailOut)
def amend_report(
    report_id: UUID,
    body: ReportAmendRequest,
    user: User = Depends(require_role(*_REPORT_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportDetailOut:
    services.reports.amend_report(
        db, report_id=report_id, actor=user, reason=body.reason
    )
    return ReportDetailOut.model_validate(
        services.reports.get_report(db, report_id)
    )


@router.get("/{report_id}/evidence-pack", response_model=ReportEvidencePackOut)
def evidence_pack(
    report_id: UUID,
    _user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportEvidencePackOut:
    return ReportEvidencePackOut.model_validate(
        services.reports.evidence_pack(db, report_id)
    )


@router.get("/{report_id}/audit", response_model=ReportAuditOut)
def report_audit(
    report_id: UUID,
    _user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReportAuditOut:
    report = services.reports.get_report(db, report_id)
    return ReportAuditOut(
        report_id=report["id"],
        inspection_id=report["inspection_id"],
        events=services.reports.audit_events(db, report_id),
    )


def _image_loader(db: Session, services: Services):
    def load(detail: dict | None) -> bytes | None:
        return services.reports.evidence_bytes_for_image(db, services.storage, detail)

    return load


@router.get("/{report_id}/export/pdf")
def export_pdf(
    report_id: UUID,
    user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Response:
    """Real PDF export (reportlab) — on failure the inspection data is
    unchanged and the error envelope carries the spec §24 message."""
    from app.services.report.pdf import render_report_pdf

    report, version = services.reports.current_version_snapshot(db, report_id)
    pack = services.reports.evidence_pack(db, report_id)
    audit_events = services.reports.audit_events(db, report_id)
    try:
        pdf_bytes = render_report_pdf(
            version.snapshot or {},
            evidence_items=pack["items"],
            image_loader=_image_loader(db, services),
            audit_events=audit_events,
        )
    except Exception as exc:  # noqa: BLE001 — the data is untouched; report honestly
        from app.core.errors import AppError, ErrorCode

        raise AppError(
            "PDF generation failed. Your inspection data has not been changed.",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
        ) from exc
    services.reports.record_export(
        db, report_id=report_id, actor=user, fmt="pdf", version_id=version.id
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_filename(report.inspection.reference_no, report.version, "pdf")}"'
            )
        },
    )


@router.get("/{report_id}/export/docx")
def export_docx(
    report_id: UUID,
    user: User = Depends(require_role(*_REPORT_READ_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Response:
    """Real DOCX export (python-docx) — editable, professional formatting."""
    from app.services.report.docx import render_report_docx

    report, version = services.reports.current_version_snapshot(db, report_id)
    pack = services.reports.evidence_pack(db, report_id)
    audit_events = services.reports.audit_events(db, report_id)
    try:
        docx_bytes = render_report_docx(
            version.snapshot or {},
            evidence_items=pack["items"],
            image_loader=_image_loader(db, services),
            audit_events=audit_events,
        )
    except Exception as exc:  # noqa: BLE001 — the data is untouched; report honestly
        from app.core.errors import AppError, ErrorCode

        raise AppError(
            "Document generation failed.",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
        ) from exc
    services.reports.record_export(
        db, report_id=report_id, actor=user, fmt="docx", version_id=version.id
    )
    return Response(
        content=docx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_filename(report.inspection.reference_no, report.version, "docx")}"'
            )
        },
    )
