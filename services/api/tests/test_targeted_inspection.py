"""Complaint → Targeted Inspection API tests (UI-05).

The core METRASIGHT workflow: an ACCEPTED citizen complaint becomes a real,
linked inspection without ever losing the original complaint evidence.

* creation: the existing CREATE_INSPECTION transition bridges complaint →
  inspection; the inspection carries complaint provenance (sourceComplaint)
  and the complaint keeps its link (inspectionId/reference/status)
* duplicate protection: a complaint with a linked inspection is rejected 409
* pre-flight: a complaint with zero verifiable evidence cannot be converted
* source complaint endpoint: full brief + immutable citizen evidence
* assignment: SUPERVISOR/ADMIN only, validated target, finalized protection,
  explicit reassignment, source-complaint sync, audited
* audit trail: every transition leaves an append-only audit event
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from tests.conftest import API, AUDITOR_EMAIL


def _png(width: int = 1600, height: int = 2000) -> bytes:
    img = PILImage.new("RGB", (width, height), (120, 90, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_complaint(
    client: TestClient,
    *,
    description: str | None = "The printed MRP looks tampered with",
    issue: str = "MRP appears inconsistent",
    location: str = "UI05 Testville",
) -> dict:
    """Anonymous scan + report → a SUBMITTED complaint with photo evidence."""
    scan = client.post(
        f"{API}/citizen/scans",
        files={"file": ("package.jpg", _png(), "image/jpeg")},
    ).json()
    return client.post(
        f"{API}/citizen/reports",
        json={
            "scanId": scan["id"],
            "product": "UI05 Targeted Product",
            "shop": "UI05 Test Store",
            "location": location,
            "issue": issue,
            "description": description,
        },
    ).json()


def _transition(
    client: TestClient,
    headers: dict[str, str],
    complaint_id: str,
    action: str,
    **extra: object,
):
    return client.post(
        f"{API}/citizen/complaints/{complaint_id}/transition",
        headers=headers,
        json={"action": action, **extra},
    )


def _accept(client: TestClient, headers: dict[str, str], complaint_id: str) -> dict:
    assert _transition(client, headers, complaint_id, "START_REVIEW").status_code == 200
    resp = _transition(client, headers, complaint_id, "ACCEPT")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _convert(client: TestClient, headers: dict[str, str], complaint_id: str):
    return _transition(client, headers, complaint_id, "CREATE_INSPECTION")


def _inspection_audit(client: TestClient, headers: dict[str, str], inspection_id: str) -> list[dict]:
    """The append-only audit trail scoped to one inspection (any staff role)."""
    resp = client.get(f"{API}/inspections/{inspection_id}/audit", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _audited(events: list[dict], event_type: str) -> bool:
    return any(e["eventType"] == event_type for e in events)


class TestCreateTargetedInspection:
    def test_accepted_complaint_converts_to_linked_inspection(
        self, client: TestClient, inspector_headers
    ):
        report = _make_complaint(client)
        accepted = _accept(client, inspector_headers, report["id"])
        assert accepted["status"] == "ACCEPTED"

        converted = _convert(client, inspector_headers, report["id"])
        assert converted.status_code == 200, converted.text
        body = converted.json()

        # The complaint advanced along its own state machine and kept the link.
        assert body["status"] == "INSPECTION_SCHEDULED"
        assert body["inspectionId"]
        assert body["inspectionReference"].startswith("LM-")

        # The inspection is real and carries its complaint provenance.
        inspection = client.get(
            f"{API}/inspections/{body['inspectionId']}", headers=inspector_headers
        ).json()
        assert inspection["sourceComplaint"]["reference"] == report["reference"]
        assert inspection["sourceComplaint"]["issue"] == "MRP appears inconsistent"
        assert report["reference"] in inspection["note"]

        # The full chain is audited against the inspection.
        events = _inspection_audit(client, inspector_headers, inspection["id"])
        assert _audited(events, "INSPECTION_CREATED")
        assert _audited(events, "COMPLAINT_INSPECTION_CREATED")

    def test_queue_row_exposes_inspection_status(self, client: TestClient, inspector_headers):
        report = _make_complaint(client)
        _accept(client, inspector_headers, report["id"])
        converted = _convert(client, inspector_headers, report["id"]).json()

        rows = client.get(
            f"{API}/citizen/complaints", headers=inspector_headers
        ).json()
        row = next(r for r in rows if r["reference"] == report["reference"])
        assert row["inspectionId"] == converted["inspectionId"]
        assert row["inspectionStatus"] == "CREATED"

    def test_duplicate_inspection_rejected(self, client: TestClient, inspector_headers):
        report = _make_complaint(client)
        _accept(client, inspector_headers, report["id"])
        assert _convert(client, inspector_headers, report["id"]).status_code == 200

        again = _convert(client, inspector_headers, report["id"])
        assert again.status_code == 409
        # The state machine itself blocks re-conversion (the complaint has
        # moved past ACCEPTED/ASSIGNED); the "already linked" guard is the
        # server-side invariant underneath it.
        assert "inspection" in again.json()["error"]["message"].lower()

    def test_preflight_rejects_complaint_without_evidence(
        self, client: TestClient, inspector_headers, db: Session
    ):
        # Public API complaints always carry a photo; strip the evidence via
        # the DB to prove the server-side guard (no photo, no description, no
        # follow-ups → the officer must request information first).
        report = _make_complaint(client)
        _accept(client, inspector_headers, report["id"])

        from app.models import CitizenReport

        row = db.get(CitizenReport, uuid.UUID(report["id"]))
        row.evidence = None
        row.description = None
        db.commit()

        resp = _convert(client, inspector_headers, report["id"])
        assert resp.status_code == 422
        assert "additional information required" in resp.json()["error"]["message"].lower()

    def test_not_accepted_complaint_cannot_convert(self, client: TestClient, inspector_headers):
        report = _make_complaint(client)  # SUBMITTED
        resp = _convert(client, inspector_headers, report["id"])
        assert resp.status_code == 409

    def test_auditor_cannot_convert(self, client: TestClient, auditor_headers):
        report = _make_complaint(client)
        resp = _convert(client, auditor_headers, report["id"])
        assert resp.status_code == 403


class TestSourceComplaintEndpoint:
    def test_source_complaint_returns_brief_and_evidence(
        self, client: TestClient, inspector_headers
    ):
        report = _make_complaint(client)
        _accept(client, inspector_headers, report["id"])
        converted = _convert(client, inspector_headers, report["id"]).json()

        resp = client.get(
            f"{API}/inspections/{converted['inspectionId']}/source-complaint",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        brief = resp.json()
        assert brief["reference"] == report["reference"]
        assert brief["product"] == "UI05 Targeted Product"
        assert brief["issue"] == "MRP appears inconsistent"
        assert brief["location"] == "UI05 Testville"
        assert brief["description"] == "The printed MRP looks tampered with"
        assert brief["evidence"]["imageUrl"]
        assert brief["evidence"]["detectedFields"] is not None
        # submitted, review started, accepted, inspection created
        assert brief["eventCount"] >= 4

    def test_ordinary_inspection_has_no_source_complaint(
        self, client: TestClient, inspector_headers
    ):
        created = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": "Plain intake", "productCategory": "general"},
        )
        assert created.status_code == 201, created.text
        resp = client.get(
            f"{API}/inspections/{created.json()['id']}/source-complaint",
            headers=inspector_headers,
        )
        assert resp.status_code == 404
        assert "did not originate" in resp.json()["error"]["message"].lower()

    def test_unknown_inspection_404(self, client: TestClient, inspector_headers):
        resp = client.get(
            f"{API}/inspections/{uuid.uuid4()}/source-complaint", headers=inspector_headers
        )
        assert resp.status_code == 404

    def test_anonymous_cannot_read_source_complaint(self, client: TestClient, inspector_headers):
        report = _make_complaint(client)
        _accept(client, inspector_headers, report["id"])
        converted = _convert(client, inspector_headers, report["id"]).json()

        resp = client.get(f"{API}/inspections/{converted['inspectionId']}/source-complaint")
        assert resp.status_code == 401


class TestAssignInspection:
    def _targeted(self, client: TestClient, headers: dict[str, str]) -> dict:
        report = _make_complaint(client)
        _accept(client, headers, report["id"])
        converted = _convert(client, headers, report["id"]).json()
        return {"report": report, "inspection": converted}

    def _inspector_id(self, client: TestClient, headers: dict[str, str]) -> str:
        inspectors = client.get(f"{API}/citizen/complaints/inspectors", headers=headers).json()
        return next(u["id"] for u in inspectors if u["role"] == "INSPECTOR")

    def test_supervisor_assigns_inspector(self, client: TestClient, supervisor_headers):
        ctx = self._targeted(client, supervisor_headers)
        inspection_id = ctx["inspection"]["inspectionId"]
        inspector_id = self._inspector_id(client, supervisor_headers)

        resp = client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": inspector_id, "note": "Verify the MRP marking in person"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["inspectorId"] == inspector_id
        assert body["inspectorName"]

        # The source complaint stays in sync: the inspector is recorded while
        # the complaint keeps its post-conversion status (the inspection link
        # already advanced it past ASSIGNED).
        detail = client.get(
            f"{API}/citizen/complaints/{ctx['report']['id']}", headers=supervisor_headers
        ).json()
        assert detail["assignedInspectorId"] == inspector_id
        assert detail["status"] == "INSPECTION_SCHEDULED"

        events = _inspection_audit(client, supervisor_headers, inspection_id)
        assert _audited(events, "INSPECTION_ASSIGNED")
        assert _audited(events, "COMPLAINT_ASSIGNED")

    def test_assignment_visible_in_inspector_list(self, client: TestClient, supervisor_headers):
        ctx = self._targeted(client, supervisor_headers)
        inspection_id = ctx["inspection"]["inspectionId"]
        inspector_id = self._inspector_id(client, supervisor_headers)
        client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": inspector_id},
        )

        items = client.get(
            f"{API}/inspections", headers=supervisor_headers, params={"page": 1, "pageSize": 100}
        ).json()["items"]
        row = next(i for i in items if i["id"] == inspection_id)
        assert row["inspectorId"] == inspector_id
        assert row["inspectorName"]
        assert row["sourceComplaint"]["reference"] == ctx["report"]["reference"]

    def test_inspector_cannot_assign(self, client: TestClient, inspector_headers):
        ctx = self._targeted(client, inspector_headers)
        inspector_id = self._inspector_id(client, inspector_headers)
        resp = client.post(
            f"{API}/inspections/{ctx['inspection']['inspectionId']}/assign",
            headers=inspector_headers,
            json={"inspectorId": inspector_id},
        )
        assert resp.status_code == 403

    def test_auditor_cannot_assign(self, client: TestClient, auditor_headers, inspector_headers):
        ctx = self._targeted(client, inspector_headers)
        inspector_id = self._inspector_id(client, inspector_headers)
        resp = client.post(
            f"{API}/inspections/{ctx['inspection']['inspectionId']}/assign",
            headers=auditor_headers,
            json={"inspectorId": inspector_id},
        )
        assert resp.status_code == 403

    def test_anonymous_cannot_assign(self, client: TestClient, inspector_headers):
        ctx = self._targeted(client, inspector_headers)
        resp = client.post(
            f"{API}/inspections/{ctx['inspection']['inspectionId']}/assign",
            json={"inspectorId": str(uuid.uuid4())},
        )
        assert resp.status_code == 401

    def test_unknown_inspector_rejected(self, client: TestClient, supervisor_headers):
        ctx = self._targeted(client, supervisor_headers)
        resp = client.post(
            f"{API}/inspections/{ctx['inspection']['inspectionId']}/assign",
            headers=supervisor_headers,
            json={"inspectorId": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert "inspector" in resp.json()["error"]["message"].lower()

    def test_invalid_role_target_rejected(self, client: TestClient, supervisor_headers, db: Session):
        # AUDITOR is a read-only role: never a valid assignment target.
        from sqlalchemy import select

        from app.models import User

        auditor = db.execute(select(User).where(User.email == AUDITOR_EMAIL)).scalar_one()
        ctx = self._targeted(client, supervisor_headers)
        resp = client.post(
            f"{API}/inspections/{ctx['inspection']['inspectionId']}/assign",
            headers=supervisor_headers,
            json={"inspectorId": str(auditor.id)},
        )
        assert resp.status_code == 422

    def test_same_inspector_is_idempotent(self, client: TestClient, supervisor_headers):
        ctx = self._targeted(client, supervisor_headers)
        inspection_id = ctx["inspection"]["inspectionId"]
        inspector_id = self._inspector_id(client, supervisor_headers)
        first = client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": inspector_id},
        )
        assert first.status_code == 200
        second = client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": inspector_id},
        )
        assert second.status_code == 200  # no-op, not an error

        # Only ONE assignment was recorded — no duplicate audit spam.
        events = _inspection_audit(client, supervisor_headers, inspection_id)
        assert sum(1 for e in events if e["eventType"] == "INSPECTION_ASSIGNED") == 1

    def test_reassignment_requires_explicit_flag(self, client: TestClient, supervisor_headers):
        ctx = self._targeted(client, supervisor_headers)
        inspection_id = ctx["inspection"]["inspectionId"]
        inspectors = client.get(
            f"{API}/citizen/complaints/inspectors", headers=supervisor_headers
        ).json()
        first = next(u for u in inspectors if u["role"] == "INSPECTOR")
        second = next(u for u in inspectors if u["id"] != first["id"])

        assert (
            client.post(
                f"{API}/inspections/{inspection_id}/assign",
                headers=supervisor_headers,
                json={"inspectorId": first["id"]},
            ).status_code
            == 200
        )
        blocked = client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": second["id"]},
        )
        assert blocked.status_code == 409
        assert "reassignment" in blocked.json()["error"]["message"].lower()

        allowed = client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": second["id"], "reassign": True},
        )
        assert allowed.status_code == 200
        assert allowed.json()["inspectorId"] == second["id"]

    def test_finalized_inspection_cannot_be_assigned(
        self, client: TestClient, supervisor_headers, db: Session
    ):
        ctx = self._targeted(client, supervisor_headers)
        inspection_id = ctx["inspection"]["inspectionId"]

        # Force the terminal state directly on the row (deterministic — the
        # workflow's own completion path is covered by its own tests).
        from app.models import Inspection as InspectionModel

        row = db.get(InspectionModel, uuid.UUID(inspection_id))
        row.status = "COMPLETED"
        row.completed_at = row.completed_at or datetime.now(timezone.utc)
        db.commit()

        inspector_id = self._inspector_id(client, supervisor_headers)
        resp = client.post(
            f"{API}/inspections/{inspection_id}/assign",
            headers=supervisor_headers,
            json={"inspectorId": inspector_id},
        )
        assert resp.status_code == 409
        assert "finalized" in resp.json()["error"]["message"].lower()
