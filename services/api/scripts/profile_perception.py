"""Stage-level perception profiling (Prompt 11, Phase 5) — MEASURED only.

Times every stage of the REAL perception pipeline directly (same service
objects the API uses) so the OCR optimization work is driven by numbers,
never guesses:

    preprocessor.prepare   (decode + EXIF + grayscale + autocontrast + resize)
    ocr.extract_text       (engine init on FIRST call, then warm inference)
    vision.detect_regions  (OpenCV QR/barcode)
    extractor.extract      (deterministic field extraction)

Run from ``services/api``:

    .venv/Scripts/python.exe scripts/profile_perception.py [image.png ...]

Defaults to the four demo labels. Every number is wall-clock
time.perf_counter(); nothing is extrapolated.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "app" / "db" / "demo_images"
DEFAULTS = ["demo-food.png", "demo-water.png", "demo-oil.png", "demo-quinoa.png"]


def main() -> None:
    from app.core.config import get_settings
    from app.services.perception.extract import DeterministicFieldExtractor
    from app.services.registry import (
        _build_perception_ocr,
        _build_perception_vision,
        _build_preprocessor,
    )

    settings = get_settings()
    preprocessor = _build_preprocessor(settings)
    ocr = _build_perception_ocr(settings)
    vision = _build_perception_vision(settings)
    extractor = DeterministicFieldExtractor(
        review_threshold=settings.perception_field_review_threshold
    )

    names = sys.argv[1:] or DEFAULTS
    print(f"OCR backend: {settings.perception_ocr_backend}")
    print(f"preprocessor bounds: {preprocessor._min_long_edge}-{preprocessor._max_long_edge}")
    print()

    first = True
    for name in names:
        raw = (DEMO_DIR / name).read_bytes()
        print(f"--- {name} ({len(raw) // 1024} KB) ---")

        t0 = time.perf_counter()
        prep = preprocessor.prepare(image_bytes=raw)
        t_prep = time.perf_counter() - t0
        print(
            f"  preprocessor.prepare      {t_prep:7.2f}s"
            f"  ({prep.width}x{prep.height}, {len(prep.data) // 1024} KB derivative)"
        )

        t0 = time.perf_counter()
        ocr_result = ocr.extract_text(
            image_bytes=prep.data, storage_key=f"profile:{name}", seed=name
        )
        t_ocr = time.perf_counter() - t0
        tag = "  [COLD — engine init + first inference]" if first else ""
        print(
            f"  ocr.extract_text          {t_ocr:7.2f}s"
            f"  ({len(ocr_result.lines)} lines){tag}"
        )
        first = False

        t0 = time.perf_counter()
        vision_result = vision.detect_regions(
            image_bytes=prep.data, storage_key=f"profile:{name}", seed=name
        )
        t_vision = time.perf_counter() - t0
        print(
            f"  vision.detect_regions     {t_vision:7.2f}s"
            f"  ({len(vision_result.regions)} regions)"
        )

        t0 = time.perf_counter()
        candidates = extractor.extract(ocr=ocr_result)
        t_extract = time.perf_counter() - t0
        print(f"  extractor.extract         {t_extract:7.2f}s  ({len(candidates)} candidates)")

        total = t_prep + t_ocr + t_vision + t_extract
        print(f"  TOTAL (perception core)   {total:7.2f}s")
        print()


if __name__ == "__main__":
    main()
