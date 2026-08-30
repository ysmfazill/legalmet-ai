# METRASIGHT — Intake & Perception API

> **Status:** Real package intake (Prompt 3) — followed by the real perception
> API (Prompt 4) in the second half of this document. These endpoints ingest **real**
> uploaded/captured image bytes, validate them server-side, store them, grade
> their usability, and advance an inspection to `READY_FOR_ANALYSIS`.
>
> **Scope guardrail:** nothing here runs OCR, computer vision, product
> classification, or the rule engine. **The strongest possible outcome of
> uploading an image is `READY_FOR_ANALYSIS` — never a compliance verdict.** No
> findings are ever produced by intake.

Sources: `services/api/app/api/routers/images.py`,
`services/api/app/api/routers/storage.py`,
`services/api/app/services/intake/service.py`,
`services/api/app/schemas/image.py`. Interactive contract: Swagger UI at
`/docs`, raw schema at `/openapi.json`.

All routes are under the API prefix (default `/api/v1`). All request/response
bodies are **camelCase** (`CamelModel`). Errors use the uniform envelope
`{"error": {"code", "message", "details?", "requestId?"}}`.

---

## 1. Authentication & roles

Every intake route requires a bearer token. **Mutations** (create package,
upload, batch, quality-check, prepare, delete, mark-ready) require an intake
role — `INSPECTOR`, `SUPERVISOR`, or `ADMIN`. **Reads** (get/list image) require
any authenticated user; auditors are read-only (a `403` on any mutation).

| Failure | Status | `error.code` |
| --- | --- | --- |
| No / invalid token | `401` | — |
| Authenticated but wrong role | `403` | — |

---

## 2. Endpoints

| Method & path | Role | Purpose |
| --- | --- | --- |
| `POST /inspections/{id}/packages` | intake | Create a package (label optional) |
| `POST /inspections/{id}/images/upload` | intake | Upload one image (multipart) |
| `POST /inspections/{id}/images/batch` | intake | Upload many images, per-file isolation |
| `GET  /inspections/{id}/images` | any | List an inspection's images |
| `POST /inspections/{id}/ready` | intake | Transition → `READY_FOR_ANALYSIS` |
| `GET  /images/{id}` | any | Fetch one image record |
| `POST /images/{id}/quality-check` | intake | Recompute usability (deterministic) |
| `POST /images/{id}/prepare` | intake | Produce a display/analysis-ready derivative |
| `DELETE /images/{id}` | intake | Delete image row + stored object(s) → `204` |
| `GET  /storage/{key:path}` | any | Retrieve stored bytes (see [storage.md](./storage.md)) |

---

## 3. Single upload

`POST /inspections/{inspection_id}/images/upload` — `multipart/form-data`:

| Field | Required | Notes |
| --- | --- | --- |
| `file` | yes | The image bytes |
| `captureSource` | no | `CAMERA` / `UPLOAD` / `BATCH` (default `UPLOAD`) |
| `imageType` | no | `FRONT` / `BACK` / … (default `OTHER`) |
| `packageId` | no | Target package; a first package is auto-created if omitted |

**Success `201`** → an `ImageOut` including `mimeType` (server-sniffed),
`width`/`height` (post-EXIF), `fileSize`, `checksum` (SHA-256, 64 hex chars),
`captureSource`, `processingStatus` (`PENDING`), `qualityGrade`, `qualityScore`,
`qualityMetrics`, `storageKey`, `url`, and `isDemo: false`.

---

## 4. Server-authoritative validation

The accept/reject decision is made from the **actual decoded bytes**, never the
client-supplied filename, extension, or `Content-Type`. Client-side checks are
UX only; this is the authority.

Order of checks in `_validate_and_sniff` → checksum → duplicate:

