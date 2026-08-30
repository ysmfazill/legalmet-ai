"""Intake service — real physical-package image ingestion (Prompt 3).

This is the deterministic, non-AI pipeline that turns a raw camera/upload/batch
image into a validated, stored, provenance-rich :class:`Image` record and moves
the inspection towards ``READY_FOR_ANALYSIS``:

    bytes -> validate (server-authoritative) -> checksum -> store original
          -> usability quality grade -> Image row (+provenance) -> lifecycle

Scope boundaries (enforced by design, not convention)
-----------------------------------------------------
* **No perception, no rules, no compliance.** Nothing here runs OCR, computer
  vision, product classification or the rule engine. Uploading an image can only
  ever advance state to ``READY_FOR_ANALYSIS`` — never COMPLIANT / VIOLATION /
  LEGAL. Those belong to the (later) analysis phase.
* **The quality grade is a usability score**, not AI/compliance confidence.
* **The server is authoritative.** The accept/reject decision is made from the
  actual decoded bytes (Pillow content sniff), never the client-supplied
  filename, extension, or MIME. Those are recorded for provenance only.
* **The original is immutable.** Bytes are stored verbatim under ``storage_key``;
  any derivative (EXIF-oriented, resized, metadata-stripped) lives separately
  under ``processed_storage_key``.

Each public mutating method owns one transaction (commits internally), matching
the surrounding :class:`InspectionService` convention.
"""
from __future__ import annotations

import hashlib
import uuid
from io import BytesIO

