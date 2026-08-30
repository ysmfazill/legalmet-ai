# METRASIGHT — Image Usability Grading

> **Status:** Real package intake (Prompt 3). Unlike the perception mocks, this
> subsystem is a **real, working** implementation — it computes a reproducible
> verdict from the actual pixels of an uploaded photo.
>
> **What it is NOT:** the score is an **image-usability** signal only. It is
> **not** an AI-confidence score, **not** a compliance / Legal-Metrology
> judgement, and it never asserts that a package is `COMPLIANT`, a `VIOLATION`,
> or `LEGAL`. No OCR, object detection, or rule evaluation happens here.

Source: `services/api/app/services/quality/pillow.py`
(`PillowImageQualityAnalyzer`).

---

## 1. Purpose

The grader answers one question: **how usable is this image for reading a label
later — by a human or a machine?** It exists so that, at intake time, an
inspector gets immediate, honest feedback ("this photo is too dark / too small /
too blurry — retake it") *before* any analysis is attempted, and so the stored
record carries a trustworthy legibility signal.

It is deterministic Pillow-only image statistics — **no numpy, no OpenCV, no
learned parameters**. Same bytes in → same result out. That reproducibility is
what makes it safe to assert on in tests and to record as a provenance input.

---

## 2. What it measures

The image is decoded, EXIF-oriented (`ImageOps.exif_transpose`), converted to
luminance (`L`), and downscaled to a bounded copy (`_STATS_MAX_DIM = 1024`) so
cost is independent of input size. Four component scores are computed, each
normalised to `0..1`:

| Component | Signal | Derivation | Normalisation constant |
| --- | --- | --- | --- |
| **Resolution** | Is there enough detail? | `min(width, height) / 1600` | `1600` px reference |
| **Sharpness** | Is it in focus? | std-dev of a `FIND_EDGES` pass | `_SHARPNESS_FULL = 34.0` |
| **Contrast** | Is there tonal spread? | std-dev of luminance | `_CONTRAST_FULL = 72.0` |
| **Brightness** | Is exposure sensible? | `1 − |mean − 0.55| / 0.55` | `_IDEAL_BRIGHTNESS = 0.55` |

These constants are **empirical and deterministic**, not trained weights. Each
component describes legibility potential only — never legal conformity.

---

## 3. The overall score

The four components combine into a single weighted usability score
(`0.0 … 1.0`), rounded to three decimals:

```
overall = 0.35 · resolution
        + 0.30 · sharpness
        + 0.20 · contrast
        + 0.15 · brightness
```

Resolution and sharpness dominate because an unreadable-small or out-of-focus
label is unusable no matter how well-exposed it is.

---

## 4. Grades

The score maps onto an `ImageQualityGrade` band (highest matching threshold
wins):

| Grade | Score band | Meaning (usability only) |
| --- | --- | --- |
| `EXCELLENT` | `≥ 0.85` | Crisp, well-exposed, high-resolution |
| `GOOD` | `≥ 0.70` | Clearly usable |
| `ACCEPTABLE` | `≥ 0.50` | Usable, some degradation |
| `POOR` | `≥ 0.30` | Legible-ish; a retake is advised |
| `REJECTED` | `< 0.30` | Not usable |

**Hard resolution floor.** Independent of the weighted score, an image below the
configured minimum (`min_image_width` / `min_image_height`, default `400×400`)
is graded `REJECTED` with status `LOW_RESOLUTION` and its score capped at
`0.29`. In the intake pipeline this floor is enforced *earlier still*:
`_validate_and_sniff` raises `InvalidImageError` for sub-minimum images **before
grading**, so they are never stored (see [storage.md](./storage.md) and
[api.md](./api.md)).

---

## 5. Metrics payload

Every grade carries a `quality_metrics` object (camelCase, persisted as JSON and
returned on the image). It is a transparent breakdown, not a black box:

```json
{
  "width": 800,
  "height": 600,
  "megapixels": 0.48,
  "minDimension": 600,
  "brightness": 0.55,
  "contrast": 41.2,
  "sharpness": 22.8,
  "resolutionScore": 0.375,
  "sharpnessScore": 0.671,
  "contrastScore": 0.572,
  "brightnessScore": 0.998
}
```

A rejected-for-resolution image additionally carries
`"rejectedReason": "LOW_RESOLUTION"`.

---

## 6. Failure handling

* **No bytes** → `REJECTED`, status `UNKNOWN`, score `0.0` (defensive guard;
  intake always supplies bytes).
* **Corrupt / undecodable bytes** → caught (`OSError`/`ValueError`/`SyntaxError`)
  → `REJECTED`, status `UNKNOWN`, score `0.0`. The grader never raises to its
  caller.

A legacy `ImageQualityStatus` (`OK` / `BLURRY` / `GLARE` / `INSUFFICIENT` /
`LOW_RESOLUTION` / `UNKNOWN`) is also derived, for back-compatibility with the
pre-Prompt-3 aggregate-quality read path. The **grade** is the authoritative
Prompt-3 signal.

---

## 7. Where it runs

* **On upload** — `IntakeService.upload_image` grades the accepted bytes and
  writes `quality_score`, `quality_grade`, `quality_status`, `quality_metrics`
  onto the `Image` row, then emits a `QUALITY_CHECK_COMPLETED` audit event.
* **On demand** — `POST /images/{id}/quality-check` re-reads the stored original
  and recomputes. Because the analyzer is deterministic, re-checking unchanged
  bytes yields an identical score.

The `ImageQualityAnalyzer` interface (`app/services/interfaces.py`) is the seam:
the deterministic Pillow analyzer is the intake default; the demo pipeline still
uses its mock. Neither ever produces a compliance conclusion.