| Check | On failure | Status | `error.code` |
| --- | --- | --- | --- |
| Non-empty | empty upload | `400` | `INVALID_IMAGE` |
| Size ≤ `max_image_size` (15 MiB) | too large | `413` | `IMAGE_TOO_LARGE` |
| Decodes + `verify()` passes | corrupt/truncated | `400` | `INVALID_IMAGE` |
| Sniffed format ∈ allowed MIME list | e.g. GIF | `415` | `UNSUPPORTED_FILE` |
| Original extension ∈ {jpg,jpeg,png,webp} if present | bad ext | `415` | `UNSUPPORTED_FILE` |
| `width ≥ 400` and `height ≥ 400` | too small | `400` | `INVALID_IMAGE` |
| SHA-256 not already on this inspection | duplicate | `409` | `CONFLICT` |

The declared client MIME is recorded for provenance but ignored for the
decision: a PNG mislabeled `image/jpeg` is stored as `image/png`. EXIF
orientation is normalised before dimensions are measured (an `800×600` photo
tagged rotate-90° is recorded as `600×800`).

---

## 5. Batch upload

`POST /inspections/{inspection_id}/images/batch` — repeated `files` parts
(optional `packageId`). Per-file failures are **isolated**: one bad file never
aborts the rest. Exceeding `max_batch_files` (default 20) rejects the whole
request with `422 VALIDATION_ERROR`.

**Success `201`** → `BatchUploadResponse`:

```json
{
  "uploaded": 2,
  "rejected": 1,
  "items": [
    { "filename": "a.png",  "status": "UPLOADED", "image": { "...": "ImageOut" } },
    { "filename": "bad.png", "status": "REJECTED", "error": { "code": "INVALID_IMAGE", "message": "…" } },
    { "filename": "c.jpg",  "status": "UPLOADED", "image": { "...": "ImageOut" } }
  ]
}
```

Every uploaded item carries its full `ImageOut` (with usability grade); every
rejected item carries the `{code, message}` reason and a `null` image.

---

## 6. Lifecycle: mark ready

`POST /inspections/{inspection_id}/ready` transitions the inspection (and each
package that has images) to `READY_FOR_ANALYSIS`.

* Requires **at least one attached image** → else `422 VALIDATION_ERROR`.
* Requires at least one image **not graded `REJECTED`** → else `409 CONFLICT`.
* Performs **no analysis** and asserts **no compliance conclusion**. After
  marking ready, `GET /inspections/{id}/findings` still returns `[]`.

---

## 7. Single-image operations

* **`POST /images/{id}/quality-check`** — re-reads the stored original and
  recomputes usability (deterministic: unchanged bytes → identical score). See
  [image-quality.md](./image-quality.md).
* **`POST /images/{id}/prepare`** — EXIF-orient, downscale to
  `processed_max_dimension` (2000), re-encode JPEG (strips metadata). Sets
  `processingStatus: READY` and populates `processedStorageKey` / `processedUrl`.
  The **original is untouched**. This is preparation, not analysis.
* **`DELETE /images/{id}`** — removes the DB row and both stored objects
  (idempotent) → `204`.

---

## 8. Audit trail

Every intake step appends an append-only audit event (see
`app/services/audit`), including on rejection. A representative single-upload +
prepare + delete produces:

```
PACKAGE_CREATED
IMAGE_UPLOAD_STARTED      (recorded before validation, so rejects leave a trace)
IMAGE_UPLOADED            (bytes validated + stored)
QUALITY_CHECK_COMPLETED   (usability graded)
IMAGE_PREPARED
IMAGE_DELETED
```

A rejected upload records `IMAGE_UPLOAD_STARTED` then `IMAGE_REJECTED` (with the
`error.code` and reason), and both are committed even though the request errors.

---

## 9. Configuration

| Setting | Default | Effect |
| --- | --- | --- |
| `max_image_size` | `15 MiB` | Per-file size ceiling (`413` above) |
| `max_batch_files` | `20` | Batch count ceiling (`422` above) |
| `min_image_width` / `min_image_height` | `400` / `400` | Resolution floor (`400`) |
| `allowed_image_mime_types` | `image/jpeg,image/png,image/webp` | Accepted formats (`415` otherwise) |
| `processed_max_dimension` | `2000` | Longest edge of a prepared derivative |

