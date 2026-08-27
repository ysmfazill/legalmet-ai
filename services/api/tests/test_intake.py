"""Integration + service tests for the real package-intake pipeline (Prompt 3).

Covers validation (format/size/dimensions/corruption/extension), checksum +
duplicate detection, usability grading, storage, batch partial-failure,
preprocessing, deletion, the READY_FOR_ANALYSIS lifecycle, RBAC and the intake
audit trail. Real image bytes are generated in-memory with Pillow.

A guardrail asserted throughout: uploading an image NEVER yields a compliance
verdict. The strongest outcome is READY_FOR_ANALYSIS, and no findings appear.
"""
from __future__ import annotations

from io import BytesIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core.enums import AuditEventType, ImageProcessingStatus, PackageStatus
from app.core.errors import ConflictError, ImageTooLargeError, ValidationError
from app.schemas.inspection import CreateInspectionRequest
from app.services.intake.service import IntakeService
from tests.conftest import API

# --- image generators ------------------------------------------------------


def _img_bytes(
    fmt: str = "PNG", size: tuple[int, int] = (800, 600), *, content: bool = True
) -> bytes:
    img = Image.new("RGB", size, (245, 245, 245))
    if content:
        draw = ImageDraw.Draw(img)
        for x in range(0, size[0], 24):
            draw.line([(x, 0), (x, size[1])], fill=(10, 10, 10), width=2)
        for y in range(0, size[1], 24):
            draw.line([(0, y), (size[0], y)], fill=(50, 50, 50), width=2)
        draw.rectangle([30, 30, size[0] - 30, size[1] - 30], outline=(0, 0, 0), width=5)
    buffer = BytesIO()
    img.save(buffer, format=fmt)
    return buffer.getvalue()


# --- helpers ---------------------------------------------------------------