from PIL import Image as PILImage
from PIL import ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.enums import (
    AuditEventType,
    CaptureSource,
    ImageProcessingStatus,
    ImageQualityGrade,
    ImageType,
    InspectionStatus,
    PackageStatus,
)
from app.core.errors import (
    AppError,
    ConflictError,
    ImageTooLargeError,
    InvalidImageError,
    NotFoundError,
    UnsupportedFileError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models import Image, Inspection, Package
from app.services.audit.service import AuditService
from app.services.interfaces import ImageQualityAnalyzer
from app.services.storage.base import StorageService

logger = get_logger(__name__)

# PIL format string -> canonical MIME + file extension. The decoded format is
# the single source of truth for what a file actually is.
_FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_MIME_TO_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
# Extensions we permit on the ORIGINAL filename (defence in depth; the content
# sniff above is what actually authorises the upload).
_ALLOWED_EXTS = {"jpg", "jpeg", "png", "webp"}


class SniffedImage:
    """Result of decoding raw bytes with Pillow (server-authoritative facts)."""

    __slots__ = ("mime", "ext", "width", "height")

    def __init__(self, *, mime: str, ext: str, width: int, height: int) -> None:
        self.mime = mime
        self.ext = ext
        self.width = width
        self.height = height


class IntakeService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: StorageService,
        quality: ImageQualityAnalyzer,
        audit: AuditService,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._quality = quality
        self._audit = audit

    # -- Reads --------------------------------------------------------------

    def get_inspection(self, db: Session, inspection_id: uuid.UUID) -> Inspection:
        stmt = (
            select(Inspection)
            .where(Inspection.id == inspection_id)
            .options(selectinload(Inspection.packages).selectinload(Package.images))
        )
        inspection = db.execute(stmt).scalar_one_or_none()
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        return inspection

    def get_image(self, db: Session, image_id: uuid.UUID) -> Image:
        stmt = (
            select(Image)
            .where(Image.id == image_id)
            .options(selectinload(Image.package))
        )
        image = db.execute(stmt).scalar_one_or_none()
        if image is None:
            raise NotFoundError(f"Image not found: {image_id}")
        return image

    def list_images(self, db: Session, inspection_id: uuid.UUID) -> list[Image]:
        inspection = self.get_inspection(db, inspection_id)
        images: list[Image] = []
        for package in inspection.packages:
            images.extend(package.images)
        images.sort(key=lambda i: i.created_at)
        return images

    # -- Packages -----------------------------------------------------------

    def create_package(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        label: str | None,
        actor_id: uuid.UUID | None,
    ) -> Package:
        inspection = self.get_inspection(db, inspection_id)
        package = Package(
            inspection_id=inspection.id,
            product_id=inspection.product_id,
            label=(label or f"Package {len(inspection.packages) + 1}").strip()[:255],
            status=PackageStatus.CREATED.value,
        )
        db.add(package)
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.PACKAGE_CREATED,
            entity_type="package",
            entity_id=package.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"label": package.label},
        )
        db.commit()
        db.refresh(package)
        return package

    # -- Upload (single) ----------------------------------------------------

    def upload_image(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        filename: str,
        declared_mime: str | None,
        data: bytes,
        capture_source: CaptureSource = CaptureSource.UPLOAD,
        image_type: ImageType = ImageType.OTHER,
        package_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Image:
        inspection = self.get_inspection(db, inspection_id)
        package = self._resolve_package(db, inspection, package_id)
        safe_name = _safe_filename(filename)

        # Provenance: record the ATTEMPT before validating, so rejected uploads
        # remain in the audit trail (committed together with the outcome).
        self._audit.record(
            db,
            event_type=AuditEventType.IMAGE_UPLOAD_STARTED,
            entity_type="image",
            entity_id=None,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={
                "filename": safe_name,
                "declaredMime": (declared_mime or "").lower() or None,
                "size": len(data),
                "captureSource": capture_source.value,
            },
        )

        try:
            sniffed = self._validate_and_sniff(data=data, filename=safe_name)
            checksum = hashlib.sha256(data).hexdigest()
            self._reject_duplicate(db, inspection=inspection, checksum=checksum)
            storage_key = self._storage_key(inspection.id, sniffed.ext)
            self._storage.save(key=storage_key, data=data, content_type=sniffed.mime)
        except AppError as exc:
            self._audit.record(
                db,
                event_type=AuditEventType.IMAGE_REJECTED,
                entity_type="image",
                entity_id=None,
                actor_id=actor_id,
                inspection_id=inspection.id,
                payload={"filename": safe_name, "code": exc.code.value, "reason": exc.message},
            )
            db.commit()
            raise

        quality = self._quality.analyze(
            image_bytes=data,
            width=sniffed.width,
            height=sniffed.height,
            mime_type=sniffed.mime,
            seed=storage_key,
        )

        image = Image(
            package_id=package.id,
            storage_key=storage_key,
            original_filename=safe_name,
            mime_type=sniffed.mime,
            width=sniffed.width,
            height=sniffed.height,
            file_size=len(data),
            image_type=image_type.value,
            quality_score=quality.score,
            quality_status=quality.status.value,
            quality_grade=quality.grade.value if quality.grade else None,
            quality_metrics=quality.metrics or None,
            checksum=checksum,
            capture_source=capture_source.value,
            processing_status=ImageProcessingStatus.PENDING.value,
            is_demo=False,
        )
        db.add(image)

        if package.status == PackageStatus.CREATED.value:
            package.status = PackageStatus.IMAGE_ATTACHED.value
        if inspection.status == InspectionStatus.CREATED.value:
            inspection.status = InspectionStatus.IMAGES_PENDING.value
        db.flush()

        # The upload itself succeeded (validated + stored). Recorded as a
        # distinct event from the subsequent quality grading so the trail reads
        # STARTED -> UPLOADED -> QUALITY_CHECK_COMPLETED. This asserts NOTHING
        # about compliance — only that bytes were accepted and persisted.
        self._audit.record(
            db,
            event_type=AuditEventType.IMAGE_UPLOADED,
            entity_type="image",
            entity_id=image.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={
                "filename": safe_name,
                "mimeType": sniffed.mime,
                "width": sniffed.width,
                "height": sniffed.height,
                "size": len(data),
                "checksum": checksum,
                "captureSource": capture_source.value,
                "storageKey": storage_key,
            },
        )
        self._audit.record(
            db,
            event_type=AuditEventType.QUALITY_CHECK_COMPLETED,
            entity_type="image",
            entity_id=image.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={
                "grade": quality.grade.value if quality.grade else None,
                "score": quality.score,
                "status": quality.status.value,
            },
        )
        db.commit()
        db.refresh(image)
        return image

    # -- Upload (batch) -----------------------------------------------------

    def batch_upload(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        files: list[tuple[str, str | None, bytes]],
        package_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Upload many files, isolating per-file failures.

        Returns one result dict per input file preserving order:
        ``{"filename", "status": "UPLOADED"|"REJECTED", "image"|"error"}``. A bad
        file (invalid, oversized, duplicate) never aborts the rest of the batch.
        """
        if len(files) > self._settings.max_batch_files:
            raise ValidationError(
                f"Batch exceeds the maximum of {self._settings.max_batch_files} files.",
                details={"maxBatchFiles": self._settings.max_batch_files, "received": len(files)},
            )

        results: list[dict] = []
        for filename, declared_mime, data in files:
            try:
                image = self.upload_image(
                    db,
                    inspection_id=inspection_id,
                    filename=filename,
                    declared_mime=declared_mime,
                    data=data,
                    capture_source=CaptureSource.BATCH,
                    package_id=package_id,
                    actor_id=actor_id,
                )
                results.append(
                    {"filename": _safe_filename(filename), "status": "UPLOADED", "image": image}
                )
            except AppError as exc:
                results.append(
                    {
                        "filename": _safe_filename(filename),
                        "status": "REJECTED",
                        "error": {"code": exc.code.value, "message": exc.message},
                    }
                )
        return results

    # -- Quality re-check ---------------------------------------------------

    def quality_check(
        self, db: Session, *, image_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> Image:
        image = self.get_image(db, image_id)
        data = self._storage.read(key=image.storage_key)
        quality = self._quality.analyze(
            image_bytes=data,
            width=image.width,
            height=image.height,
            mime_type=image.mime_type,
            seed=image.storage_key,
        )
        image.quality_score = quality.score
        image.quality_status = quality.status.value
        image.quality_grade = quality.grade.value if quality.grade else None
        image.quality_metrics = quality.metrics or None
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.QUALITY_CHECK_COMPLETED,
            entity_type="image",
            entity_id=image.id,
            actor_id=actor_id,
            inspection_id=image.package.inspection_id,
            payload={
                "grade": quality.grade.value if quality.grade else None,
                "score": quality.score,
                "status": quality.status.value,
            },
        )
        db.commit()
        db.refresh(image)
        return image

    # -- Preprocessing (derivative only — NOT analysis) ---------------------

    def prepare_image(
        self, db: Session, *, image_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> Image:
        """Produce a display/analysis-ready derivative of a stored original.

        Applies EXIF orientation, downscales to ``processed_max_dimension`` and
        re-encodes as JPEG (which strips metadata). The ORIGINAL is untouched.
        This is image *preparation* only — it performs no OCR/CV/analysis.
        """
        image = self.get_image(db, image_id)
        image.processing_status = ImageProcessingStatus.PROCESSING.value
        db.flush()

        try:
            original = self._storage.read(key=image.storage_key)
            with PILImage.open(BytesIO(original)) as opened:
                oriented = ImageOps.exif_transpose(opened)
                if oriented.mode not in ("RGB", "L"):
                    oriented = oriented.convert("RGB")
                max_dim = self._settings.processed_max_dimension
                oriented.thumbnail((max_dim, max_dim))
                buffer = BytesIO()
                oriented.save(buffer, format="JPEG", quality=90, optimize=True)
                processed_bytes = buffer.getvalue()
                processed_size = oriented.size
        except (OSError, ValueError, SyntaxError) as exc:
            image.processing_status = ImageProcessingStatus.FAILED.value
            db.commit()
            raise InvalidImageError("Stored image could not be prepared.") from exc

        processed_key = self._processed_key(image.package.inspection_id)
        self._storage.save(key=processed_key, data=processed_bytes, content_type="image/jpeg")
        image.processed_storage_key = processed_key
        image.processing_status = ImageProcessingStatus.READY.value
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.IMAGE_PREPARED,
            entity_type="image",
            entity_id=image.id,
            actor_id=actor_id,
            inspection_id=image.package.inspection_id,
            payload={
                "processedWidth": processed_size[0],
                "processedHeight": processed_size[1],
                "processedSize": len(processed_bytes),
            },
        )
        db.commit()
        db.refresh(image)
        return image

    # -- Delete -------------------------------------------------------------

    def delete_image(
        self, db: Session, *, image_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> None:
        image = self.get_image(db, image_id)
        package = image.package
        inspection_id = package.inspection_id
        # Storage deletes are idempotent no-ops if the object is already gone.
        self._storage.delete(key=image.storage_key)
        if image.processed_storage_key:
            self._storage.delete(key=image.processed_storage_key)

        db.delete(image)
        db.flush()
        self._recompute_after_delete(db, package)
        self._audit.record(
            db,
            event_type=AuditEventType.IMAGE_DELETED,
            entity_type="image",
            entity_id=image_id,
            actor_id=actor_id,
            inspection_id=inspection_id,
            payload={"storageKey": image.storage_key},
        )
        db.commit()

    # -- Lifecycle: mark ready ---------------------------------------------

    def mark_ready(
        self, db: Session, *, inspection_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> Inspection:
        """Advance an inspection to READY_FOR_ANALYSIS.

        Requires at least one attached image that was not REJECTED by the
        usability grader. Explicitly performs NO analysis and asserts NO
        compliance conclusion — the only outcome here is "ready for analysis".
        """
        inspection = self.get_inspection(db, inspection_id)
        all_images = [img for pkg in inspection.packages for img in pkg.images]
        if not all_images:
            raise ValidationError("Attach at least one image before marking ready for analysis.")

        usable = [
            img for img in all_images if img.quality_grade != ImageQualityGrade.REJECTED.value
        ]
        if not usable:
            raise ConflictError(
                "All attached images were rejected by the quality check; none are usable.",
                details={"imageCount": len(all_images), "usableCount": 0},
            )

        for package in inspection.packages:
            if package.images:
                package.status = PackageStatus.READY_FOR_ANALYSIS.value
        inspection.status = InspectionStatus.READY_FOR_ANALYSIS.value
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.INSPECTION_READY,
            entity_type="inspection",
            entity_id=inspection.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"imageCount": len(all_images), "usableCount": len(usable)},
        )
        db.commit()
        return self.get_inspection(db, inspection.id)

    # -- Internals ----------------------------------------------------------

    def _validate_and_sniff(self, *, data: bytes, filename: str) -> SniffedImage:
        """Server-authoritative validation. Decides accept/reject from BYTES."""
        if not data:
            raise InvalidImageError("Uploaded file is empty.")
        if len(data) > self._settings.max_image_size:
            raise ImageTooLargeError(
                "Image exceeds the maximum allowed size.",
                details={"maxImageSize": self._settings.max_image_size, "size": len(data)},
            )

        # Integrity probe: verify() raises on truncated/corrupt data. It leaves
        # the object unusable, so the image is reopened afterwards for real use.
        try:
            with PILImage.open(BytesIO(data)) as probe:
                probe.verify()
            with PILImage.open(BytesIO(data)) as opened:
                fmt = opened.format
                oriented = ImageOps.exif_transpose(opened)
                width, height = oriented.size
        except (OSError, ValueError, SyntaxError) as exc:
            raise InvalidImageError("File is not a valid or is a corrupt image.") from exc

        mime = _FORMAT_TO_MIME.get(fmt or "")
        if mime is None or mime not in self._settings.allowed_image_mime_list:
            raise UnsupportedFileError(
                f"Unsupported image format: {fmt or 'unknown'}.",
                details={"allowed": self._settings.allowed_image_mime_list},
            )

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext and ext not in _ALLOWED_EXTS:
            raise UnsupportedFileError(f"Unsupported file extension: .{ext}")

        if width < self._settings.min_image_width or height < self._settings.min_image_height:
            raise InvalidImageError(
                "Image resolution is below the minimum required for intake.",
                details={
                    "minWidth": self._settings.min_image_width,
                    "minHeight": self._settings.min_image_height,
                    "width": width,
                    "height": height,
                },
            )

        # Extreme dimensions: a tiny file can decode to a huge pixel buffer
        # (decompression bomb). Reject before any further processing.
        max_dim = self._settings.max_image_dimension
        if width > max_dim or height > max_dim or width * height > max_dim * max_dim:
            raise InvalidImageError(
                "Image dimensions exceed the maximum allowed for intake.",
                details={
                    "maxDimension": max_dim,
                    "width": width,
                    "height": height,
                },
            )

        return SniffedImage(mime=mime, ext=_MIME_TO_EXT[mime], width=width, height=height)

    def _reject_duplicate(self, db: Session, *, inspection: Inspection, checksum: str) -> None:
        package_ids = [pkg.id for pkg in inspection.packages]
        if not package_ids:
            return
        stmt = select(Image.id).where(
            Image.package_id.in_(package_ids), Image.checksum == checksum
        )
        if db.execute(stmt).first() is not None:
            raise ConflictError(
                "An identical image (same checksum) already exists for this inspection.",
                details={"checksum": checksum},
            )

    def _resolve_package(
        self, db: Session, inspection: Inspection, package_id: uuid.UUID | None
    ) -> Package:
        if package_id is not None:
            for package in inspection.packages:
                if package.id == package_id:
                    return package
            raise NotFoundError(f"Package not found on this inspection: {package_id}")
        if inspection.packages:
            return inspection.packages[0]
        package = Package(
            inspection_id=inspection.id,
            product_id=inspection.product_id,
            label="Package 1",
            status=PackageStatus.CREATED.value,
        )
        db.add(package)
        db.flush()
        inspection.packages.append(package)
        return package

    @staticmethod
    def _recompute_after_delete(db: Session, package: Package) -> None:
        db.refresh(package)
        if not package.images and package.status != PackageStatus.CREATED.value:
            package.status = PackageStatus.CREATED.value
            db.flush()

    @staticmethod
    def _storage_key(inspection_id: uuid.UUID, ext: str) -> str:
        return f"inspections/{inspection_id}/{uuid.uuid4().hex}.{ext}"

    @staticmethod
    def _processed_key(inspection_id: uuid.UUID) -> str:
        return f"inspections/{inspection_id}/processed/{uuid.uuid4().hex}.jpg"


def _safe_filename(filename: str | None) -> str:
    """Keep only a display-safe basename. NEVER used to build a storage key."""
    if not filename:
        return "upload"
    base = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (base or "upload")[:512]