Storage-side configuration and the retrieval route are documented in
[storage.md](./storage.md); the usability grader in
[image-quality.md](./image-quality.md).

---
---

# Perception API (Prompt 4)

> **Status:** Real multimodal package perception. These endpoints run **real**
> OCR (PaddleOCR, local CPU) and real QR/barcode detection (OpenCV) over the
> stored package images and return structured, traceable perception evidence:
> OCR text lines, visual regions, extracted field candidates and processing-run
> history. No values are hard-coded and no confidence is fabricated — a run
> either reads the image or fails visibly.
>
> **Scope guardrail:** perception answers *“what can the system see?”* — nothing
> more. **The strongest possible outcome of these routes is perception evidence
> plus an explicit `AWAITING_REGULATORY_EVALUATION` marker — never a compliance
> verdict, never a compliance score.** Field statuses (`DETECTED`,
> `REVIEW_REQUIRED`, `NOT_EXTRACTED`) describe evidence quality, not legality.

Sources: `services/api/app/api/routers/perception.py`,
`services/api/app/services/perception/` (service, pipeline, extractor),
`services/api/app/schemas/perception.py`. Pipeline internals:
[perception.md](./perception.md); engines: [ocr.md](./ocr.md),
[vision.md](./vision.md).

---

## 1. Authentication & roles

Same rules as intake: all routes require a bearer token. **Mutations**
(`perceive`, `reanalyze`) require a perception role — `INSPECTOR`, `SUPERVISOR`
or `ADMIN`; **reads** (analysis, OCR, regions, fields, runs) allow any
authenticated user. Auditors are read-only.

| Failure | Status | `error.code` |
| --- | --- | --- |
| No / invalid token | `401` | — |
| Authenticated but wrong role | `403` | — |
| Unknown inspection / image / run | `404` | `NOT_FOUND` |
| Inspection has no analysable images | `422` | `VALIDATION_ERROR` |

---

## 2. Endpoints

| Method & path | Role | Purpose |
| --- | --- | --- |
| `POST /inspections/{id}/perceive` | perception | Queue one run per analysable image → `202` |
| `POST /images/{id}/reanalyze` | perception | Queue a NEW run for one image (history kept) → `202` |
| `GET  /inspections/{id}/analysis` | any | Aggregated perception summary + poll state |
| `GET  /inspections/{id}/ocr` | any | All OCR text lines (raw + normalized) |
| `GET  /inspections/{id}/regions` | any | All visual regions (text/symbol) |
| `GET  /inspections/{id}/fields` | any | Extracted field candidates + statuses |
| `GET  /inspections/{id}/processing` | any | Processing-run history |
| `GET  /processing-runs/{run_id}` | any | One run's full detail (incl. old runs) |

---

## 3. Starting perception

`POST /inspections/{inspection_id}/perceive` creates one **QUEUED**
`ProcessingRun` per attached, non-`REJECTED` image (multi-image support:
front/back/side each get their own run and evidence). **Success `202`**:

```json
{
  "inspectionId": "…",
  "runs": [
    { "runId": "…", "reference": "PR-3F9A2C1D", "imageId": "…" },
    { "runId": "…", "reference": "PR-8B01EE44", "imageId": "…" }
  ]
}
```

The runs execute asynchronously in a background task (no Redis/Celery/Kafka);
each run uses its own DB session. No images are analysable → `422`.

`POST /images/{image_id}/reanalyze` behaves identically but for a single image,
and **always creates a new run** — prior runs and all their evidence rows
remain queryable via `GET /processing-runs/{run_id}`.

---

## 4. Reading results

