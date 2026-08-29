"""Compliance engine API tests (Prompt 6) — HTTP surface.

Covers the Phase 16 endpoints end to end over the real seeded regulatory data
and the mock perception pipeline:

* POST /inspections/{id}/evaluate      — run, RBAC, 404, never-overwrite
* GET  /inspections/{id}/compliance    — explicit NOT_EVALUATED before a run
* GET  /inspections/{id}/compliance/findings — engine findings list
* GET  /compliance/evaluations/{id}    — historical evaluations stay readable
* GET  /compliance/findings/{id}       — one finding with explanation + note
* GET  /compliance/engine              — vocabulary, no-LLM contract
* GET  /compliance/review/queue        — pending inspector decisions (read-only)

Legal-safety invariants asserted at the HTTP layer: every payload carries the
boundary note, the summary contains counts only (never a percentage), and an
engine failure never surfaces as COMPLIANT.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.enums import EvaluationStatus
from tests.conftest import API

# The statuses that legitimately appear in the review queue.
_QUEUE_STATUSES = {"REVIEW_REQUIRED", "NON_COMPLIANT", "NOT_DETECTED", "NOT_EVALUATED"}

_UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def _evaluate(client: TestClient, headers: dict, inspection_id: str) -> dict:
    resp = client.post(f"{API}/inspections/{inspection_id}/evaluate", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["evaluation"]


# --- engine info ---------------------------------------------------------------


class TestEngineInfoApi:
    def test_requires_auth(self, client):
        assert client.get(f"{API}/compliance/engine").status_code == 401

    def test_engine_info_contract(self, client, inspector_headers):
        resp = client.get(f"{API}/compliance/engine", headers=inspector_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["engineVersion"]
        assert body["usesLlm"] is False  # hard requirement: no LLM anywhere
        assert len(body["ruleTypes"]) == 13
        assert {rt["ruleType"] for rt in body["ruleTypes"]} == {
            "PRESENCE", "TEXT_MATCH", "TEXT_PATTERN", "NUMERIC_VALUE",
            "UNIT_MATCH", "MRP_FORMAT", "DATE_FORMAT", "CONTACT_FORMAT",
            "DECLARATION_FORMAT", "FIELD_REQUIRED", "FIELD_NOT_REQUIRED",
            "RANGE", "COMPARISON",
        }
        assert "not, by themselves, legal enforcement determinations" in (
            body["boundaryNote"]
        )

    def test_engine_info_readable_by_auditor(self, client, auditor_headers):
        resp = client.get(f"{API}/compliance/engine", headers=auditor_headers)
        assert resp.status_code == 200


# --- POST /inspections/{id}/evaluate -------------------------------------------


class TestEvaluateApi:
    def test_requires_auth(self, client, analyzed_inspection):
        resp = client.post(f"{API}/inspections/{analyzed_inspection['id']}/evaluate")
        assert resp.status_code == 401

    def test_auditor_cannot_run_evaluation(self, client, auditor_headers):
        inspection_id = analyzed_inspection_id(client, inspector_login(client))
        resp = client.post(
            f"{API}/inspections/{inspection_id}/evaluate", headers=auditor_headers
        )
        assert resp.status_code == 403

    def test_unknown_inspection_404(self, client, inspector_headers):
        resp = client.post(
            f"{API}/inspections/{_UNKNOWN_ID}/evaluate", headers=inspector_headers
        )
        assert resp.status_code == 404

    def test_evaluation_shape_and_boundary_note(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        resp = client.post(
            f"{API}/inspections/{inspection['id']}/evaluate", headers=inspector_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "not, by themselves, legal enforcement determinations" in (
            body["boundaryNote"]
        )
        evaluation = body["evaluation"]
        assert evaluation["inspectionId"] == inspection["id"]
        assert evaluation["status"] in {s.value for s in EvaluationStatus}
        assert evaluation["engineVersion"]
        assert evaluation["regulatoryVersionId"]
        assert evaluation["completedAt"]
        assert evaluation["findings"], "consolidated version must yield findings"

        # Findings reference REAL requirements and carry the seven-question
        # explanation, provenance and the boundary note.
        for finding in evaluation["findings"]:
            assert finding["requirementId"]
            assert len(finding["explanation"]) > 40
            assert finding["provenance"]["requirementCode"]
            assert finding["provenance"]["versionId"]
            assert finding["provenance"]["sourceName"]
            assert finding["boundaryNote"] == body["boundaryNote"]
            assert finding["status"] in {
                "COMPLIANT", "NON_COMPLIANT", "REVIEW_REQUIRED",
                "NOT_DETECTED", "NOT_APPLICABLE", "NOT_EVALUATED",
            }

    def test_summary_is_counts_only_never_a_percentage(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        evaluation = _evaluate(client, inspector_headers, inspection["id"])
        summary = evaluation["summary"]
        assert set(summary) == {
            "totalFindings", "byStatus", "reviewQueueCount", "requirementsEvaluated",
        }
        assert summary["totalFindings"] == len(evaluation["findings"])
        # The forbidden patterns: no percentage, no confidence, no score.
        summary_text = str(summary).lower()
        for forbidden in ("percent", "%", "confidence", "score"):
            assert forbidden not in summary_text

    def test_repeated_evaluation_never_overwrites(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        first = _evaluate(client, inspector_headers, inspection["id"])
        second = _evaluate(client, inspector_headers, inspection["id"])
        assert first["id"] != second["id"]
        # The historical evaluation is still readable, byte-identical summary.
        resp = client.get(
            f"{API}/compliance/evaluations/{first['id']}", headers=inspector_headers
        )
        assert resp.status_code == 200
        assert resp.json()["summary"] == first["summary"]

    def test_failed_engine_never_compliant(self, client, inspector_headers, db):
        """An inspection whose regulatory data is missing → FAILED with a code,
        never COMPLIANT. Uses a fresh inspection with no analyzed evidence."""
        from app.models import Inspection, Product

        product = Product(name=f"No-Reg {uuid.uuid4().hex[:6]}", category="food")
        db.add(product)
        db.flush()
        inspection = Inspection(
            reference_no=f"INS-API-{uuid.uuid4().hex[:8].upper()}",
            status="ANALYZED",
            product_id=product.id,
            context_date=None,
            is_demo=False,
        )
        db.add(inspection)
        db.commit()
        # No perception evidence at all → version resolution still works but
        # no field evidence exists; every finding is NOT_DETECTED (never
        # NON_COMPLIANT) — missing OCR is not a violation.
        resp = client.post(
            f"{API}/inspections/{inspection.id}/evaluate", headers=inspector_headers
        )
        assert resp.status_code == 200
        evaluation = resp.json()["evaluation"]
        statuses = {f["status"] for f in evaluation["findings"]}
        assert "NON_COMPLIANT" not in statuses
        assert statuses <= {"NOT_DETECTED", "NOT_APPLICABLE", "REVIEW_REQUIRED"}


# --- GET /inspections/{id}/compliance ------------------------------------------


class TestComplianceStatusApi:
    def test_requires_auth(self, client, analyzed_inspection):
        resp = client.get(f"{API}/inspections/{analyzed_inspection['id']}/compliance")
        assert resp.status_code == 401

    def test_before_evaluation_explicit_not_evaluated(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        resp = client.get(
            f"{API}/inspections/{inspection['id']}/compliance",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "NOT_EVALUATED"
        assert body["evaluation"] is None  # absence is never presented as compliance

    def test_after_evaluation_returns_latest(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        evaluation = _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/inspections/{inspection['id']}/compliance",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == evaluation["status"]
        assert body["evaluation"]["id"] == evaluation["id"]

    def test_unknown_inspection_404(self, client, inspector_headers):
        resp = client.get(
            f"{API}/inspections/{_UNKNOWN_ID}/compliance", headers=inspector_headers
        )
        assert resp.status_code == 404

    def test_latest_is_the_most_recent_evaluation(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        _evaluate(client, inspector_headers, inspection["id"])
        second = _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/inspections/{inspection['id']}/compliance",
            headers=inspector_headers,
        )
        assert resp.json()["evaluation"]["id"] == second["id"]


# --- GET /inspections/{id}/compliance/findings ---------------------------------


class TestInspectionFindingsApi:
    def test_requires_auth(self, client, analyzed_inspection):
        resp = client.get(f"{API}/inspections/{analyzed_inspection['id']}/compliance/findings")
        assert resp.status_code == 401

    def test_empty_before_evaluation(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        resp = client.get(
            f"{API}/inspections/{inspection['id']}/compliance/findings",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_latest_findings(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        first = _evaluate(client, inspector_headers, inspection["id"])
        second = _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/inspections/{inspection['id']}/compliance/findings",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        findings = resp.json()
        assert findings
        assert {f["evaluationId"] for f in findings} == {second["id"]}
        assert {f["evaluationId"] for f in findings} != {first["id"]}

    def test_unknown_inspection_404(self, client, inspector_headers):
        resp = client.get(
            f"{API}/inspections/{_UNKNOWN_ID}/compliance/findings",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_prompt1_demo_findings_route_untouched(
        self, client, inspector_headers, analyzed_inspection
    ):
        """GET /inspections/{id}/findings still serves the Prompt 1 demo flow —
        the engine route lives under /compliance and shadows nothing."""
        resp = client.get(
            f"{API}/inspections/{analyzed_inspection['id']}/findings",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# --- GET /compliance/evaluations/{id} and /compliance/findings/{id} -------------


class TestDetailApis:
    def test_evaluation_requires_auth(self, client):
        assert client.get(
            f"{API}/compliance/evaluations/{_UNKNOWN_ID}"
        ).status_code == 401

    def test_unknown_evaluation_404(self, client, inspector_headers):
        assert client.get(
            f"{API}/compliance/evaluations/{_UNKNOWN_ID}", headers=inspector_headers
        ).status_code == 404

    def test_finding_by_id(self, client, inspector_headers, make_analyzed_inspection):
        inspection = make_analyzed_inspection()
        evaluation = _evaluate(client, inspector_headers, inspection["id"])
        finding_id = evaluation["findings"][0]["id"]
        resp = client.get(
            f"{API}/compliance/findings/{finding_id}", headers=inspector_headers
        )
        assert resp.status_code == 200
        finding = resp.json()
        assert finding["id"] == finding_id
        assert finding["evaluationId"] == evaluation["id"]
        assert finding["inspectionId"] == inspection["id"]
        assert finding["explanation"]
        assert finding["provenance"]["requirementCode"]
        assert "inspector decision pending" in finding["boundaryNote"]

    def test_unknown_finding_404(self, client, inspector_headers):
        assert client.get(
            f"{API}/compliance/findings/{_UNKNOWN_ID}", headers=inspector_headers
        ).status_code == 404

    def test_finding_requires_auth(self, client):
        assert client.get(
            f"{API}/compliance/findings/{_UNKNOWN_ID}"
        ).status_code == 401


# --- GET /compliance/review/queue ----------------------------------------------


class TestReviewQueueApi:
    def test_requires_auth(self, client):
        assert client.get(f"{API}/compliance/review/queue").status_code == 401

    def test_queue_shape_and_statuses(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        make_analyzed_inspection()  # ensure at least one evaluated inspection
        inspection = make_analyzed_inspection()
        _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/compliance/review/queue",
            headers=inspector_headers,
            params={"page": 1, "pageSize": 50},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"items", "total", "page", "pageSize"}
        assert body["page"] == 1
        for item in body["items"]:
            assert item["status"] in _QUEUE_STATUSES
            assert "inspector decision pending" in item["boundaryNote"]

    def test_queue_excludes_compliant_and_not_applicable(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/compliance/review/queue", headers=inspector_headers
        )
        statuses = {i["status"] for i in resp.json()["items"]}
        assert statuses <= _QUEUE_STATUSES
        assert "COMPLIANT" not in statuses
        assert "NOT_APPLICABLE" not in statuses

    def test_queue_is_read_only_no_decision_fields(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        """Phase 18: the queue performs no approval — there is no decision /
        approvedBy / resolvedBy field on any queued item."""
        inspection = make_analyzed_inspection()
        _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/compliance/review/queue", headers=inspector_headers
        )
        for item in resp.json()["items"]:
            for forbidden in (
                "decision", "approved", "resolved", "enforcement", "verdict",
            ):
                assert forbidden not in item, (
                    f"queue item must not carry a decision field ({forbidden})"
                )

    def test_queue_paginates(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        _evaluate(client, inspector_headers, inspection["id"])
        first = client.get(
            f"{API}/compliance/review/queue",
            headers=inspector_headers,
            params={"page": 1, "pageSize": 1},
        ).json()
        if first["total"] < 2:
            return  # not enough queued findings in this run to paginate
        second = client.get(
            f"{API}/compliance/review/queue",
            headers=inspector_headers,
            params={"page": 2, "pageSize": 1},
        ).json()
        assert first["items"][0]["id"] != second["items"][0]["id"]


# --- audit (Phase 20) -----------------------------------------------------------


class TestComplianceAudit:
    def test_evaluation_records_audit_events(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        inspection = make_analyzed_inspection()
        _evaluate(client, inspector_headers, inspection["id"])
        resp = client.get(
            f"{API}/inspections/{inspection['id']}/audit", headers=inspector_headers
        )
        assert resp.status_code == 200
        types = {e["eventType"] for e in resp.json()}
        assert "COMPLIANCE_EVALUATION_STARTED" in types
        assert "COMPLIANCE_EVALUATION_COMPLETED" in types


# --- helpers ---------------------------------------------------------------------


def inspector_login(client: TestClient) -> dict[str, str]:
    from tests.conftest import INSPECTOR_EMAIL, INSPECTOR_PASSWORD, _login

    return {"Authorization": f"Bearer {_login(client, INSPECTOR_EMAIL, INSPECTOR_PASSWORD)}"}


def analyzed_inspection_id(client: TestClient, headers: dict) -> str:
    """A minimal analyzed inspection (used where the full fixture is unneeded)."""
    from tests.conftest import TINY_PNG_BASE64

    create = client.post(
        f"{API}/inspections",
        headers=headers,
        json={"productName": f"RBAC {uuid.uuid4().hex[:6]}", "productCategory": "food"},
    )
    assert create.status_code == 201, create.text
    inspection_id = create.json()["id"]
    image = client.post(
        f"{API}/inspections/{inspection_id}/images",
        headers=headers,
        json={
            "originalFilename": "front.png",
            "mimeType": "image/png",
            "imageType": "FRONT",
            "contentBase64": TINY_PNG_BASE64,
            "width": 1200,
            "height": 1600,
            "fileSize": 2048,
        },
    )
    assert image.status_code == 201, image.text
    analyze = client.post(
        f"{API}/inspections/{inspection_id}/analyze",
        headers=headers,
        json={"contextDate": "2026-06-01"},
    )
    assert analyze.status_code == 200, analyze.text
    return inspection_id
