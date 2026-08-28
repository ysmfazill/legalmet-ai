"""Real PaddleOCR service (Prompt 4).

Wraps a LOCAL PaddleOCR (PaddlePaddle CPU) engine behind the existing
:class:`OCRService` seam so the rest of the system never imports paddle. The
engine is initialised lazily on first use — the server starts fast and does NOT
download models at boot; the first analysis initialises (and, if not yet
cached, downloads) the configured models. Failures surface as a clear
``AI_SERVICE_UNAVAILABLE`` error pointing at the documented model setup.

Compatibility notes (verified on this project's environment):
- paddlepaddle 3.0.0 (CPU) + paddleocr 3.1.0 + paddlex 3.1.0 on
  Windows 11 / Python 3.11 work; paddlex MUST be pinned to 3.1.0 because
  3.7.x changes ``PaddlePredictorOption.__init__`` and breaks paddleocr 3.1.
- CPU-only inference; no GPU required. Accuracy not yet benchmarked.

Multilingual: one engine per configured language code (e.g. ``en``,
``devanagari``, ``tamil``, ``telugu``). Results are merged and each line is
tagged with the language whose engine read it. Only languages actually
configured are claimed — see docs/ocr.md for the supported list.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from app.core.enums import ModelServiceType
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.services.interfaces import BBox, OcrLine, OcrResult, OCRService, ServiceDescriptor

logger = get_logger(__name__)

# Model files used per language (recorded in run configuration / ModelVersion
# meta for auditability).
_MODEL_FAMILY = "PP-OCRv5"


class PaddleOCRService(OCRService):
    """Real local OCR via PaddleOCR. One lazily-built engine per language."""

    def __init__(
        self,
        *,
        langs: list[str] | None = None,
        timeout_seconds: float = 180.0,
        use_doc_orientation_classify: bool = False,
        use_doc_unwarping: bool = False,
        use_textline_orientation: bool = False,
    ) -> None:
        self._langs = [lang.strip() for lang in (langs or ["en"]) if lang.strip()]
        self._timeout_seconds = timeout_seconds
        self._engine_flags = {
            "use_doc_orientation_classify": use_doc_orientation_classify,
            "use_doc_unwarping": use_doc_unwarping,
            "use_textline_orientation": use_textline_orientation,
        }
        self._engines: dict[str, object] = {}
        self._engine_lock = threading.Lock()
        # Single worker keeps inference serialized (paddle inference is not
        # thread-safe) while still giving us a hard timeout handle.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-ocr")
        self._predict_lock = threading.Lock()

    @property
    def descriptor(self) -> ServiceDescriptor:
        version = self._paddleocr_version()
        return ServiceDescriptor(
            service_type=ModelServiceType.OCR,
            name=f"paddleocr-{_MODEL_FAMILY.lower()}",
            version=version,
            provider="PaddlePaddle",
        )

    @property
    def langs(self) -> list[str]:
        return list(self._langs)

    @property
    def model_family(self) -> str:
        return _MODEL_FAMILY

    # --- OCRService ----------------------------------------------------------

    def extract_text(self, *, image_bytes: bytes | None, storage_key: str, seed: str) -> OcrResult:
        if image_bytes is None:
            raise ServiceUnavailableError(
                "Real OCR requires the stored image bytes; none were provided.",
                details={"storageKey": storage_key},
            )

        import cv2  # numpy/cv2 come with the paddleocr install
        import numpy as np

        array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if array is None:
            raise ServiceUnavailableError(
                "The OCR derivative could not be decoded for inference.",
                details={"storageKey": storage_key},
            )
        height, width = array.shape[:2]

        lines: list[OcrLine] = []
        for lang in self._langs:
            engine = self._engine_for(lang)
            try:
                with self._predict_lock:
                    future = self._executor.submit(self._predict, engine, array)
                    raw_results = future.result(timeout=self._timeout_seconds)
            except FutureTimeoutError as exc:
                raise ServiceUnavailableError(
                    "OCR timed out before the engine finished.",
                    code=None,
                    details={"timeoutSeconds": self._timeout_seconds, "language": lang},
                ) from exc
            lines.extend(self._to_lines(raw_results, width, height, lang))

        mean = round(sum(line.confidence for line in lines) / len(lines), 4) if lines else 0.0
        return OcrResult(
            lines=lines,
            mean_confidence=mean,
            descriptor=self.descriptor,
            width=width,
            height=height,
        )

    # --- internals -------------------------------------------------------------

    @staticmethod
    def _predict(engine, array):
        return engine.predict(array)

    def _engine_for(self, lang: str):
        with self._engine_lock:
            engine = self._engines.get(lang)
            if engine is not None:
                return engine
            try:
                from paddleocr import PaddleOCR
            except Exception as exc:  # pragma: no cover - depends on local install
                raise ServiceUnavailableError(
                    "Perception model unavailable. PaddleOCR is not installed — "
                    "complete the documented local model setup (see docs/ocr.md).",
                    details={"language": lang, "reason": type(exc).__name__},
                ) from exc
            try:
                engine = PaddleOCR(lang=lang, **self._engine_flags)
            except Exception as exc:
                raise ServiceUnavailableError(
                    "Perception model unavailable. The OCR engine could not be "
                    "initialised (models missing or failed to load). Complete the "
                    "documented local model setup (see docs/ocr.md).",
                    details={"language": lang, "reason": f"{type(exc).__name__}: {exc}"},
                ) from exc
            self._engines[lang] = engine
            logger.info("paddle_ocr_engine_ready", language=lang)
            return engine

    @staticmethod
    def _to_lines(raw_results, width: int, height: int, lang: str) -> list[OcrLine]:
        lines: list[OcrLine] = []
        for result in raw_results or []:
            texts = list(result.get("rec_texts", []))
            scores = list(result.get("rec_scores", []))
            polys = list(result.get("rec_polys", []))
            for text, score, poly in zip(texts, scores, polys, strict=False):
                xs = [float(pt[0]) for pt in poly]
                ys = [float(pt[1]) for pt in poly]
                x0, x1 = max(0.0, min(xs)), min(float(width), max(xs))
                y0, y1 = max(0.0, min(ys)), min(float(height), max(ys))
                bbox = BBox(
                    x=round(x0 / width, 6),
                    y=round(y0 / height, 6),
                    width=round(max(0.0, x1 - x0) / width, 6),
                    height=round(max(0.0, y1 - y0) / height, 6),
                )
                lines.append(
                    OcrLine(
                        text=str(text),
                        bbox=bbox,
                        confidence=round(float(score), 4),
                        language=lang,
                    )
                )
        return lines

    @staticmethod
    def _paddleocr_version() -> str:
        try:
            from paddleocr import __version__ as paddleocr_version

            return f"{paddleocr_version}+{_MODEL_FAMILY}"
        except Exception:  # pragma: no cover - import already guarded upstream
            return f"unknown+{_MODEL_FAMILY}"