* **`GET /inspections/{id}/analysis`** — per-image summary (text lines,
  regions, declarations, low-confidence count, duration, models), run history
  and an `active` flag for polling. Always carries
  `regulatoryEvaluation: "AWAITING_REGULATORY_EVALUATION"`.
* **`GET /inspections/{id}/ocr`** — every `OcrTextResult` across runs:
  `rawText` **verbatim** from the engine, derived `normalizedText`, normalized
  bbox, `confidence` (the engine's **OCR confidence** — not legal confidence),
  `language`, provider/model/version, `regionId`, `processingRunId`.
* **`GET /inspections/{id}/regions`** — `ImageRegion` rows: `TEXT_LINE`
  (derived from OCR boxes), `QR_CODE` / `BARCODE` with payload
  `{symbology, value, decoded}` (undecodable-but-detected symbols are reported
  with `decoded: false`, never given an invented value).
* **`GET /inspections/{id}/fields`** — `ExtractedField` candidates:
  `fieldType`, `rawText`, `normalizedValue`, `unit`,
  `confidence` = OCR confidence × pattern weight, `extractionMethod`,
  `status` ∈ `DETECTED` / `REVIEW_REQUIRED` / `NOT_EXTRACTED`, plus the full
  evidence linkage (`sourceOcrResultId`, `imageRegionId`, `processingRunId`,
  `modelVersionId`).

---

## 5. Failure semantics

| Situation | Run outcome | API surface |
| --- | --- | --- |
| OCR engine unavailable / timed out / models missing | `FAILED`, `error.code = AI_SERVICE_UNAVAILABLE` (+ failing stage) | Runs readable; analysis shows the error — **never fake text** |
| Vision stage failed | `PARTIAL`, `error.code = VISION_STAGE_FAILED`; all OCR evidence kept | OCR/fields still returned |
| Unexpected internal error | `FAILED`, `error.code = INTERNAL_ERROR` (sanitized message, no internals leaked) | Run readable |
| Low-confidence field candidates | `REVIEW_REQUIRED` terminal status | Fields carry `REVIEW_REQUIRED` |

---

## 6. Audit trail

Perception appends: `PERCEPTION_STARTED` (per run, with reference),
`PERCEPTION_COMPLETED` (with status + evidence counts) or `PERCEPTION_FAILED`
(with code + stage), and `IMAGE_REANALYZED` on re-analysis. All events include
the inspection id and actor (where a user initiated it).

---

## 7. Configuration

See [perception.md](./perception.md) §4 for the full table
(`PERCEPTION_OCR_BACKEND`, `PERCEPTION_OCR_LANGS`,
`PERCEPTION_OCR_TIMEOUT_SECONDS`, `PERCEPTION_FIELD_REVIEW_THRESHOLD`,
preprocessor edge bounds) and [ocr.md](./ocr.md) for engine installation and
model caching.

---

# Part 3 — Regulatory Intelligence API (Prompt 5)

> **Scope guardrail:** these endpoints expose the Source → Document → Version
> → Requirement hierarchy with full provenance. They never evaluate compliance
> — the strongest statement they make about a perceived field is *"candidate
> requirement — applicability not evaluated, awaiting the compliance engine"*.
> **Regulatory intelligence is not itself a legal determination.**

Sources: `services/api/app/api/routers/regulations.py`,
`services/api/app/services/regulatory/service.py`. Full design notes:
[regulatory.md](./regulatory.md).

All routes require a bearer token. Reads are available to any authenticated
user. The **only** mutation is `PATCH /regulations/sources/{id}` — ADMIN-only
and audited (a `REGULATORY_SOURCE_UPDATED` event records the before/after
verification states).

## 1. Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/regulations/sources` | filters: `verificationStatus`, `sourceType` |
| GET | `/regulations/sources/{id}` | |
| PATCH | `/regulations/sources/{id}` | **ADMIN, audited**; body `{verificationStatus, verificationNote?}` — a note is *required* to move to `VERIFIED` |
| GET | `/regulations/documents` | filters: `sourceId`, `documentType`, `isDemo` |
| GET | `/regulations/documents/{id}` | includes the version list |
| GET | `/regulations/versions` | filters: `documentId`, `status`, `effectiveOn` |
| GET | `/regulations/versions/resolve` | `documentId` + `on` → deterministic selection |
| GET | `/regulations/requirements` | paginated; filters incl. `versionId`, `documentId`, `sourceId`, `fieldKey`, `requirementType`, `category`, `status`, `effectiveOn`, `current`, `isDemo` |
| GET | `/regulations/requirements/{id}` | full `provenance` object |
| GET | `/inspections/{id}/regulatory-candidates` | field → candidate requirements |

Prompt 1's demo endpoints (`GET /regulations`, `GET /rules`,
`GET /rules/validators`) are unchanged.

