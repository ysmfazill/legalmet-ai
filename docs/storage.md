# METRASIGHT — Object Storage

> **Status:** Real package intake (Prompt 3). The storage layer is a **real,
> working** implementation that persists actual uploaded image bytes and serves
> them back to the authenticated frontend.

Sources: `services/api/app/services/storage/base.py` (interface),
`services/api/app/services/storage/local.py` (local-disk default),
`services/api/app/api/routers/storage.py` (retrieval route).

---

## 1. The interface

All persistence goes through the abstract `StorageService`, so the backend is a
swap at the composition root (`services/registry.py`) — call sites never depend
on the implementation:

| Method | Contract |
| --- | --- |
| `save(key, data, content_type?)` | Persist bytes; returns the stored key |
| `read(key)` | Return bytes; raises `NotFoundError` if absent |
| `exists(key)` | Boolean presence check |
| `url(key)` | Retrieval reference for the frontend |
| `delete(key)` | **Idempotent** — a missing object is a successful no-op |
| `get_metadata(key)` | `{key, size, contentType}` |

The default `storage_backend` is `local`, rooted at `storage_dir`
(default `./storage`). A production deployment swaps in an object-store adapter
(e.g. S3) behind the same interface — `url()` would then return a signed URL
instead of the app-relative path.

---

## 2. Storage keys are server-generated — never client input

The intake service builds every key itself from a server UUID; **a client
filename is never used to construct a storage path**:

```
original   inspections/{inspection_id}/{uuid4().hex}.{ext}
processed  inspections/{inspection_id}/processed/{uuid4().hex}.jpg
```

`{ext}` is derived from the **sniffed** image format (`image/png` → `png`), not
the uploaded extension. The client filename is kept only as
`original_filename` for display, after being reduced to a safe basename by
`_safe_filename` (strips directories and `..`, so `../../etc/passwd` → `passwd`).

This means a caller cannot influence *where* bytes land even before the storage
adapter's own guard runs — defence in depth.

---

## 3. Path-traversal defence (the security guarantee)

Even though intake only ever hands it server-generated keys, `LocalStorage` must
keep **every** object inside the storage root no matter what key it is given.
`_resolve` enforces this on every operation (`save` / `read` / `exists` /
`delete` / `get_metadata`):

```python
_SAFE_KEY = re.compile(r"[^a-zA-Z0-9._/\-]")

def _resolve(self, key: str) -> Path:
    safe = _SAFE_KEY.sub("_", key).lstrip("/")
    path = (self._base / safe).resolve()
    if not str(path).startswith(str(self._base)):
        raise NotFoundError("Invalid storage key.")
    return path
```

Two distinct protections, verified in `tests/test_storage.py`:

* **Forward-slash traversal is blocked.** `../../escape.png`,
  `inspections/../../../out.png`, etc. survive the character filter (`.`, `/`,
  `-` are allowed), but `.resolve()` computes a path outside `self._base`, so the
  `startswith` check fails and the operation raises `NotFoundError`. Nothing is
  read or written.
* **Backslashes are sanitised, not treated as separators.** A Windows-style
  `..\..\win.png` has every `\` replaced with `_`, collapsing to a single
  in-root filename (`.._.._win.png`) — it can never escape the root.

The route returns a structured `NotFoundError` rather than leaking whether a path
was rejected for traversal versus genuinely missing.

---

## 4. Retrieval is authenticated

`GET /api/v1/storage/{key:path}` requires a valid bearer token
(`get_current_user`); there are no public object URLs. The handler delegates to
`storage.read(key=...)`, guesses a media type from the key, and returns the raw
bytes. A missing or traversal-rejected key surfaces as a `404`.

Because retrieval needs the `Authorization` header, the frontend cannot use a
bare `<img src>`. It fetches the object as a blob with the token attached and
wraps it in an object URL (`apps/web/src/intake/useObjectUrl.ts`).

---

## 5. Original vs. derivative

The **original bytes are immutable** — stored verbatim under `storage_key` and
never mutated. Any derivative produced by `prepare_image` (EXIF-oriented,
downscaled to `processed_max_dimension`, re-encoded as JPEG which strips
metadata) is written to a **separate** `processed_storage_key`. Deleting an image
removes both objects (idempotently) and the DB row.

---

## 6. Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `storage_backend` | `local` | Adapter selection |
| `storage_dir` | `./storage` | Local-disk root |
| `processed_max_dimension` | `2000` | Longest edge of a prepared derivative |

See [api.md](./api.md) for the upload/validation limits (`max_image_size`,
`max_batch_files`, `min_image_width/height`, `allowed_image_mime_types`).
