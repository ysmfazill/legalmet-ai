"""Citizen Mode API tests (UI-02).

Covers the anonymous SCAN → screen → REPORT surface:

* anonymous access works (no token) — by design, documented
* real quality gate: tiny/1x1 images are honestly rejected as unreadable
  rather than silently screened
* screening outcome vocabulary is the honest set — the API can never express
  a "confirmed violation"
* report submission attaches the scan's evidence snapshot and returns a
  real, backend-generated reference
* citizen endpoints cannot enumerate/list anything, and RBAC on every
  other mutating route is untouched (test_api_security)
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.schemas.citizen import CitizenScreenOutcome, CitizenReportStatus
from tests.conftest import API


def _png(width: int, height: int) -> bytes:
    """A real, decodable PNG (solid brown-ish noise-free fill)."""
    img = PILImage.new("RGB", (width, height), (120, 90, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _label_png(width: int = 1600, height: int = 2000) -> bytes:
    """A larger PNG whose Pillow usability grade is not REJECTED/POOR."""
    return _png(width, height)


class TestCitizenScan:
    def test_anonymous_scan_allowed(self, client: TestClient):
        # No Authorization header — Citizen Mode is anonymous by design.
        resp = client.post(
            f"{API}/citizen/scans",
            files={"file": ("package.jpg", _label_png(), "image/jpeg")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["reference"].startswith("CS-")
        assert body["outcome"] in {o.value for o in CitizenScreenOutcome}
        assert body["quality"]["grade"] is not None

    def test_tiny_image_is_unreadable_not_silently_screened(self, client: TestClient):
        resp = client.post(
            f"{API}/citizen/scans",
            files={"file": ("tiny.png", _png(1, 1), "image/png")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["outcome"] == "IMAGE_UNREADABLE", body
        assert body["quality"]["readable"] is False
        assert "retake" in (body["outcomeRationale"] or "").lower()

    def test_outcome_vocabulary_never_contains_violation(self, client: TestClient):
        # The outcome field cannot express a confirmed violation — by enum.
        outcomes = {o.value for o in CitizenScreenOutcome}
        assert "VIOLATION" not in " ".join(outcomes)
        assert "CONFIRMED" not in " ".join(outcomes)

    def test_invalid_file_rejected_with_clear_error(self, client: TestClient):
        resp = client.post(
            f"{API}/citizen/scans",
            files={"file": ("notes.txt", b"this is not an image", "text/plain")},
        )
        assert resp.status_code == 422, resp.text
        assert "JPEG" in resp.text or "image" in resp.text.lower()

    def test_corrupt_image_rejected(self, client: TestClient):
        # Magic bytes say PNG but the body is truncated garbage.
        bad = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        resp = client.post(
            f"{API}/citizen/scans",
            files={"file": ("corrupt.png", bad, "image/png")},
        )
        assert resp.status_code == 422
        assert "traceback" not in resp.text.lower()

    def test_scan_can_be_reread_by_uuid(self, client: TestClient):
        created = client.post(
            f"{API}/citizen/scans",
            files={"file": ("package.jpg", _label_png(), "image/jpeg")},
        ).json()
        fetched = client.get(f"{API}/citizen/scans/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["reference"] == created["reference"]

    def test_unknown_scan_404(self, client: TestClient):
        resp = client.get(f"{API}/citizen/scans/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_no_listing_endpoint(self, client: TestClient):
        # Anonymous surface must not allow enumeration.
        resp = client.get(f"{API}/citizen/scans")
        assert resp.status_code == 405

    def test_scan_is_audited(self, client: TestClient, db):
        from app.models import AuditEvent

        before = db.query(AuditEvent).filter(
            AuditEvent.event_type == "CITIZEN_SCAN_COMPLETED"
        ).count()
        client.post(
            f"{API}/citizen/scans",
            files={"file": ("package.jpg", _label_png(), "image/jpeg")},
        )
        after = db.query(AuditEvent).filter(
            AuditEvent.event_type == "CITIZEN_SCAN_COMPLETED"
        ).count()
        assert after == before + 1


class TestCitizenReport:
    def _scan(self, client: TestClient) -> dict:
        return client.post(
            f"{API}/citizen/scans",
            files={"file": ("package.jpg", _label_png(), "image/jpeg")},
        ).json()

    def test_submit_report_anonymous(self, client: TestClient):
        scan = self._scan(client)
        resp = client.post(
            f"{API}/citizen/reports",
            json={
                "scanId": scan["id"],
                "product": "DEMO Wholesome Product",
                "shop": "Local store",
                "location": "Pune",
                "issue": "MRP may be unclear",
                "description": "The printed price looks scratched",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        # UI-03: reports ARE complaints now — the reference is the complaint ID.
        assert body["reference"].startswith("CMP-")
        assert body["status"] == CitizenReportStatus.SUBMITTED.value

    def test_report_requires_real_scan(self, client: TestClient):
        resp = client.post(
            f"{API}/citizen/reports",
            json={
                "scanId": "00000000-0000-0000-0000-000000000000",
                "product": "x",
                "issue": "y",
            },
        )
        assert resp.status_code == 404

    def test_report_validation(self, client: TestClient):
        scan = self._scan(client)
        resp = client.post(
            f"{API}/citizen/reports",
            json={"scanId": scan["id"], "product": "   ", "issue": "y"},
        )
        assert resp.status_code == 422

    def test_report_reread_and_evidence_snapshot(self, client: TestClient, db: Session):
        scan = self._scan(client)
        created = client.post(
            f"{API}/citizen/reports",
            json={
                "scanId": scan["id"],
                "product": "DEMO Product",
                "issue": "Net quantity missing",
            },
        ).json()
        fetched = client.get(f"{API}/citizen/reports/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["reference"] == created["reference"]

        # Evidence snapshot recorded with the report row.
        from uuid import UUID

        from app.models import CitizenReport

        report = db.get(CitizenReport, UUID(created["id"]))
        assert report is not None
        assert report.evidence["scanReference"] == scan["reference"]
        assert "detectedFields" in report.evidence

    def test_report_is_audited(self, client: TestClient, db):
        from app.models import AuditEvent

        scan = self._scan(client)
        client.post(
            f"{API}/citizen/reports",
            json={"scanId": scan["id"], "product": "x", "issue": "y"},
        )
        events = (
            db.query(AuditEvent)
            .filter(AuditEvent.event_type == "CITIZEN_REPORT_SUBMITTED")
            .count()
        )
        assert events >= 1