## 2. Version resolution

`GET /regulations/versions/resolve?documentId=…&on=2016-06-01T00:00:00Z`
returns:

```json
{
  "documentId": "…",
  "requestedDate": "2016-06-01T00:00:00Z",
  "status": "FOUND",              // or NO_APPLICABLE_VERSION
  "version": { "versionLabel": "as amended by G.S.R. 385(E)/2015", … }
}
```

`NO_APPLICABLE_VERSION` is an explicit state (`version: null`) — the resolver
**never silently falls back to the newest version**.

## 3. Candidate mapping

`GET /inspections/{id}/regulatory-candidates[?on=…]` maps each extracted
field from the latest perception run per image to requirement definitions in
force at the context date (default: the inspection's creation date):

```json
{
  "inspectionId": "…",
  "contextDate": "2026-08-28T…",
  "fields": [
    {
      "fieldId": "…", "fieldType": "MRP", "fieldStatus": "DETECTED",
      "candidates": [
        {
          "requirementId": "…", "ruleCode": "LM-PC-2011-6.1(e)",
          "versionLabel": "as amended through G.S.R. 629(E)/2017 (consolidated)",
          "effectiveFrom": "2017-06-23T00:00:00Z",
          "sourceReference": "…", "sourceVerificationStatus": "UNVERIFIED"
        }
      ],
      "mappingStatus": "CANDIDATE",
      "applicabilityStatus": "APPLICABILITY_NOT_EVALUATED",
      "evaluationStatus": "AWAITING_COMPLIANCE_ENGINE"
    }
  ],
  "regulatoryEvaluation": "AWAITING_REGULATORY_EVALUATION"
}
```

No compliance verdict exists on this route — see [regulatory.md](./regulatory.md) §5.

---

# Part 4 — Deterministic Compliance Engine API (Prompt 6)

> **Boundary statement:** compliance findings are system-generated
> decision-support outputs. **They are not, by themselves, legal enforcement
> determinations.** The deterministic engine never claims that an AI model
> determines legality — the inspector remains responsible for the final
> enforcement decision.

Sources: `services/api/app/api/routers/compliance.py`,
`services/api/app/services/compliance/service.py`. Full design notes:
[compliance.md](./compliance.md).

All routes require a bearer token. Reads are available to any authenticated
user. The **only** mutation is `POST /inspections/{id}/evaluate` — restricted
to INSPECTOR / SUPERVISOR / ADMIN (it writes audit events). It creates a NEW
evaluation row every time; historical evaluations are never overwritten.

## 1. Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/inspections/{id}/evaluate` | **INSPECTOR+, audited**; body optional (nothing is tunable — the run is fully determined by the inspection's evidence and the version in force) |
| GET | `/inspections/{id}/compliance` | latest evaluation, or `status=NOT_EVALUATED` + `evaluation=null` when none has run |
| GET | `/inspections/{id}/compliance/findings` | findings of the LATEST evaluation (engine vocabulary) |
| GET | `/compliance/evaluations/{id}` | one historical evaluation, findings included — reproducible |
| GET | `/compliance/findings/{id}` | one finding with explanation, rule trace and frozen provenance |
| GET | `/compliance/engine` | engine version, the 13-type rule vocabulary, `usesLlm: false` |
| GET | `/compliance/review/queue` | paginated (page/pageSize) findings awaiting an inspector decision |

Path note: `GET /inspections/{id}/findings` (no `/compliance` segment) is the
Prompt 1 demo endpoint and is unchanged — engine findings live under the
`/compliance` namespace so the two vocabularies never mix.

## 2. Evaluation payload

```json
{
  "evaluation": {
    "id": "…", "inspectionId": "…",
    "regulatoryVersionId": "…",            // version in force at context date
    "status": "REVIEW_REQUIRED",           // NOT_EVALUATED | EVALUATING | COMPLETED | PARTIAL | FAILED | NO_APPLICABLE_REQUIREMENT
    "engineVersion": "1.0.0",
    "contextDate": "2026-06-01T00:00:00Z",
    "summary": {                            // COUNTS ONLY — never a percentage
      "totalFindings": 7,
      "byStatus": { "COMPLIANT": 5, "REVIEW_REQUIRED": 1, "NOT_DETECTED": 1 },
      "reviewQueueCount": 2,
      "requirementsEvaluated": 7
    },
    "error": null,                          // {code, message} when FAILED
    "findings": [ … ]
  },
  "boundaryNote": "System finding — inspector decision pending. …"
}
```

## 3. Finding payload

```json
{
  "id": "…", "evaluationId": "…", "inspectionId": "…", "requirementId": "…",
  "extractedFieldId": "…", "evidenceRegionId": "…", "imageId": "…",
  "status": "NON_COMPLIANT",                // COMPLIANT | NON_COMPLIANT | REVIEW_REQUIRED | NOT_DETECTED | NOT_APPLICABLE | NOT_EVALUATED
  "severity": "MAJOR",                      // triage label, not a legal penalty
  "applicability": "YES",                   // YES | NO | UNKNOWN
  "detectedValue": "MRP ₹ 60.00",
  "expectedValue": "MRP ₹__ (inclusive of all taxes)",
  "explanation": "…seven-question deterministic explanation…",
  "provenance": {                           // frozen at evaluation time
    "requirementCode": "LM-PC-2011-6.1(e)",
    "versionId": "…", "versionLabel": "as amended through G.S.R. 629(E)/2017 (consolidated)",
    "documentTitle": "…", "sourceName": "…", "sourceVerificationStatus": "UNVERIFIED"
  },
  "detail": {
    "rules": [                              // per-rule trace
      { "ruleCode": "LM-PC-2011-6.1(e):MRP_FORMAT", "ruleType": "MRP_FORMAT",
        "passed": false, "reason": "…", "expected": "…" }
    ],
    "evidenceFieldIds": ["…"], "searchedRunIds": ["…"],
    "fieldKey": "MRP", "evidenceCount": 1
  },
  "boundaryNote": "System finding — inspector decision pending. …"
}
```

`NOT_DETECTED` findings carry `detail.absence: "FIELD_NOT_FOUND"` — missing
OCR is never legal non-compliance and never evidence the declaration is
absent from the package.

## 4. Review queue

`GET /compliance/review/queue` returns the standard paginated envelope over
findings with status `REVIEW_REQUIRED`, `NON_COMPLIANT`, `NOT_DETECTED` or
`NOT_EVALUATED` from each inspection's **latest** evaluation only. The queue
is read-only: no decision/approval/verdict fields exist on any item —
recording the inspector's final enforcement decision is a later phase.

## 5. Audit events

`COMPLIANCE_EVALUATION_STARTED` (with engine version + context date),
`COMPLIANCE_EVALUATION_COMPLETED` (status + finding count) or
`COMPLIANCE_EVALUATION_FAILED` (error code + message), and
`COMPLIANCE_FINDING_CREATED` per finding (finding id + status + requirement
code).
