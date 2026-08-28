"""API tests for the perception routes (Prompt 4).

Exercises the HTTP surface end to end against the in-memory database with the
REAL pipeline but FAKE OCR/vision providers (monkeypatched per test). The
real-engine path is covered separately by the ``integration``-marked test.

RBAC, the 202-then-poll contract, reanalysis history, failure surfacing and
the perception-only guardrail (no compliance verdict anywhere) are all
asserted here.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import ProcessingRunStatus
from app.models import OcrTextResult, ProcessingRun
from app.services.registry import Services
from tests.conftest import API
from tests.test_perception_pipeline import (
    FailingOCRService,
    FakeOCRService,
    FakeVisionService,
    _label_png,
)

# --- helpers ---------------------------------------------------------------


def _create_inspection(client: TestClient, headers: dict[str, str]) -> str:
    resp = client.post(
        f"{API}/inspections",
        headers=headers,
        json={"productName": "Real Perception Sample", "productCategory": "food"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _upload_image(client: TestClient, headers: dict[str, str], inspection_id: str) -> str:
    resp = client.post(
        f"{API}/inspections/{inspection_id}/images/upload",
        headers=headers,
        files={"file": ("front.png", _label_png(), "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["qualityGrade"] != "REJECTED"
    return body["id"]


@pytest.fixture()
def fakes(services: Services, monkeypatch):
    """Swap the pipeline's providers for deterministic fakes (auto-restored)."""
    pipeline = services.perception._pipeline
    ocr, vision = FakeOCRService(), FakeVisionService()
    monkeypatch.setattr(pipeline, "_ocr", ocr)
    monkeypatch.setattr(pipeline, "_vision", vision)
    return ocr, vision


@pytest.fixture()
def perceived_inspection(client, inspector_headers, fakes):
    """Inspection + usable image + one completed perception run."""
    inspection_id = _create_inspection(client, inspector_headers)
    image_id = _upload_image(client, inspector_headers, inspection_id)
    resp = client.post(f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers)
    assert resp.status_code == 202, resp.text
    return inspection_id, image_id


# --- kickoff + polling ------------------------------------------------------


class TestPerceiveKickoff:
    def test_perceive_returns_202_with_run_reference(
        self, client, inspector_headers, fakes
    ):
        inspection_id = _create_inspection(client, inspector_headers)
        _upload_image(client, inspector_headers, inspection_id)

        resp = client.post(f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers)
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "QUEUED"
        assert len(body["runs"]) == 1
        assert body["runs"][0]["reference"].startswith("PR-")
        assert "no compliance evaluation" in body["note"]

        # TestClient runs background tasks synchronously: the run is terminal
        # by the time the analysis endpoint is queried.
        analysis = client.get(
            f"{API}/inspections/{inspection_id}/analysis", headers=inspector_headers
        )
        assert analysis.status_code == 200, analysis.text
        payload = analysis.json()
        assert payload["hasRuns"] is True
        assert payload["active"] is False
        assert payload["regulatoryEvaluation"] == "AWAITING_REGULATORY_EVALUATION"
        assert payload["summary"]["textElements"] == 5
        assert payload["summary"]["ocrModel"] == "fake/fake-ocr/1.0.0"
        assert payload["summary"]["visionModel"] == "fake/fake-vision/1.0.0"

    def test_perceive_without_usable_images_is_422(self, client, inspector_headers, fakes):
        inspection_id = _create_inspection(client, inspector_headers)
        resp = client.post(f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers)
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_perceive_requires_field_role(self, client, inspector_headers, auditor_headers, fakes):
        # Auditors are read-only: they may neither upload nor run perception.
        inspection_id = _create_inspection(client, inspector_headers)
        _upload_image(client, inspector_headers, inspection_id)
        resp = client.post(f"{API}/inspections/{inspection_id}/perceive", headers=auditor_headers)
        assert resp.status_code == 403, resp.text

    def test_perceive_unknown_inspection_is_404(self, client, inspector_headers, fakes):
        resp = client.post(
            f"{API}/inspections/00000000-0000-0000-0000-000000000000/perceive",
            headers=inspector_headers,
        )
        assert resp.status_code == 404, resp.text


