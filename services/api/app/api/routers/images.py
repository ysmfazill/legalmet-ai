"""Real package-intake routes (Prompt 3).

Multipart camera/upload/batch ingestion, image lifecycle (quality re-check,
preprocessing, deletion) and the ``READY_FOR_ANALYSIS`` transition. Handlers are
thin; all validation, storage and provenance live in ``services.intake``.

Nothing here runs OCR, computer vision, or the rule engine. The strongest
possible outcome of uploading an image is READY_FOR_ANALYSIS — never a
compliance verdict.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep, require_role
from app.core.enums import CaptureSource, ImageType, UserRole
from app.core.errors import ValidationError
from app.db.session import get_db
from app.models import User
from app.schemas.image import (
    BatchUploadItemResult,
    BatchUploadResponse,
    CreatePackageRequest,
    ImageOut,
)
from app.schemas.inspection import InspectionDetailOut, PackageOut
from app.services.registry import Services

router = APIRouter(tags=["intake"])

# Intake mutations are performed by field staff; auditors keep read-only access.
_INTAKE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


def _image_out(image, services: Services) -> ImageOut:
    """Serialise an Image and attach storage retrieval URLs (not ORM columns)."""
    out = ImageOut.model_validate(image)
    out.url = services.storage.url(key=image.storage_key)
    if image.processed_storage_key:
        out.processed_url = services.storage.url(key=image.processed_storage_key)
    return out


def _parse_capture_source(value: str | None) -> CaptureSource:
    if not value:
        return CaptureSource.UPLOAD
    try:
        return CaptureSource(value.strip().upper())
    except ValueError as exc:
        raise ValidationError(f"Invalid captureSource: {value}") from exc


def _parse_image_type(value: str | None) -> ImageType:
    if not value:
        return ImageType.OTHER
    try:
        return ImageType(value.strip().upper())
    except ValueError as exc:
        raise ValidationError(f"Invalid imageType: {value}") from exc


def _parse_package_id(value: str | None) -> UUID | None:
    if not value or not value.strip():
        return None
    try:
        return UUID(value.strip())
    except ValueError as exc:
        raise ValidationError(f"Invalid packageId: {value}") from exc


# --- Packages --------------------------------------------------------------


@router.post(
    "/inspections/{inspection_id}/packages", response_model=PackageOut, status_code=201
)
def create_package(
    inspection_id: UUID,
    body: CreatePackageRequest | None = None,
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> PackageOut:
    package = services.intake.create_package(
        db,
        inspection_id=inspection_id,
        label=body.label if body else None,
        actor_id=user.id,
    )
    return PackageOut.model_validate(package)


# --- Upload (single) -------------------------------------------------------


@router.post(
    "/inspections/{inspection_id}/images/upload", response_model=ImageOut, status_code=201
)
async def upload_image(
    inspection_id: UUID,
    file: UploadFile = File(...),
    capture_source: str | None = Form(default=None, alias="captureSource"),
    image_type: str | None = Form(default=None, alias="imageType"),
    package_id: str | None = Form(default=None, alias="packageId"),
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ImageOut:
    data = await file.read()
    image = services.intake.upload_image(
        db,
        inspection_id=inspection_id,
        filename=file.filename or "upload",
        declared_mime=file.content_type,
        data=data,
        capture_source=_parse_capture_source(capture_source),
        image_type=_parse_image_type(image_type),
        package_id=_parse_package_id(package_id),
        actor_id=user.id,
    )
    return _image_out(image, services)


# --- Upload (batch) --------------------------------------------------------


@router.post(
    "/inspections/{inspection_id}/images/batch",
    response_model=BatchUploadResponse,
    status_code=201,
)
async def batch_upload(
    inspection_id: UUID,
    files: list[UploadFile] = File(...),
    package_id: str | None = Form(default=None, alias="packageId"),
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> BatchUploadResponse:
    payloads: list[tuple[str, str | None, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "upload", upload.content_type, await upload.read()))

    results = services.intake.batch_upload(
        db,
        inspection_id=inspection_id,
        files=payloads,
        package_id=_parse_package_id(package_id),
        actor_id=user.id,
    )

    items: list[BatchUploadItemResult] = []
    uploaded = 0
    rejected = 0
    for result in results:
        if result["status"] == "UPLOADED":
            uploaded += 1
            items.append(
                BatchUploadItemResult(
                    filename=result["filename"],
                    status="UPLOADED",
                    image=_image_out(result["image"], services),
                )
            )
        else:
            rejected += 1
            items.append(
                BatchUploadItemResult(
                    filename=result["filename"], status="REJECTED", error=result["error"]
                )
            )
    return BatchUploadResponse(items=items, uploaded=uploaded, rejected=rejected)


# --- Listing ---------------------------------------------------------------


@router.get("/inspections/{inspection_id}/images", response_model=list[ImageOut])
def list_images(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[ImageOut]:
    images = services.intake.list_images(db, inspection_id)
    return [_image_out(image, services) for image in images]


# --- Lifecycle: mark ready -------------------------------------------------


@router.post("/inspections/{inspection_id}/ready", response_model=InspectionDetailOut)
def mark_ready(
    inspection_id: UUID,
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDetailOut:
    inspection = services.intake.mark_ready(db, inspection_id=inspection_id, actor_id=user.id)
    out = InspectionDetailOut.model_validate(inspection)
    out.finding_counts = services.analytics.finding_counts(db, inspection_id=inspection.id)
    return out


# --- Single-image operations ----------------------------------------------


@router.get("/images/{image_id}", response_model=ImageOut)
def get_image(
    image_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ImageOut:
    return _image_out(services.intake.get_image(db, image_id), services)


@router.post("/images/{image_id}/quality-check", response_model=ImageOut)
def quality_check(
    image_id: UUID,
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ImageOut:
    image = services.intake.quality_check(db, image_id=image_id, actor_id=user.id)
    return _image_out(image, services)


@router.post("/images/{image_id}/prepare", response_model=ImageOut)
def prepare_image(
    image_id: UUID,
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ImageOut:
    image = services.intake.prepare_image(db, image_id=image_id, actor_id=user.id)
    return _image_out(image, services)


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: UUID,
    user: User = Depends(require_role(*_INTAKE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Response:
    services.intake.delete_image(db, image_id=image_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
