# METRASIGHT — OCR Engine (PaddleOCR, local CPU)

> **Status:** the OCR stage of package perception is a REAL local engine
> (PaddleOCR on PaddlePaddle CPU). No OCR text is ever fabricated: every
> `OcrTextResult` row comes from actual inference over actual image pixels, and
> the engine's own recognition score is stored as the line's **OCR confidence**
> (which is a recognition score, never a legal confidence).
>
> **Scope guardrail:** OCR reads text. It does not interpret the Legal
> Metrology Act, and no compliance conclusion is drawn from OCR output.

Sources: `services/api/app/services/ocr/paddle.py`,
`services/api/app/services/interfaces.py` (the `OCRService` seam),
`services/api/app/services/perception/normalize.py`.

---

## 1. Engine and versions

| Component | Version (pinned) | Why pinned |
| --- | --- | --- |
| `paddlepaddle` | `3.0.0` (CPU build) | Last CPU wheel verified with paddleocr 3.1 on Python 3.11 / Windows 11. |
| `paddleocr` | `3.1.0` | Stable PP-OCRv5 pipeline API (`engine.predict`). |
| `paddlex` | `3.1.0` | **Must** match paddleocr 3.1 — paddlex 3.7.x changes `PaddlePredictorOption.__init__` and crashes paddleocr 3.1 at engine construction. |

Install (inside the backend virtualenv):

```bash
pip install "paddlepaddle==3.0.0" "paddleocr==3.1.0" "paddlex==3.1.0"
```

Versions were verified working in this project's environment (Windows 11,
Python 3.11, CPU-only). Compatibility was checked before adoption; if you swap
any of them, re-run `pytest -m integration` to re-verify.

## 2. Model download and caching

* Models are **not** bundled with the repo and are **not** downloaded at server
  boot. The engine is constructed lazily on first OCR use; the first run per
  language downloads the PP-OCRv5 detection + recognition models into
  `~/.paddlex/official_models` (PaddleX's standard cache) and later runs reuse
  the cache.
* If PaddleOCR is not installed, or the models fail to load, the run fails with
  `AI_SERVICE_UNAVAILABLE` and a message pointing at this document — the
  failure is surfaced clearly, never faked.
* Model identity is recorded per run (`ocr_provider` / `ocr_model` /
  `ocr_version`, plus a `model_versions` provenance row), so any result can be
  traced to the exact engine and model family that produced it
  (descriptor name: `paddleocr-pp-ocrv5-{tier}`, default tier `mobile`).

## 2a. Model tier and startup pre-warm (measured optimisation)

`PERCEPTION_OCR_MODEL_TIER` selects the PP-OCRv5 detection + recognition
models:

* `mobile` (**default**) — `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec`.
  Measured ~5× faster on CPU than the server models and at least as accurate
  on this project's synthetic label set (the mobile model even read
  `Batch No:` where the server model read `BatchNo:`).
* `server` — `PP-OCRv5_server_det` + `PP-OCRv5_server_rec`. Highest capacity,
  ~5× slower on CPU.

`PERCEPTION_OCR_PREWARM` (default `true`) loads every configured language's
engine at startup, so the first perception request never pays engine-init
latency (costs ~10 s of boot time when the backend is `paddle`).

**Measured on this project's machine (CPU-only, wall clock, three formal
runs against a pre-warmed server via the real HTTP API):**

| Scenario | Before (server models) | After (mobile + pre-warm) |
| --- | --- | --- |
| Cold first run (engine init + inference) | 36.9 s | ~7 s (first request after boot) |
| Warm per-image run | 26.6–38.5 s | **1.0–1.2 s** (backend `durationMs`) |
| End-to-end demo walkthrough perception step | ~30 s | 2.1 s |

Reproduce with `scripts/profile_perception.py` (stage-level profiler) and
`scripts/perf_three_runs.py` (three live-API runs). Per-stage profile:
preprocessing 0.01–0.03 s, OCR inference ≈ 99 % of pipeline time, vision
0.05 s, extraction ≈ 0 s — the optimisation targeted the only stage that
mattered (model choice + warm engine).

## 3. Languages — what is actually claimed

**Currently configured: English (`en`) only.** `PERCEPTION_OCR_LANGS`
(defaults to `en`) accepts comma-separated PaddleOCR language codes, e.g.
`PERCEPTION_OCR_LANGS=en,devanagari` to add Hindi (Devanagari) support.

The service builds one engine per configured language, merges results, and tags
every OCR line with the language whose engine read it (`language` column).
**Only languages actually configured are claimed** — the system never claims
multilingual support it has not loaded models for, and no accuracy on any
Indian-language packaging is claimed (unbenchmarked).

Practical notes for Indian packaging:

* PaddleOCR ships PP-OCRv5 models for many scripts relevant to India
  (Devanagari/Hindi, Tamil, Telugu, etc.); adding them is a configuration
  change plus a first-run model download, not a code change.
* Bilingual English+Hindi labels are common; running both engines on one image
  is supported by design, at the cost of doubling inference time per image.
* Accuracy on real Indian packaging in this stack has **not been benchmarked**;
  no percentage is claimed anywhere in this project.

## 4. Behavioural contract

* Input: the stored OCR derivative (preprocessed PNG), never the original —
  the original image bytes are immutable evidence.
* Output per line: `raw_text` (verbatim), bbox (normalized 0–1), OCR
  confidence (engine score), language, provider/model/version.
* Inference is serialized behind a lock with a hard timeout
  (`PERCEPTION_OCR_TIMEOUT_SECONDS`, default 180 s) — PaddlePaddle inference is
  not thread-safe.
* A timeout or engine failure raises `AI_SERVICE_UNAVAILABLE`, which fails the
  whole run (OCR is a fatal stage). Failure is reported, never papered over
  with synthetic text.

## 5. Swapping the OCR provider

`OCRService` is a seam: implement `extract_text(*, image_bytes, storage_key,
seed) -> OcrResult` and register the implementation in
`app/services/registry.py`. `PERCEPTION_OCR_BACKEND=mock` selects the
deterministic fake used by the fast test suite; any alternative real engine
(Tesseract, cloud OCR, etc.) drops in the same way — the rest of the pipeline
is provider-agnostic. When swapping, re-verify with
`pytest -m integration` and update this document's version/licence table.

## 6. Licences

| Package | Licence |
| --- | --- |
| PaddleOCR | Apache-2.0 |
| PaddlePaddle | Apache-2.0 |
| PaddleX | Apache-2.0 |
| PP-OCRv5 model weights | Distributed under PaddleOCR's Apache-2.0 terms — verify the model card at download time. |

No credentials or API keys are involved: the engine runs entirely locally, so
there is nothing secret to manage beyond the usual `.env` hygiene.