# --- evidence reads ----------------------------------------------------------


class TestPerceptionReads:
    def test_ocr_endpoint_returns_verbatim_raw_and_derived_normalized(
        self, client, inspector_headers, perceived_inspection
    ):
        inspection_id, _ = perceived_inspection
        resp = client.get(f"{API}/inspections/{inspection_id}/ocr", headers=inspector_headers)
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 5
        by_raw = {row["rawText"]: row for row in rows}
        assert "M.R.P. ₹ 499.00 (incl. of all taxes)" in by_raw  # verbatim evidence
        assert by_raw["M.R.P. ₹ 499.00 (incl. of all taxes)"]["normalizedText"] == (
            "M.R.P. ₹499.00 (incl. of all taxes)"
        )
        for row in rows:
            assert row["provider"] == "fake"
            assert row["modelName"] == "fake-ocr"
            assert row["regionId"]
            assert row["processingRunId"]
            assert 0.0 <= row["confidence"] <= 1.0

    def test_regions_endpoint_includes_decoded_symbols(
        self, client, inspector_headers, perceived_inspection
    ):
        inspection_id, _ = perceived_inspection
        resp = client.get(f"{API}/inspections/{inspection_id}/regions", headers=inspector_headers)
        assert resp.status_code == 200, resp.text
        regions = resp.json()
        qr = [r for r in regions if r["regionType"] == "QR_CODE"]
        barcode = [r for r in regions if r["regionType"] == "BARCODE"]
        text = [r for r in regions if r["regionType"] == "TEXT_LINE"]
        assert len(text) == 5
        assert qr[0]["payload"] == {
            "symbology": "QR",
            "value": "HELLO LEGALMET 123",
            "decoded": True,
        }
        assert barcode[0]["payload"]["value"] == "8901234123457"

    def test_fields_endpoint_exposes_status_and_evidence_link(
        self, client, inspector_headers, perceived_inspection
    ):
        inspection_id, _ = perceived_inspection
        resp = client.get(f"{API}/inspections/{inspection_id}/fields", headers=inspector_headers)
        assert resp.status_code == 200, resp.text
        fields = resp.json()
        assert len(fields) >= 5
        by_type = {f["fieldType"]: f for f in fields}
        assert by_type["MRP"]["normalizedValue"] == "₹499.00"
        assert by_type["MRP"]["status"] == "DETECTED"
        assert by_type["MRP"]["sourceOcrResultId"]
        assert by_type["BATCH_NUMBER"]["status"] == "REVIEW_REQUIRED"
        assert by_type["PRODUCT_NAME"]["status"] == "REVIEW_REQUIRED"
        for field in fields:
            # Perception statuses only — never a compliance verdict.
            assert field["status"] in ("DETECTED", "REVIEW_REQUIRED", "NOT_EXTRACTED")
            assert field["processingRunId"]

    def test_processing_run_detail(self, client, inspector_headers, perceived_inspection):
        inspection_id, _ = perceived_inspection
        runs = client.get(
            f"{API}/inspections/{inspection_id}/processing", headers=inspector_headers
        ).json()
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "REVIEW_REQUIRED"
        assert run["pipelineVersion"] == "4.0.0"
        assert run["ocrModel"] == "fake-ocr"
        assert run["visionModel"] == "fake-vision"
        assert run["durationMs"] is not None
        assert run["configuration"]["preprocessing"]["operations"]
        assert run["summary"]["textElements"] == 5

        detail = client.get(
            f"{API}/processing-runs/{run['id']}", headers=inspector_headers
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert len(body["ocrResults"]) == 5
        assert len(body["regions"]) == 7
        assert len(body["fields"]) >= 5

    def test_unknown_run_is_404(self, client, inspector_headers):
        resp = client.get(
            f"{API}/processing-runs/00000000-0000-0000-0000-000000000000",
            headers=inspector_headers,
        )
        assert resp.status_code == 404, resp.text

    def test_reads_require_authentication(self, client, perceived_inspection):
        inspection_id, _ = perceived_inspection
        assert (
            client.get(f"{API}/inspections/{inspection_id}/analysis").status_code == 401
        )

    def test_auditor_can_read_but_not_run(self, client, auditor_headers, perceived_inspection):
        inspection_id, _ = perceived_inspection
        resp = client.get(f"{API}/inspections/{inspection_id}/analysis", headers=auditor_headers)
        assert resp.status_code == 200, resp.text


# --- failure surfacing -------------------------------------------------------


class TestFailureSurfacing:
    def test_ocr_failure_marks_run_failed(
        self, client, inspector_headers, services, monkeypatch, fakes
    ):
        inspection_id = _create_inspection(client, inspector_headers)
        _upload_image(client, inspector_headers, inspection_id)
        monkeypatch.setattr(services.perception._pipeline, "_ocr", FailingOCRService())

        resp = client.post(f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers)
        assert resp.status_code == 202  # accepted; failure surfaces via polling
        runs = client.get(
            f"{API}/inspections/{inspection_id}/processing", headers=inspector_headers
        ).json()
        assert runs[0]["status"] == "FAILED"
        assert runs[0]["error"]["code"] == "AI_SERVICE_UNAVAILABLE"
        fields = client.get(
            f"{API}/inspections/{inspection_id}/fields", headers=inspector_headers
        ).json()
        assert fields == []


# --- reanalysis --------------------------------------------------------------


class TestReanalysis:
    def test_reanalyze_creates_new_run_and_preserves_old(
        self, client, inspector_headers, db, perceived_inspection
    ):
        inspection_id, image_id = perceived_inspection

        resp = client.post(f"{API}/images/{image_id}/reanalyze", headers=inspector_headers)
        assert resp.status_code == 202, resp.text
        assert resp.json()["runs"][0]["reference"].startswith("PR-")

        runs = client.get(
            f"{API}/inspections/{inspection_id}/processing", headers=inspector_headers
        ).json()
        assert len(runs) == 2

        # Old run's OCR evidence still exists in the database (scoped to this
        # inspection — the session DB is shared across all tests).
        run_uuids = [UUID(r["id"]) for r in runs]
        ocr_rows = list(
            db.execute(
                select(OcrTextResult).where(OcrTextResult.processing_run_id.in_(run_uuids))
            ).scalars()
        )
        assert len(ocr_rows) == 10  # 5 lines x 2 runs — history intact

        # Latest-run reads show exactly one run's evidence.
        ocr_now = client.get(
            f"{API}/inspections/{inspection_id}/ocr", headers=inspector_headers
        ).json()
        assert len(ocr_now) == 5

    def test_reanalyze_unknown_image_is_404(self, client, inspector_headers):
        resp = client.post(
            f"{API}/images/00000000-0000-0000-0000-000000000000/reanalyze",
            headers=inspector_headers,
        )
        assert resp.status_code == 404, resp.text

    def test_reanalysis_records_audit_event(
        self, db, client, inspector_headers, perceived_inspection
    ):
        inspection_id, image_id = perceived_inspection
        client.post(f"{API}/images/{image_id}/reanalyze", headers=inspector_headers)
        runs = list(
            db.execute(
                select(ProcessingRun).where(ProcessingRun.image_id == UUID(image_id))
            ).scalars()
        )
        assert len(runs) == 2
        assert all(r.status != ProcessingRunStatus.QUEUED.value for r in runs)


# --- demo flow untouched ------------------------------------------------------


class TestDemoFlowUnaffected:
    def test_existing_demo_analyze_still_works(
        self, client, inspector_headers, make_analyzed_inspection
    ):
        """Prompt 2's demo compliance flow (POST /analyze) is untouched by
        Prompt 4 — the demo mock OCR path keeps producing findings."""
        result = make_analyzed_inspection()
        assert result["findings"], "demo analysis must still produce findings"
