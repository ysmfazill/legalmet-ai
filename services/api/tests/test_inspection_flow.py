"""End-to-end inspection lifecycle over the HTTP API.

Mock perception/quality are seeded per run, so this test asserts the lifecycle
and structural invariants (valid states, review effects, audit trail) rather
than a specific compliance verdict.
"""
from __future__ import annotations

from app.core.enums import ComplianceStatus
from tests.conftest import API, TINY_PNG_B64

_VALID_STATUSES = {s.value for s in ComplianceStatus}


def test_create_requires_auth(client):
    resp = client.post(f"{API}/inspections", json={"productName": "X", "productCategory": "food"})
    assert resp.status_code == 401


def test_full_inspection_lifecycle(client, inspector_headers):
    # 1. Create
    created = client.post(
        f"{API}/inspections",
        headers=inspector_headers,
        json={"productName": "DEMO Biscuits", "productCategory": "food"},
    )
    assert created.status_code == 201, created.text
    inspection = created.json()
    inspection_id = inspection["id"]
    assert inspection["referenceNo"].startswith("LM-")
    assert inspection["status"] == "CREATED"
    assert inspection["isDemo"] is True

    # 2. Upload an image
    img = client.post(
        f"{API}/inspections/{inspection_id}/images",
        headers=inspector_headers,
        json={
            "originalFilename": "front.png",
            "mimeType": "image/png",
            "imageType": "FRONT",
            "contentBase64": TINY_PNG_B64,
            "width": 900,
            "height": 700,
        },
    )
    assert img.status_code == 201, img.text
    assert img.json()["qualityStatus"]  # a verdict was produced

    # 3. Analyze (context date selects the v2 rule set)
    analyzed = client.post(
        f"{API}/inspections/{inspection_id}/analyze",
        headers=inspector_headers,
        json={"contextDate": "2026-06-01"},
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["status"] == "ANALYZED"
    counts = body["findingCounts"]
    assert counts["total"] >= 1

    # 4. Findings all carry a valid, honest compliance state (never PASS/FAIL).
    findings_resp = client.get(f"{API}/inspections/{inspection_id}/findings", headers=inspector_headers)
    assert findings_resp.status_code == 200
    # This endpoint returns a bare list, not a paginated {items:[...]} object.
    findings = findings_resp.json()
    assert len(findings) == counts["total"]
    for finding in findings:
        assert finding["status"] in _VALID_STATUSES
        assert 0.0 <= finding["confidence"] <= 1.0
        assert finding["rationale"]

    # 5. Human-in-the-loop: accepting a finding marks it reviewed.
    first_id = findings[0]["id"]
    review = client.post(
        f"{API}/findings/{first_id}/review",
        headers=inspector_headers,
        json={"action": "ACCEPT", "note": "Looks correct."},
    )
    assert review.status_code == 200, review.text
    assert review.json()["isReviewed"] is True

    # 6. CORRECT without a corrected status is rejected (data-integrity guard).
    bad = client.post(
        f"{API}/findings/{first_id}/review",
        headers=inspector_headers,
        json={"action": "CORRECT"},
    )
    assert bad.status_code >= 400
    assert "error" in bad.json()

    # 7. Audit trail recorded the lifecycle.
    audit = client.get(f"{API}/inspections/{inspection_id}/audit", headers=inspector_headers)
    assert audit.status_code == 200, audit.text
    # This endpoint returns a bare list of audit events, not a paginated object.
    event_types = {e["eventType"] for e in audit.json()}
    assert "INSPECTION_CREATED" in event_types
    assert "ANALYSIS_COMPLETED" in event_types
    assert "REVIEW_RECORDED" in event_types


def test_dashboard_reflects_activity(client, inspector_headers, make_analyzed_inspection):
    make_analyzed_inspection()
    resp = client.get(f"{API}/analytics/dashboard", headers=inspector_headers)
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["inspections"]["total"] >= 1
    assert summary["findings"]["total"] >= 1
    assert "generatedAt" in summary


def test_review_queue_is_available(client, inspector_headers):
    resp = client.get(f"{API}/review/queue", headers=inspector_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