def _create_inspection(client: TestClient, headers: dict[str, str]) -> str:
    resp = client.post(
        f"{API}/inspections",
        headers=headers,
        json={"productName": "DEMO Intake Sample", "productCategory": "food"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _upload(
    client: TestClient,
    headers: dict[str, str],
    inspection_id: str,
    data: bytes,
    *,
    filename: str = "front.png",
    mime: str = "image/png",
    capture_source: str = "UPLOAD",
    image_type: str = "FRONT",
):
    return client.post(
        f"{API}/inspections/{inspection_id}/images/upload",
        headers=headers,
        files={"file": (filename, data, mime)},
        data={"captureSource": capture_source, "imageType": image_type},
    )


# --- valid uploads across formats -----------------------------------------


@pytest.mark.parametrize(
    "fmt,filename,mime,expected_mime",
    [
        ("PNG", "front.png", "image/png", "image/png"),
        ("JPEG", "front.jpg", "image/jpeg", "image/jpeg"),
        ("WEBP", "front.webp", "image/webp", "image/webp"),
    ],
)
def test_upload_valid_formats(
    client, inspector_headers, fmt, filename, mime, expected_mime
) -> None:
    iid = _create_inspection(client, inspector_headers)
    resp = _upload(
        client, inspector_headers, iid, _img_bytes(fmt), filename=filename, mime=mime,
        capture_source="CAMERA",
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Server-authoritative MIME comes from the decoded bytes, not the client.
    assert body["mimeType"] == expected_mime
    assert body["width"] == 800 and body["height"] == 600
    assert body["captureSource"] == "CAMERA"
    assert body["processingStatus"] == ImageProcessingStatus.PENDING.value
    assert body["checksum"] and len(body["checksum"]) == 64
    assert body["qualityGrade"] is not None
    assert body["qualityMetrics"]["width"] == 800
    assert body["isDemo"] is False
    assert body["url"].endswith(body["storageKey"])
    # No compliance conclusion is implied by an upload.
    assert "status" not in body or body.get("status") not in {"COMPLIANT", "POTENTIAL_VIOLATION"}


def test_upload_ignores_lying_client_mime_and_uses_content(client, inspector_headers) -> None:
    """A PNG re-labelled as JPEG is stored per its real (sniffed) type."""
    iid = _create_inspection(client, inspector_headers)
    resp = _upload(
        client, inspector_headers, iid, _img_bytes("PNG"), filename="mislabeled.jpg",
        mime="image/jpeg",
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["mimeType"] == "image/png"


# --- rejection paths -------------------------------------------------------


def test_upload_rejects_unsupported_format(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    gif = _img_bytes("GIF")
    resp = _upload(client, inspector_headers, iid, gif, filename="anim.gif", mime="image/gif")
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_upload_rejects_corrupt_bytes(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    resp = _upload(client, inspector_headers, iid, b"this is not an image" * 5)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"


def test_upload_rejects_below_minimum_resolution(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    resp = _upload(client, inspector_headers, iid, _img_bytes("PNG", (200, 200)))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"


def test_duplicate_checksum_conflicts(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    data = _img_bytes("PNG")
    first = _upload(client, inspector_headers, iid, data)
    assert first.status_code == 201, first.text
    second = _upload(client, inspector_headers, iid, data)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


# --- batch -----------------------------------------------------------------


def test_batch_upload_partial_failure(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    files = [
        ("files", ("a.png", _img_bytes("PNG"), "image/png")),
        ("files", ("bad.png", b"not an image", "image/png")),
        ("files", ("c.jpg", _img_bytes("JPEG"), "image/jpeg")),
    ]
    resp = client.post(
        f"{API}/inspections/{iid}/images/batch", headers=inspector_headers, files=files
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["uploaded"] == 2
    assert body["rejected"] == 1
    statuses = {item["filename"]: item["status"] for item in body["items"]}
    assert statuses["a.png"] == "UPLOADED"
    assert statuses["bad.png"] == "REJECTED"
    assert statuses["c.jpg"] == "UPLOADED"
    rejected = next(i for i in body["items"] if i["status"] == "REJECTED")
    assert rejected["error"]["code"] == "INVALID_IMAGE"
    assert rejected["image"] is None


# --- lifecycle: mark ready -------------------------------------------------


def test_mark_ready_transitions_without_compliance(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    assert _upload(client, inspector_headers, iid, _img_bytes("PNG")).status_code == 201

    ready = client.post(f"{API}/inspections/{iid}/ready", headers=inspector_headers)
    assert ready.status_code == 200, ready.text
    detail = ready.json()
    assert detail["status"] == "READY_FOR_ANALYSIS"
    assert detail["packages"][0]["status"] == PackageStatus.READY_FOR_ANALYSIS.value

    # The critical guardrail: still zero findings, no compliance verdict.
    findings = client.get(f"{API}/inspections/{iid}/findings", headers=inspector_headers)
    assert findings.status_code == 200
    assert findings.json() == []


def test_mark_ready_requires_an_image(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    resp = client.post(f"{API}/inspections/{iid}/ready", headers=inspector_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- single-image operations ----------------------------------------------


def test_prepare_produces_resized_derivative(client, inspector_headers, services) -> None:
    iid = _create_inspection(client, inspector_headers)
    upload = _upload(client, inspector_headers, iid, _img_bytes("JPEG", (3000, 2000)),
                     filename="big.jpg", mime="image/jpeg")
    assert upload.status_code == 201, upload.text
    image_id = upload.json()["id"]

    prepared = client.post(f"{API}/images/{image_id}/prepare", headers=inspector_headers)
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    assert body["processingStatus"] == ImageProcessingStatus.READY.value
    assert body["processedStorageKey"]
    assert body["processedUrl"]

    # The derivative is fetchable and downscaled within the configured bound.
    fetched = client.get(f"{API}/storage/{body['processedStorageKey']}", headers=inspector_headers)
    assert fetched.status_code == 200
    with Image.open(BytesIO(fetched.content)) as derivative:
        assert max(derivative.size) <= services.settings.processed_max_dimension


def test_delete_image_removes_record_and_object(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    image_id = _upload(client, inspector_headers, iid, _img_bytes("PNG")).json()["id"]

    deleted = client.delete(f"{API}/images/{image_id}", headers=inspector_headers)
    assert deleted.status_code == 204
    assert client.get(f"{API}/images/{image_id}", headers=inspector_headers).status_code == 404
    listing = client.get(f"{API}/inspections/{iid}/images", headers=inspector_headers)
    assert listing.status_code == 200 and listing.json() == []


def test_create_package_and_target_upload(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    created = client.post(
        f"{API}/inspections/{iid}/packages", headers=inspector_headers, json={"label": "Back panel"}
    )
    assert created.status_code == 201, created.text
    package = created.json()
    assert package["label"] == "Back panel"
    assert package["status"] == PackageStatus.CREATED.value

    resp = client.post(
        f"{API}/inspections/{iid}/images/upload",
        headers=inspector_headers,
        files={"file": ("b.png", _img_bytes("PNG"), "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "BACK", "packageId": package["id"]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["packageId"] == package["id"]


# --- RBAC + auth -----------------------------------------------------------


def test_upload_requires_authentication(client) -> None:
    # Route still needs a real inspection id shape; auth is checked first.
    resp = client.post(
        f"{API}/inspections/{UUID(int=0)}/images/upload",
        files={"file": ("f.png", _img_bytes("PNG"), "image/png")},
    )
    assert resp.status_code == 401


def test_auditor_cannot_upload(client, inspector_headers, auditor_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    resp = _upload(client, auditor_headers, iid, _img_bytes("PNG"))
    assert resp.status_code == 403


# --- audit trail -----------------------------------------------------------


def test_intake_emits_audit_events(client, inspector_headers, db, services) -> None:
    iid = _create_inspection(client, inspector_headers)
    assert _upload(client, inspector_headers, iid, _img_bytes("PNG")).status_code == 201
    # A rejected upload must also leave a trace.
    _upload(client, inspector_headers, iid, b"garbage bytes")
    ready = client.post(f"{API}/inspections/{iid}/ready", headers=inspector_headers)
    assert ready.status_code == 200

    events = {e.event_type for e in services.audit.list_for_inspection(db, UUID(iid))}
    assert AuditEventType.IMAGE_UPLOAD_STARTED.value in events
    assert AuditEventType.IMAGE_REJECTED.value in events
    assert AuditEventType.QUALITY_CHECK_COMPLETED.value in events
    assert AuditEventType.INSPECTION_READY.value in events


# --- service-level tests for configured limits -----------------------------


def _seed_inspection(db, services) -> UUID:
    inspection = services.inspection.create_inspection(
        db,
        inspector_id=None,
        request=CreateInspectionRequest(product_name="Svc Sample", product_category="food"),
    )
    return inspection.id


def test_oversized_image_is_rejected(db, services) -> None:
    tight = services.settings.model_copy(update={"max_image_size": 1024})
    svc = IntakeService(
        settings=tight, storage=services.storage, quality=services.intake_quality,
        audit=services.audit,
    )
    inspection_id = _seed_inspection(db, services)
    with pytest.raises(ImageTooLargeError):
        svc.upload_image(
            db, inspection_id=inspection_id, filename="big.png", declared_mime="image/png",
            data=_img_bytes("PNG"),
        )


def test_duplicate_detection_service_level(db, services) -> None:
    svc = services.intake
    inspection_id = _seed_inspection(db, services)
    data = _img_bytes("PNG")
    svc.upload_image(
        db, inspection_id=inspection_id, filename="a.png", declared_mime="image/png", data=data
    )
    with pytest.raises(ConflictError):
        svc.upload_image(
            db, inspection_id=inspection_id, filename="a.png", declared_mime="image/png", data=data
        )


def test_batch_over_limit_is_rejected(db, services) -> None:
    tight = services.settings.model_copy(update={"max_batch_files": 1})
    svc = IntakeService(
        settings=tight, storage=services.storage, quality=services.intake_quality,
        audit=services.audit,
    )
    inspection_id = _seed_inspection(db, services)
    files = [
        ("a.png", "image/png", _img_bytes("PNG")),
        ("b.png", "image/png", _img_bytes("PNG", (640, 480))),
    ]
    with pytest.raises(ValidationError):
        svc.batch_upload(db, inspection_id=inspection_id, files=files)


# --- additional coverage (Prompt 3 completion) -----------------------------


def test_empty_file_is_rejected(client, inspector_headers) -> None:
    """A zero-byte upload is rejected up front as an invalid image (not a 500)."""
    iid = _create_inspection(client, inspector_headers)
    resp = _upload(client, inspector_headers, iid, b"")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"


def test_quality_check_endpoint_recomputes_usability(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    image_id = _upload(client, inspector_headers, iid, _img_bytes("PNG")).json()["id"]

    resp = client.post(f"{API}/images/{image_id}/quality-check", headers=inspector_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["qualityGrade"] is not None
    assert 0.0 <= body["qualityScore"] <= 1.0
    assert body["qualityMetrics"]["width"] == 800
    # Re-checking the same stored bytes is deterministic.
    again = client.post(f"{API}/images/{image_id}/quality-check", headers=inspector_headers)
    assert again.status_code == 200
    assert again.json()["qualityScore"] == body["qualityScore"]
    # Still no compliance conclusion from a quality re-check.
    assert body.get("status") not in {"COMPLIANT", "POTENTIAL_VIOLATION"}


def test_batch_all_valid_uploads_none_rejected(client, inspector_headers) -> None:
    iid = _create_inspection(client, inspector_headers)
    files = [
        ("files", ("a.png", _img_bytes("PNG"), "image/png")),
        ("files", ("b.jpg", _img_bytes("JPEG", (900, 700)), "image/jpeg")),
        ("files", ("c.webp", _img_bytes("WEBP", (1000, 800)), "image/webp")),
    ]
    resp = client.post(
        f"{API}/inspections/{iid}/images/batch", headers=inspector_headers, files=files
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["uploaded"] == 3
    assert body["rejected"] == 0
    assert all(item["status"] == "UPLOADED" for item in body["items"])
    assert all(item["image"] is not None for item in body["items"])


def test_exif_orientation_is_normalized_on_intake(client, inspector_headers) -> None:
    """A photo tagged with an EXIF rotate is stored at its VISUAL orientation.

    Landscape 800x600 pixels + orientation=6 (rotate 90°) must be recorded as
    600x800 — the server applies ``exif_transpose`` before measuring.
    """
    iid = _create_inspection(client, inspector_headers)
    base = Image.new("RGB", (800, 600), (240, 240, 240))
    draw = ImageDraw.Draw(base)
    for x in range(0, 800, 20):
        draw.line([(x, 0), (x, 600)], fill=(0, 0, 0), width=2)
    exif = base.getexif()
    exif[0x0112] = 6  # Orientation tag: rotate 90° on display.
    buffer = BytesIO()
    base.save(buffer, format="JPEG", exif=exif)

    resp = _upload(
        client, inspector_headers, iid, buffer.getvalue(), filename="rot.jpg", mime="image/jpeg"
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["width"] == 600 and body["height"] == 800


def test_intake_emits_complete_audit_trail(client, inspector_headers, db, services) -> None:
    """Every intake step leaves its own audit event, including IMAGE_UPLOADED."""
    iid = _create_inspection(client, inspector_headers)
    pkg = client.post(
        f"{API}/inspections/{iid}/packages", headers=inspector_headers, json={"label": "P1"}
    )
    assert pkg.status_code == 201, pkg.text
    image_id = _upload(client, inspector_headers, iid, _img_bytes("PNG")).json()["id"]
    assert client.post(
        f"{API}/images/{image_id}/prepare", headers=inspector_headers
    ).status_code == 200
    assert client.delete(
        f"{API}/images/{image_id}", headers=inspector_headers
    ).status_code == 204

    events = {e.event_type for e in services.audit.list_for_inspection(db, UUID(iid))}
    for expected in (
        AuditEventType.PACKAGE_CREATED,
        AuditEventType.IMAGE_UPLOAD_STARTED,
        AuditEventType.IMAGE_UPLOADED,
        AuditEventType.QUALITY_CHECK_COMPLETED,
        AuditEventType.IMAGE_PREPARED,
        AuditEventType.IMAGE_DELETED,
    ):
        assert expected.value in events, f"missing audit event: {expected.value}"


# --- filename / storage-key safety (path-traversal defence) ----------------


def test_safe_filename_strips_paths_and_traversal() -> None:
    from app.services.intake.service import _safe_filename

    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("..\\..\\windows\\system32\\evil.png") == "evil.png"
    assert _safe_filename("/abs/path/label.jpg") == "label.jpg"
    assert _safe_filename("front-label.png") == "front-label.png"
    assert _safe_filename("") == "upload"
    assert _safe_filename(None) == "upload"


def test_storage_key_is_uuid_based_never_client_filename() -> None:
    key = IntakeService._storage_key(UUID(int=1234), "png")
    assert key.startswith("inspections/")
    assert key.endswith(".png")
    # The unpredictable segment is a server uuid, never a client-supplied value.
    assert "passwd" not in key and ".." not in key
