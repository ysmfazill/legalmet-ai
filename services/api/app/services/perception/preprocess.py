"""Pillow-based OCR preprocessor (Prompt 4).

Builds the OCR-oriented derivative of an original image: EXIF orientation,
grayscale, autocontrast, and bounded resizing. The ORIGINAL image is the
primary evidence and is never modified — this derivative exists purely to give
the OCR engine a well-conditioned input, and the operations applied are
recorded in the processing run's configuration for reproducibility.

Transformations are deliberately conservative and each is individually
toggleable: no blind denoise/sharpen/threshold by default, because aggressive
binarization frequently *hurts* modern OCR engines.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image as PILImage
from PIL import ImageOps

from app.core.errors import InvalidImageError
from app.services.interfaces import ImagePreprocessor, PreprocessedImage


class PillowOcrPreprocessor(ImagePreprocessor):
    def __init__(
        self,
        *,
        min_long_edge: int = 1000,
        max_long_edge: int = 2400,
        grayscale: bool = True,
        autocontrast: bool = True,
    ) -> None:
        self._min_long_edge = min_long_edge
        self._max_long_edge = max_long_edge
        self._grayscale = grayscale
        self._autocontrast = autocontrast

    @property
    def name(self) -> str:
        return "pillow-ocr-preprocessor"

    @property
    def version(self) -> str:
        return "1.0.0"

    def prepare(self, *, image_bytes: bytes) -> PreprocessedImage:
        operations: list[str] = []
        try:
            with PILImage.open(BytesIO(image_bytes)) as opened:
                oriented = ImageOps.exif_transpose(opened)
                # Work on a copy: exif_transpose may return the same object.
                oriented = oriented.copy()
        except (OSError, ValueError, SyntaxError) as exc:
            raise InvalidImageError("Stored image could not be decoded for OCR.") from exc

        if oriented.mode not in ("RGB", "L"):
            oriented = oriented.convert("RGB")
            operations.append("convert_rgb")

        if self._grayscale and oriented.mode != "L":
            oriented = oriented.convert("L")
            operations.append("grayscale")

        if self._autocontrast:
            oriented = ImageOps.autocontrast(oriented, cutoff=1)
            operations.append("autocontrast")

        width, height = oriented.size
        long_edge = max(width, height)
        target: tuple[int, int] | None = None
        if long_edge < self._min_long_edge:
            scale = self._min_long_edge / long_edge
            target = (round(width * scale), round(height * scale))
        elif long_edge > self._max_long_edge:
            scale = self._max_long_edge / long_edge
            target = (round(width * scale), round(height * scale))
        if target is not None:
            oriented = oriented.resize(target, PILImage.LANCZOS)
            operations.append(f"resize:{target[0]}x{target[1]}")

        # PNG keeps the derivative lossless — no compression artifacts for the
        # engine, and the derivative itself remains reproducible.
        buffer = BytesIO()
        oriented.save(buffer, format="PNG")
        return PreprocessedImage(
            data=buffer.getvalue(),
            width=oriented.size[0],
            height=oriented.size[1],
            operations=operations,
        )
