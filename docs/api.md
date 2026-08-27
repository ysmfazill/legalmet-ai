# LEGALMET AI — Intake API

> **Status:** Real package intake (Prompt 3). These endpoints ingest **real**
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
