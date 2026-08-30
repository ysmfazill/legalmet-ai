"""PROMPT 9 Phase 1 — END-TO-END GOLDEN PATH over the REAL pipeline.

One complete flow, every stage persisted and asserted:

    REAL package image (tests/dataset, rendered locally with Pillow)
    → intake upload + quality gate
    → REAL PaddleOCR + REAL OpenCV vision (no mocks anywhere)
    → deterministic field extraction
    → regulatory requirement resolution (seeded research-grade fixture)
    → deterministic rule evaluation
    → finding
    → evidence graph
    → human review + correction
    → re-evaluation (new evaluation, history preserved)
    → final human decision
    → audit trail

NO FAKE AI: nothing in this module monkeypatches the perception pipeline.
The only deterministic fixtures are the regulatory/rule seeds (the same ones a
started server uses) and the label pixels themselves.

Marked ``integration`` (excluded from the default suite) because it runs the
real CPU OCR engine — expect ~tens of seconds, minutes on a cold model cache.

    pytest -m integration tests/test_golden_e2e_integration.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_services_dep, get_settings_dep
from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.services.registry import Services, build_services
from tests.conftest import API, INSPECTOR_EMAIL, INSPECTOR_PASSWORD

pytestmark = pytest.mark.integration

DATASET_DIR = Path(__file__).resolve().parent / "dataset"
GOLDEN_IMAGE = DATASET_DIR / "images" / "food-clean-001.png"
MANIFEST = DATASET_DIR / "manifest.json"

# The exact strings rendered onto the golden label's pixels (generator source).
GOLDEN_LABEL_SUBSTRINGS = ["net qty", "250 g", "149", "batch", "india"]


def _manifest_record(record_id: str) -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return next(r for r in data["images"] if r["id"] == record_id)


@pytest.fixture(scope="module")
def golden_record() -> dict:
    return _manifest_record("FOOD-CLEAN-001")


@pytest.fixture(scope="module")
def golden_image_bytes() -> bytes:
    assert GOLDEN_IMAGE.exists(), "run tests/dataset/generate.py first"
    return GOLDEN_IMAGE.read_bytes()


@pytest.fixture(scope="module")
def paddle_settings(test_settings: Settings) -> Settings:
    """Same coherent test settings, but with the REAL OCR backend on."""
    return test_settings.model_copy(
        update={
            "perception_ocr_backend": "paddle",
            "perception_ocr_timeout_seconds": 600.0,
        }
    )


@pytest.fixture(scope="module")
def paddle_services(
    paddle_settings: Settings, session_factory
) -> Services:
    # Real PaddleOCR + OpenCV, sharing the SAME in-memory engine the API
    # overrides use (schema + seeds are already created by the session
    # autouse fixture in conftest).
    return build_services(paddle_settings, session_factory=session_factory)


@pytest.fixture()
def paddle_client(
    paddle_settings: Settings, paddle_services: Services, session_factory
) -> TestClient:
    application = create_app(paddle_settings)

    def _override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_settings_dep] = lambda: paddle_settings
    application.dependency_overrides[get_services_dep] = lambda: paddle_services
    yield TestClient(application)
    application.dependency_overrides.clear()


@pytest.fixture()
def inspector_headers(paddle_client: TestClient) -> dict[str, str]:
    resp = paddle_client.post(
        f"{API}/auth/login",
        json={"email": INSPECTOR_EMAIL, "password": INSPECTOR_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['accessToken']}"}


class TestGoldenPathRealPipeline:
    def test_real_image_to_decision_full_path(
        self, paddle_client, inspector_headers, golden_image_bytes, golden_record
    ):
        client = paddle_client

        # --- 1. Create the inspection -------------------------------------
        create = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": "SUNRISE CRUNCHY MASALA 250g", "productCategory": "food"},
        )
        assert create.status_code == 201, create.text
        inspection_id = create.json()["id"]

        # --- 2. Upload the REAL image (intake + quality gate) --------------
        upload = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("food-clean-001.png", golden_image_bytes, "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        assert upload.status_code == 201, upload.text
        image = upload.json()
        assert image["qualityGrade"] in ("EXCELLENT", "GOOD", "ACCEPTABLE"), image
        assert image["checksum"], "intake must record the original checksum"

        # --- 3. REAL perception run ----------------------------------------
        perceive = client.post(
            f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers
        )
        assert perceive.status_code == 202, perceive.text

        runs = client.get(
            f"{API}/inspections/{inspection_id}/processing", headers=inspector_headers
        ).json()
        assert len(runs) == 1
        run = runs[0]
        # Persisted observability fields (Phase 19): provider, model, version,
        # pipeline version, duration, terminal state.
        assert run["status"] in ("COMPLETED", "REVIEW_REQUIRED", "PARTIAL"), run
        assert run["ocrProvider"] == "PaddlePaddle", run
        assert run["ocrModel"] == "paddleocr-pp-ocrv5", run
        assert run["ocrVersion"], run
        assert run["pipelineVersion"], run
        assert run["durationMs"] and run["durationMs"] > 0
        assert run["startedAt"] and run["completedAt"]

        # --- 4. REAL OCR rows: recognition off real pixels ------------------
        ocr_rows = client.get(
            f"{API}/inspections/{inspection_id}/ocr", headers=inspector_headers
        ).json()
        assert ocr_rows, "real OCR returned no text"
        joined = " ".join(row["rawText"] for row in ocr_rows).lower()
        for needle in GOLDEN_LABEL_SUBSTRINGS:  # strings physically on the label
            assert needle in joined, f"real OCR missed {needle!r}: {joined!r}"
        for row in ocr_rows:
            assert 0.0 <= row["confidence"] <= 1.0
            assert row["bbox"]["x"] >= 0.0 and row["bbox"]["width"] > 0.0
            assert row["provider"] == "PaddlePaddle"

        # --- 5. Fields extracted deterministically from the REAL OCR --------
        fields = client.get(
            f"{API}/inspections/{inspection_id}/fields", headers=inspector_headers
        ).json()
        by_type = {f["fieldType"]: f for f in fields}
        assert "NET_QUANTITY" in by_type, f"expected NET_QUANTITY, got {by_type.keys()}"
        net_qty = by_type["NET_QUANTITY"]
        # The manifest records what is physically printed on the label.
        assert "250" in (net_qty["normalizedValue"] or net_qty["rawText"])
        assert "MRP" in by_type, f"expected MRP, got {by_type.keys()}"
        mrp_field_id = by_type["MRP"]["id"]
        mrp_original_raw = by_type["MRP"]["rawText"]
        # Every extracted field traces back to a REAL OCR row.
        for field in fields:
            if field.get("sourceOcrResultId"):
                assert any(r["id"] == field["sourceOcrResultId"] for r in ocr_rows)

        # --- 6. Regulatory evaluation over the real fields ------------------
        evaluate = client.post(
            f"{API}/inspections/{inspection_id}/evaluate", headers=inspector_headers
        )
        assert evaluate.status_code == 200, evaluate.text
        first_evaluation_id = evaluate.json()["evaluation"]["id"]
        findings = client.get(
            f"{API}/inspections/{inspection_id}/compliance/findings",
            headers=inspector_headers,
        ).json()
        assert findings, "engine produced no findings over the real extraction"
        for finding in findings:
            assert finding["reviewState"] == "PENDING_REVIEW"
            # Frozen regulatory provenance (requirement + version identity).
            prov = finding["provenance"]
            assert prov.get("requirementCode"), finding
            assert prov.get("versionId"), finding
            assert prov.get("effectiveFrom"), finding

        # --- 7. Evidence graph BEFORE any human action: AI/SYSTEM only ------
        graph = client.get(
            f"{API}/inspections/{inspection_id}/evidence-graph", headers=inspector_headers
        ).json()
        origins = {n["type"]: n["metadata"].get("origin") for n in graph["nodes"]}
        assert origins.get("EXTRACTED_FIELD") == "AI"
        assert "FIELD_CORRECTION" not in origins  # no human action yet
        assert "INSPECTION_DECISION" not in origins

        # --- 8. Human correction (append-only; original preserved) -----------
        correction = client.post(
            f"{API}/fields/{mrp_field_id}/correct",
            headers=inspector_headers,
            json={
                "correctedValue": "M.R.P. Rs. 149.00 (inclusive of all taxes)",
                "reason": "Inspector re-read the physical label; OCR dropped a digit.",
            },
        )
        assert correction.status_code == 200, correction.text
        review = client.get(
            f"{API}/fields/{mrp_field_id}/review", headers=inspector_headers
        ).json()
        # The ORIGINAL AI reading survives the correction untouched.
        assert review["originalRawText"] == mrp_original_raw
        assert review["correctedValue"] == "M.R.P. Rs. 149.00 (inclusive of all taxes)"
        assert review["correctionCount"] == 1
        assert review["correctedBy"], "corrected_by must be persisted"

        # --- 9. Re-evaluation: NEW evaluation, history intact ---------------
        reevaluate = client.post(
            f"{API}/inspections/{inspection_id}/evaluate", headers=inspector_headers
        )
        assert reevaluate.status_code == 200, reevaluate.text
        second_evaluation_id = reevaluate.json()["evaluation"]["id"]
        assert second_evaluation_id != first_evaluation_id
        # The first evaluation is still fully queryable (historical record).
        first_eval = client.get(
            f"{API}/compliance/evaluations/{first_evaluation_id}",
            headers=inspector_headers,
        )
        assert first_eval.status_code == 200
        assert first_eval.json()["id"] == first_evaluation_id

        # --- 10. Human review of the findings + final decision ---------------
        latest = [
            f
            for f in client.get(
                f"{API}/inspections/{inspection_id}/compliance/findings",
                headers=inspector_headers,
            ).json()
            if f["evaluationId"] == second_evaluation_id
        ]
        assert latest, "re-evaluation produced no findings"
        for finding in latest:
            resp = client.post(
                f"{API}/compliance/findings/{finding['id']}/review",
                headers=inspector_headers,
                json={"action": "CONFIRM"},
            )
            assert resp.status_code == 200, resp.text
        decision = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All declarations verified on the label."},
        )
        # COMPLIANT requires the gate to be open (no unresolved critical findings).
        assert decision.status_code == 200, decision.text
        assert decision.json()["decision"] == "COMPLIANT"
        assert decision.json()["decidedBy"], "decided_by must be persisted"

        # --- 11. Audit trail: every human action recorded --------------------
        audit = client.get(
            f"{API}/inspections/{inspection_id}/audit", headers=inspector_headers
        ).json()
        event_types = {e["eventType"] for e in audit}
        for expected in (
            "PERCEPTION_STARTED",
            "PERCEPTION_COMPLETED",
            "FIELD_CORRECTED",
            "FINDING_CONFIRMED",
            "DECISION_SUBMITTED",
        ):
            assert expected in event_types, f"missing audit event {expected}: {event_types}"
        # System events (perception pipeline, engine) have no actor; every
        # HUMAN action event must carry one.
        human_event_types = {
            "FIELD_CORRECTED", "FINDING_CONFIRMED", "FINDING_REJECTED",
            "FINDING_OVERRIDDEN", "FINDING_ESCALATED", "DECISION_SUBMITTED",
            "DECISION_CHANGED", "SUPERVISOR_REVIEWED",
        }
        for event in audit:
            if event["eventType"] in human_event_types:
                assert event.get("actorId"), f"human event without actor: {event}"
            assert "password" not in json.dumps(event).lower()

        # --- 12. Final evidence graph: AI and HUMAN nodes coexist -------------
        graph = client.get(
            f"{API}/inspections/{inspection_id}/evidence-graph", headers=inspector_headers
        ).json()
        node_meta = {n["type"]: n["metadata"] for n in graph["nodes"]}
        assert node_meta["EXTRACTED_FIELD"].get("origin") == "AI"
        assert node_meta["FIELD_CORRECTION"].get("origin") == "HUMAN"
        assert node_meta["INSPECTION_DECISION"].get("origin") == "HUMAN"
        edge_types = {e["type"] for e in graph["edges"]}
        assert "FIELD_CORRECTION_CORRECTS_FIELD" in edge_types
        assert "DECISION_FOR_INSPECTION" in edge_types

    def test_poor_quality_image_is_gated_not_a_legal_verdict(
        self, paddle_client, inspector_headers
    ):
        """The tiny-resolution dataset image is refused at INTAKE (below the
        400x400 minimum) — a perception-safety signal, never a compliance
        verdict. The inspection is left with NO compliance conclusion."""
        client = paddle_client
        tiny = (DATASET_DIR / "images" / "food-tinyres-013.png").read_bytes()
        create = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": "Tiny resolution test", "productCategory": "food"},
        )
        inspection_id = create.json()["id"]
        upload = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("tiny.png", tiny, "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        # Rejected before storage: sanitized error, no stack trace, and the
        # payload names the violated limit.
        assert upload.status_code == 400, upload.text
        error = upload.json()["error"]
        assert error["code"] == "INVALID_IMAGE"
        assert error["details"]["minWidth"] == 400
        assert error["details"]["width"] == 110
        # The inspection exists but was never evaluated — the quality gate
        # must NOT silently produce a compliance verdict.
        compliance = client.get(
            f"{API}/inspections/{inspection_id}/compliance", headers=inspector_headers
        ).json()
        assert compliance["status"] == "NOT_EVALUATED"
