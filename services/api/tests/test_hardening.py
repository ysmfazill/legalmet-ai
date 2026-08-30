"""PROMPT 9 hardening tests (Phases 5–8) — fast, default suite.

Covers the resource-safety and reliability guarantees added/strengthened by
Prompt 9:

* Phase 5 — image-quality gate: quality is a perception signal only and never
  becomes a compliance verdict (extreme-darkness dataset image included).
* Phase 6 — upload/resource limits: extreme dimensions rejected gracefully;
  corrupted and truncated files rejected without crashing the API.
* Phase 7 — processing reliability: a failing OCR stage marks the run FAILED
  with a sanitized error, creates NO findings, and leaves the prior run
  history intact (failure-path behaviour is also covered in
  test_perception_api.py::test_ocr_failure_marks_run_failed).
* Phase 8 — duplicate processing: repeated perceive/reanalyze while a run is
  ACTIVE returns the existing run instead of queueing duplicates; after the
  run reaches a terminal state, re-analysis creates a NEW run (history
  preserved).
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.enums import ProcessingRunStatus
from app.models import ProcessingRun
from app.services.registry import Services
from tests.conftest import API
from tests.test_perception_api import _create_inspection, _upload_image
from tests.test_perception_pipeline import FakeOCRService, FakeVisionService

DATASET_DIR = Path(__file__).resolve().parent / "dataset"

# Run statuses that end a run's lifecycle (matches perception.service._TERMINAL).
_TERMINAL_STATUSES = {"COMPLETED", "PARTIAL", "FAILED", "REVIEW_REQUIRED"}


@pytest.fixture()
def fakes(services: Services, monkeypatch):
    """Swap the pipeline's providers for deterministic fakes (auto-restored)."""
    pipeline = services.perception._pipeline
    ocr, vision = FakeOCRService(), FakeVisionService()
    monkeypatch.setattr(pipeline, "_ocr", ocr)
    monkeypatch.setattr(pipeline, "_vision", vision)
    return ocr, vision


