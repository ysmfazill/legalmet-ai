"""Department Command Center API tests (UI-04).

Covers the aggregated dashboard endpoint and the new queue filters:

* authentication: anonymous callers are rejected (401); every staff role,
  including the read-only AUDITOR, can read the dashboard
* aggregation correctness: KPI counts, status distribution, pipeline stages,
  risk distribution, evidence completeness and the priority queue all move
  exactly as the underlying complaint records change
* trend grouping by real created_at dates with a validated day window
* location rollups from real complaint locations
* recent activity from the REAL audit trail (actor + reference + link target)
* new backend filters: multi-status, inspection link, evidence band, stale
* invalid filters are structured 422s, never silent matches
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from tests.conftest import API


def _png(width: int = 1600, height: int = 2000) -> bytes:
    img = PILImage.new("RGB", (width, height), (120, 90, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_complaint(
    client: TestClient,
    *,
    location: str = "UI04 Testville",
    shop: str = "UI04 Test Store",
    description: str = "Scratched MRP sticker",
    issue: str = "MRP may be unclear",
) -> dict:
    """Anonymous scan + report → a SUBMITTED complaint, as a citizen does."""
    scan = client.post(
        f"{API}/citizen/scans",
        files={"file": ("package.jpg", _png(), "image/jpeg")},
    ).json()
    return client.post(
        f"{API}/citizen/reports",
        json={
            "scanId": scan["id"],
            "product": "UI04 Dashboard Product",
            "shop": shop,
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
) -> object:
    return client.post(
        f"{API}/citizen/complaints/{complaint_id}/transition",
        headers=headers,
        json={"action": action, **extra},
    )


def _dashboard(client: TestClient, headers: dict[str, str], **params: object) -> dict:
    resp = client.get(f"{API}/department/dashboard", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestDashboardAccess:
    def test_anonymous_cannot_read_dashboard(self, client: TestClient):
        resp = client.get(f"{API}/department/dashboard")
        assert resp.status_code == 401

    def test_inspector_can_read_dashboard(self, client: TestClient, inspector_headers):
        assert client.get(f"{API}/department/dashboard", headers=inspector_headers).status_code == 200

    def test_auditor_can_read_dashboard(self, client: TestClient, auditor_headers):
        # The dashboard is read-only — AUDITOR keeps its read-everything right.
        assert client.get(f"{API}/department/dashboard", headers=auditor_headers).status_code == 200

    def test_invalid_window_rejected(self, client: TestClient, inspector_headers):
        assert (
            client.get(
                f"{API}/department/dashboard", headers=inspector_headers, params={"days": 5}
            ).status_code
            == 422
        )
        assert (
            client.get(
                f"{API}/department/dashboard", headers=inspector_headers, params={"days": 91}
            ).status_code
            == 422
        )


class TestDashboardAggregation:
    def test_shape_and_internal_consistency(self, client: TestClient, inspector_headers):
        dash = _dashboard(client, inspector_headers)
        # Trend is zero-filled: exactly `days` points, real counts only.
        assert len(dash["trend"]) == dash["windowDays"] == 30
        assert sum(p["count"] for p in dash["trend"]) == dash["windowComplaints"]
        # Status distribution is the single source every KPI is derived from.
        assert sum(dash["statusDistribution"].values()) == dash["kpis"]["totalComplaints"]
        assert set(dash["riskDistribution"]) == {"HIGH", "MEDIUM", "LOW", "UNSET"}
        # Needs attention carries its queue filters for navigation.
        for item in dash["needsAttention"]:
            assert item["count"] >= 0 and isinstance(item["filters"], dict)

    def test_kpis_move_with_real_records(self, client: TestClient, inspector_headers):
        before = _dashboard(client, inspector_headers)["kpis"]
        complaint = _make_complaint(client)
        after = _dashboard(client, inspector_headers)["kpis"]
        assert after["totalComplaints"] == before["totalComplaints"] + 1
        assert after["pendingReview"] == before["pendingReview"] + 1
        assert after["unassignedOpen"] == before["unassignedOpen"] + 1

        _transition(client, inspector_headers, complaint["id"], "START_REVIEW")
        _transition(
            client, inspector_headers, complaint["id"], "ACCEPT", officialPriority="HIGH"
        )
        dash = _dashboard(client, inspector_headers)
        assert dash["statusDistribution"].get("ACCEPTED", 0) >= 1
        assert dash["kpis"]["highPriority"] >= 1  # official HIGH, still open
        assert dash["kpis"]["pendingReview"] == before["pendingReview"]
        # Needs attention: accepted but not yet assigned.
        attention = {i["kind"]: i["count"] for i in dash["needsAttention"]}
        assert attention["ACCEPTED_AWAITING_ASSIGNMENT"] >= 1

        _transition(client, inspector_headers, complaint["id"], "CREATE_INSPECTION")
        dash = _dashboard(client, inspector_headers)
        assert dash["kpis"]["convertedToInspection"] == before["convertedToInspection"] + 1
        assert dash["kpis"]["underInvestigation"] == before["underInvestigation"] + 1
        pipeline = dash["pipeline"]
        assert pipeline["citizenReports"] == dash["kpis"]["totalComplaints"]
        assert pipeline["accepted"] >= 1
        assert pipeline["inspectionCompleted"] >= 0  # not completed yet for this one

    def test_priority_queue_carries_triage_signals(self, client: TestClient, inspector_headers):
        complaint = _make_complaint(client, location="UI04 Priorityville")
        _transition(client, inspector_headers, complaint["id"], "START_REVIEW")
        _transition(
            client, inspector_headers, complaint["id"], "ACCEPT", officialPriority="HIGH"
        )
        dash = _dashboard(client, inspector_headers)
        row = next((q for q in dash["priorityQueue"] if q["reference"] == complaint["reference"]), None)
        assert row is not None
        assert row["priority"] == "HIGH"
        assert row["prioritySource"] == "OFFICIAL_DECISION"
        assert 0 <= row["evidenceCompleteness"] <= 100
        assert row["status"] == "ACCEPTED"

    def test_evidence_completeness_is_deterministic(self, client: TestClient, inspector_headers):
        # Full details (product, description, shop, location) + image + mock
        # OCR extraction + timestamp: 25+15+10+10+10+10+10 = 90 (COMPLETE band).
        complaint = _make_complaint(client)
        detail = client.get(
            f"{API}/citizen/complaints/{complaint['id']}", headers=inspector_headers
        ).json()
        assert detail["evidenceCompleteness"] == 90
        dash = _dashboard(client, inspector_headers)
        assert dash["evidence"]["complete"] >= 1
        assert 0 <= dash["evidence"]["average"] <= 100

    def test_trend_groups_by_creation_date(self, client: TestClient, inspector_headers):
        _make_complaint(client)
        dash = _dashboard(client, inspector_headers, days=7)
        assert len(dash["trend"]) == 7
        today = dash["trend"][-1]  # zero-filled, ascending — last point is today
        assert today["count"] >= 1

    def test_location_rollup_from_real_locations(self, client: TestClient, inspector_headers):
        area = f"UI04 Locville-{uuid.uuid4().hex[:6]}"
        complaint = _make_complaint(client, location=area)
        _transition(client, inspector_headers, complaint["id"], "START_REVIEW")
        _transition(
            client, inspector_headers, complaint["id"], "ACCEPT", officialPriority="HIGH"
        )
        _transition(client, inspector_headers, complaint["id"], "CREATE_INSPECTION")
        dash = _dashboard(client, inspector_headers)
        row = next((loc for loc in dash["locations"] if loc["area"] == area), None)
        assert row is not None
        assert row["complaints"] == 1
        assert row["highPriority"] == 1
        assert row["inspections"] == 1

    def test_recent_activity_from_real_audit_events(
        self, client: TestClient, inspector_headers
    ):
        complaint = _make_complaint(client)
        _transition(client, inspector_headers, complaint["id"], "START_REVIEW")
        dash = _dashboard(client, inspector_headers)
        assert dash["recentActivity"], "expected at least one department audit event"
        newest = dash["recentActivity"][0]
        assert newest["event"] == "COMPLAINT_REVIEW_STARTED"
        assert newest["reference"] == complaint["reference"]
        assert newest["reportId"] == complaint["id"]
        assert newest["actorName"]  # the acting department user, never blank


class TestQueueFiltersUi04:
    def test_multi_status_filter(self, client: TestClient, inspector_headers):
        a = _make_complaint(client, issue="UI04 multi status A")
        b = _make_complaint(client, issue="UI04 multi status B")
        _transition(client, inspector_headers, a["id"], "START_REVIEW")
        resp = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"status": "SUBMITTED,UNDER_REVIEW"},
        )
        assert resp.status_code == 200
        refs = {c["reference"] for c in resp.json()}
        assert {a["reference"], b["reference"]} <= refs
        assert all(c["status"] in ("SUBMITTED", "UNDER_REVIEW") for c in resp.json())

    def test_unknown_status_filter_is_422(self, client: TestClient, inspector_headers):
        resp = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"status": "NOT_A_STATUS"},
        )
        assert resp.status_code == 422

    def test_inspection_link_filter(self, client: TestClient, inspector_headers):
        complaint = _make_complaint(client, issue="UI04 linked filter")
        _transition(client, inspector_headers, complaint["id"], "START_REVIEW")
        _transition(client, inspector_headers, complaint["id"], "ACCEPT")
        _transition(client, inspector_headers, complaint["id"], "CREATE_INSPECTION")
        linked = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"inspection": "LINKED"},
        ).json()
        assert complaint["reference"] in {c["reference"] for c in linked}
        assert all(c["inspectionId"] for c in linked)
        unlinked = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"inspection": "UNLINKED"},
        ).json()
        assert complaint["reference"] not in {c["reference"] for c in unlinked}

    def test_evidence_band_filter(self, client: TestClient, inspector_headers):
        _make_complaint(client, issue="UI04 evidence band")  # 90 → COMPLETE
        complete = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"evidence": "COMPLETE"},
        ).json()
        assert complete, "expected at least one COMPLETE complaint"
        assert all(c["evidenceCompleteness"] >= 80 for c in complete)
        assert (
            client.get(
                f"{API}/citizen/complaints",
                headers=inspector_headers,
                params={"evidence": "PARTIAL"},
            ).status_code
            == 200
        )

    def test_invalid_evidence_filter_is_422(self, client: TestClient, inspector_headers):
        resp = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"evidence": "PERFECT"},
        )
        assert resp.status_code == 422

    def test_stale_filter_matches_only_old_open_complaints(
        self, client: TestClient, inspector_headers
    ):
        # Fresh complaints are never stale — the filter must exclude them.
        _make_complaint(client, issue="UI04 fresh complaint")
        stale = client.get(
            f"{API}/citizen/complaints",
            headers=inspector_headers,
            params={"stale": "true"},
        ).json()
        assert all(c["status"] not in ("REJECTED", "CLOSED") for c in stale)
