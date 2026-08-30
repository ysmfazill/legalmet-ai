# METRASIGHT — Vision / Region Detection (OpenCV)

> **Status:** the vision stage of package perception is a REAL local OpenCV
> detector pass: QR codes and 1D barcodes (EAN/UPC/Code-128 family) are located
> on the actual image and, where practical, decoded. Region payloads are
> evidence only — nothing downstream draws a legal conclusion from them.
>
> **Scope guardrail:** this is perception, not evaluation. A decoded EAN-13 is
> a fact about pixels; whether any declaration satisfies the Legal Metrology
> rules is out of scope for this stage.

Sources: `services/api/app/services/vision/opencv.py`,
`services/api/app/services/interfaces.py` (the `VisionService` seam).

---

## 1. What is detected

| Region type | Detector | Payload |
| --- | --- | --- |
| `TEXT_LINE` | derived from OCR boxes (not this module — see `docs/perception.md`) | none |
| `QR_CODE` | `cv2.QRCodeDetector.detectAndDecodeMulti` (+ single-code fallback) | `{ symbology: "QR", value, decoded }` |
| `BARCODE` | `cv2.barcode.BarcodeDetector.detectAndDecodeWithType` | `{ symbology, value, decoded }` |

"Where practical" is implemented honestly:

* A symbol that is **detected but not decoded** is still reported as a region,
  with confidence `0.5` and `decoded: false` in the payload — the system never
  invents a value it could not read.
* A decoded symbol gets confidence `1.0` and its decoded text in the payload.
* A detector crash on one modality (e.g. the barcode module missing from a
  slim OpenCV build) is swallowed so the other modality still runs; the run
  stays usable.

Every region carries: image id, processing run id, normalized bbox (0–1),
confidence, payload and (for text lines) the language from OCR.

## 2. Failure semantics

Vision is a **non-fatal** stage. If it fails entirely, the run ends `PARTIAL`
with error code `VISION_STAGE_FAILED`, and every OCR text row is preserved —
successful evidence is never discarded. (An OCR failure, by contrast, fails the
run outright; see `docs/ocr.md`.)

## 3. Deliberate limitations (no unverified claims)

* No logo/graphic segmentation, no object detection beyond QR/barcode, no
  expiry-symbol classifier. Region types `LABEL`/`IMAGE` exist in the enum for
  future providers but are not produced by this implementation.
* Detection rates on real Indian packaging have not been benchmarked; no
  accuracy figures are claimed.
* Decoding competes with curvature, glare and print quality like any
  camera-based scanner; undecodable-but-visible symbols surface as
  `decoded: false` regions rather than failures.

## 4. Swapping the VisionProvider

`VisionService` is a seam: implement `detect_regions(*, image_bytes,
storage_key, seed) -> VisionRegionsResult` and wire it in
`app/services/registry.py`. `detect_fields` on the seam is intentionally
unused by this backend — field extraction lives in the deterministic
`FieldExtractionProvider` (`app/services/perception/extract.py`), not in
vision. Any alternative (e.g. a ZXing binding or a commercial barcode SDK)
drops in without touching the pipeline.

## 5. Licences

| Package | Licence |
| --- | --- |
| OpenCV (`opencv-python`) | Apache-2.0 |
| Pillow (preprocessing + test-image rendering) | MIT-CMU (HPND-style MIT) |
| numpy | BSD-3-Clause |

All run locally; no API keys, no credentials, no network calls.
