# METRASIGHT — Package Perception Pipeline (Prompt 4)

> **Status:** Real multimodal package perception. A REAL uploaded package image
> is processed by a REAL OCR engine (PaddleOCR, CPU) and a REAL symbol detector
> (OpenCV QR/barcode), and the result is structured, traceable perception
> evidence: OCR text lines, visual regions and extracted declaration candidates.
>
> **Scope guardrail:** perception answers *“what can the system see?”* —
> nothing more. There is **no regulatory knowledge and no compliance decision
> here**. The strongest statement the perception layer can make about an
> inspection is `AWAITING_REGULATORY_EVALUATION`. Field types are *perception
> targets*, not legal requirements; `DETECTED` means "evidence was found", not
> "the declaration is legally sufficient".

Sources: `services/api/app/services/perception/` (pipeline, service, extractor,
normalizer, preprocessor), `services/api/app/api/routers/perception.py`,
`services/api/app/schemas/perception.py`, `services/api/app/models/perception.py`.

---

## 1. Pipeline

One perception run processes exactly **one image**:

```
original bytes (immutable evidence)
  → PREPROCESSING      Pillow: EXIF orientation, grayscale, autocontrast,
                        bounded resize → OCR derivative (stored separately)
  → OCR_PROCESSING     PaddleOCR PP-OCRv5 (CPU) → text + bbox + confidence
  → VISION_PROCESSING  OpenCV QR / barcode detection (non-fatal stage)
  → FIELD_EXTRACTION   deterministic regex/keyword rules → field candidates
  → COMPLETED | PARTIAL | REVIEW_REQUIRED | FAILED
```

Design rules:

* **The original image is never modified.** The OCR derivative is a separate
  stored object whose key is recorded in the run configuration.
* **Raw OCR text is stored verbatim** (`raw_text`); normalization
  (`normalized_text`) is a derived, lossy convenience column.
* **An OCR failure fails the run** — without text there is no perception.
  The run lands in `FAILED` with `error.code = AI_SERVICE_UNAVAILABLE` (or
  `INTERNAL_ERROR` for unexpected faults; internal details are never leaked).
* **A vision failure degrades the run to `PARTIAL`** and keeps every OCR
  evidence row. Successful evidence is never discarded.
* **Re-analysis always creates a NEW run.** Prior runs and their evidence
  remain untouched (`GET /processing-runs/{id}` still serves them).
* Every line, region and field carries its `processingRunId`, so the whole
  evidence chain IMAGE → REGION → OCR LINE → FIELD is queryable end to end.

### Run states

`QUEUED → PREPROCESSING → OCR_PROCESSING → VISION_PROCESSING → FIELD_EXTRACTION`
then a terminal state:

| State | Meaning |
| --- | --- |
| `COMPLETED` | All stages succeeded; no low-confidence evidence. |
| `PARTIAL` | OCR succeeded; a later stage (typically vision) failed. Text evidence is preserved. |
| `REVIEW_REQUIRED` | Finished, but some field candidates have low OCR confidence. |
| `FAILED` | A fatal stage failed (preprocessing or OCR). |

### Confidence model

Field candidate confidence is `ocr_confidence × pattern_weight`. The OCR
confidence is the engine's own **recognition** score — it is *OCR confidence*,
never "legal confidence", and it says nothing about legality or sufficiency.

| Extraction outcome | Meaning |
| --- | --- |
| `DETECTED` | Deterministic evidence found with adequate OCR confidence. |
| `REVIEW_REQUIRED` | A pattern matched, but OCR confidence is low (below the review threshold, default `0.6`). A human must confirm. |
| `NOT_EXTRACTED` | The field was located (e.g. an "MRP" label was seen) but no usable value could be read. **Never silently guessed.** |

---

## 2. Processing runs (traceability)

`processing_runs` records, per execution: image + inspection references,
timestamps, duration, status, provider/model/version for OCR and vision, the
pipeline version, the full configuration (preprocessor settings, derivative
storage key, original checksum, review threshold), a summary (counts + models)
and an error payload. References look like `PR-XXXXXXXX`.

Every provider identity is resolved into the existing `model_versions` table
via `resolve_model_version`, and every `ExtractedField` is stamped with its
`model_version_id` — so results are attributable and reproducible.

The human-correction foundation is in place (`extracted_fields.corrected_value`
/ `corrected_at`) but nothing writes it yet; correction UX is future work.

---

## 3. Async execution

Runs are queued in the request transaction (`POST .../perceive` → `202` with
run references) and executed by a FastAPI `BackgroundTask` — no Redis, Celery
or Kafka. Each run opens its own DB session. Clients poll
`GET /inspections/{id}/analysis`; `active: true` means at least one latest run
is still in a non-terminal stage.

---

## 4. Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `PERCEPTION_OCR_BACKEND` | `paddle` | `paddle` (real) or `mock` (tests/demo). |
| `PERCEPTION_OCR_LANGS` | `en` | Comma-separated OCR language list. |
| `PERCEPTION_OCR_TIMEOUT_SECONDS` | `180` | Per-image OCR hard timeout. |
| `PERCEPTION_FIELD_REVIEW_THRESHOLD` | `0.6` | Below this a candidate becomes REVIEW_REQUIRED. |
| `PERCEPTION_OCR_MIN_LONG_EDGE` | `1000` | Preprocessor upscale floor. |
| `PERCEPTION_OCR_MAX_LONG_EDGE` | `2400` | Preprocessor downscale ceiling. |

---

## 5. Testing

* **Unit / API tests** (default suite, no AI engines): the pipeline and routes
  run against deterministic fake OCR/vision providers —
  `tests/test_perception_extract.py`, `tests/test_perception_pipeline.py`,
  `tests/test_perception_api.py`.
* **Integration tests** (real engines, real pixels): marked `integration` and
  excluded from the default run.
  ```bash
  pytest                       # fast suite — no model downloads, no inference
  pytest -m integration        # real PaddleOCR + OpenCV over rendered labels
  ```
  The integration tests render a real label image with Pillow (TrueType text,
  a real QR code, a real EAN-13 barcode) and assert that the engines genuinely
  read the pixels. See `docs/ocr.md` for engine preconditions.

No accuracy percentages are claimed anywhere: the engines' real-world accuracy
on Indian packaging has not been benchmarked by this project.