def _png(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seed_hardening_inspection(db, services) -> object:
    """Minimal inspection (+ package) via the real inspection service."""
    from app.schemas.inspection import CreateInspectionRequest

    inspection = services.inspection.create_inspection(
        db,
        inspector_id=None,
        request=CreateInspectionRequest(
            product_name="Hardening Sample", product_category="food"
        ),
    )
    return inspection.id


# --- Phase 6: resource limits -------------------------------------------------


class TestResourceLimits:
    def test_extreme_dimensions_rejected_gracefully(self, client, inspector_headers):
        """A dimension-bomb image (9000px wide strip) is refused at intake with
        a sanitized INVALID_IMAGE error naming the limit — no crash."""
        inspection_id = _create_inspection(client, inspector_headers)
        resp = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("huge.png", _png(9000, 1500), "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        assert resp.status_code == 400, resp.text
        error = resp.json()["error"]
        assert error["code"] == "INVALID_IMAGE"
        assert error["details"]["maxDimension"] == 8000
        assert "traceback" not in resp.text.lower()

    def test_dimension_limit_service_level(self, db, services: Services):
        """The dimension guard fires from the service layer as well."""
        from app.services.intake.service import IntakeService

        tight = services.settings.model_copy(update={"max_image_dimension": 1500})
        intake = IntakeService(
            settings=tight,
            storage=services.storage,
            quality=services.intake_quality,
            audit=services.audit,
        )
        inspection_id = _seed_hardening_inspection(db, services)
        from app.core.enums import CaptureSource, ImageType

        with pytest.raises(Exception) as excinfo:
            intake.upload_image(
                db,
                inspection_id=inspection_id,
                filename="wide.png",
                declared_mime="image/png",
                data=_png(4000, 500),  # 4000 > 1500 cap
                capture_source=CaptureSource.UPLOAD,
                image_type=ImageType.FRONT,
                actor_id=None,
            )
        assert "maximum" in str(excinfo.value).lower()

    def test_truncated_image_rejected(self, client, inspector_headers):
        """A PNG header followed by garbage is corrupt — clean 400, no crash."""
        inspection_id = _create_inspection(client, inspector_headers)
        truncated = _png(800, 600)[:64] + b"\x00" * 32
        resp = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("trunc.png", truncated, "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] in ("INVALID_IMAGE", "UNSUPPORTED_FILE")

    def test_batch_limit_enforced(self, client, inspector_headers):
        inspection_id = _create_inspection(client, inspector_headers)
        files = [(f"f{i}.png", _png(500, 500), "image/png") for i in range(21)]
        resp = client.post(
            f"{API}/inspections/{inspection_id}/images/batch",
            headers=inspector_headers,
            files=[("files", f) for f in files],
        )
        assert resp.status_code in (400, 422), resp.text


# --- Phase 5: quality gate is not a legal verdict ------------------------------


class TestQualityGateIsPerceptionOnly:
    def test_extreme_darkness_image_graded_not_convicted(self, client, inspector_headers):
        """The extreme-darkness dataset image is graded by usability only; the
        inspection is NEVER given a compliance verdict from image quality."""
        inspection_id = _create_inspection(client, inspector_headers)
        dark = (DATASET_DIR / "images" / "food-extremedark-014.png").read_bytes()
        upload = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("dark.png", dark, "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        assert upload.status_code == 201, upload.text
        grade = upload.json()["qualityGrade"]
        assert grade in ("POOR", "ACCEPTABLE", "REJECTED"), grade
        compliance = client.get(
            f"{API}/inspections/{inspection_id}/compliance", headers=inspector_headers
        ).json()
        assert compliance["status"] == "NOT_EVALUATED"

    def test_dataset_manifest_is_honest_about_accuracy(self):
        """The dataset manifest must not claim OCR accuracy percentages."""
        manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
        text = json.dumps(manifest).lower()
        assert "accuracy" in text  # disclaimer present
        # No "NN% accuracy/recognition" claims (the only permitted % is the
        # brightness rendering parameter of the darkness fixture).
        import re

        for match in re.finditer(r"\d+(\.\d+)?\s*%", text):
            context = text[max(0, match.start() - 40) : match.end() + 40]
            assert "accuracy" not in context and "recogni" not in context, context
        assert manifest["origin"].startswith("All images are locally rendered")


# --- Phase 8: duplicate processing ----------------------------------------------


class TestDuplicateProcessingGuard:
    def test_repeated_perceive_while_active_is_idempotent(
        self, client, inspector_headers, services, fakes, monkeypatch
    ):
        """Calling perceive while a run is still ACTIVE returns the SAME run —
        no duplicate queued runs (double-click safe)."""
        inspection_id = _create_inspection(client, inspector_headers)
        image_id = _upload_image(client, inspector_headers, inspection_id)

        # Create a QUEUED (active) run directly, bypassing the background
        # execution, and keep it in-flight for the whole test (TestClient runs
        # background tasks synchronously, which would otherwise finish it).
        from uuid import UUID

        from sqlalchemy.orm import selectinload

        from app.models import Image

        monkeypatch.setattr(services.perception, "execute_runs", lambda ids: [])
        image_id = UUID(image_id)
        with services.perception._session_factory() as db:
            image = db.get(Image, image_id, options=(selectinload(Image.package),))
            run = services.perception._pipeline.create_run(
                db, image=image, inspection=image.package.inspection, actor_id=None
            )
            first_run_id = run.id

        # Two consecutive perceive requests while the run is active.
        for _ in range(2):
            resp = client.post(
                f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers
            )
            assert resp.status_code == 202, resp.text

        with services.perception._session_factory() as db:
            runs = list(
                db.execute(
                    select(ProcessingRun).where(
                        ProcessingRun.inspection_id == UUID(inspection_id)
                    )
                ).scalars()
            )
        assert len(runs) == 1, f"expected exactly one run, got {len(runs)}"
        assert runs[0].id == first_run_id
        assert runs[0].status not in _TERMINAL_STATUSES

    def test_reanalyze_while_active_returns_existing_run(
        self, client, inspector_headers, services, fakes
    ):
        from uuid import UUID

        from sqlalchemy.orm import selectinload

        from app.models import Image

        inspection_id = _create_inspection(client, inspector_headers)
        image_id = _upload_image(client, inspector_headers, inspection_id)
        with services.perception._session_factory() as db:
            image = db.get(Image, UUID(image_id), options=(selectinload(Image.package),))
            run = services.perception._pipeline.create_run(
                db, image=image, inspection=image.package.inspection, actor_id=None
            )
            active_run_id = run.id

        resp = client.post(
            f"{API}/images/{image_id}/reanalyze", headers=inspector_headers
        )
        assert resp.status_code == 202, resp.text
        with services.perception._session_factory() as db:
            runs = list(
                db.execute(
                    select(ProcessingRun).where(ProcessingRun.image_id == UUID(image_id))
                ).scalars()
            )
        assert len(runs) == 1
        assert runs[0].id == active_run_id

    def test_reanalyze_after_terminal_creates_new_run(
        self, client, inspector_headers, fakes
    ):
        """Once the run has finished, re-analysis creates a NEW run and the
        old one is preserved (regression guard for the duplicate fix)."""
        inspection_id = _create_inspection(client, inspector_headers)
        image_id = _upload_image(client, inspector_headers, inspection_id)
        assert client.post(
            f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers
        ).status_code == 202

        resp = client.post(f"{API}/images/{image_id}/reanalyze", headers=inspector_headers)
        assert resp.status_code == 202, resp.text

        runs = client.get(
            f"{API}/inspections/{inspection_id}/processing", headers=inspector_headers
        ).json()
        assert len(runs) == 2
        statuses = {r["status"] for r in runs}
        assert statuses <= {"COMPLETED", "REVIEW_REQUIRED", "PARTIAL", "FAILED"}


# --- Phase 7: reliability sanity ------------------------------------------------


class TestProcessingReliability:
    def test_run_states_follow_the_state_machine(self, client, inspector_headers, fakes):
        """Every persisted run reaches a TERMINAL state from the allowed set."""
        inspection_id = _create_inspection(client, inspector_headers)
        _upload_image(client, inspector_headers, inspection_id)
        assert client.post(
            f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers
        ).status_code == 202
        runs = client.get(
            f"{API}/inspections/{inspection_id}/processing", headers=inspector_headers
        ).json()
        assert runs
        terminal = {
            ProcessingRunStatus.COMPLETED.value,
            ProcessingRunStatus.PARTIAL.value,
            ProcessingRunStatus.FAILED.value,
            ProcessingRunStatus.REVIEW_REQUIRED.value,
        }
        for run in runs:
            assert run["status"] in terminal
            assert run.get("error") is None or isinstance(run["error"], dict)
