# Production hardening (Prompt 9)

What was hardened, verified and measured in the Prompt 9 pass — with the
evidence for each claim. Realistic results only: every number below was
measured on the development machine listed in §1, not extrapolated.

---

## 1. Performance (Phase 16) — measured, CPU-only

Machine: Windows 11 laptop, CPU-only PaddleOCR (PP-OCRv5 server models),
local SQLite. Measure again on the demo machine with
`services/api/scripts/benchmark_phase16.py` — the script drives the real HTTP
API (the same endpoints the frontend uses) with `time.perf_counter()`.

| Measurement | Result | Notes |
| --- | --- | --- |
| Backend startup (warm DB) | ~2.1 s | `uvicorn app.main:app` → "Application startup complete"; demo-inspection seeding skipped (idempotent) |
| Backend first boot, fresh DB | ~1–2 min | pays real OCR for the 3 seeded demo inspections; later boots skip |
| Frontend dev server startup | ~2.5 s | `vite` → ready |
| First OCR run (cold engine) | 35.2 s | engine init + first inference, in a fresh server process |
| Warm OCR run | 25.1 s | engine cached; per-image CPU inference dominates |
| Compliance evaluation | 0.1 s | deterministic engine over stored perception evidence |
| Single-image end-to-end (create → upload → perceive → evaluate) | 26.0 s | warm engine |
| Multi-image (3) end-to-end | 74.7 s | three runs served sequentially by the background worker (~25 s each) |

Verdict: acceptable for a CPU-only, fully-local demo. The OCR engine is the
proven bottleneck; the deterministic compliance layer is effectively free.
No architecture change was warranted — per the spec, none was made.

## 2. Offline / local demo (Phase 17)

Verified: the core demo needs **no external AI API key and no network access
after a one-time model download**.

- Frontend: no external URLs anywhere in `apps/web/src`, `index.html` or the
  CSS; API base is relative (`/api/v1`, proxied to localhost).
- Backend: no outbound HTTP client (no `httpx`/`requests`/vendor SDKs) anywhere
  in `app/`; OCR and vision are local engines.
- Database: local SQLite; regulatory dataset: seeded locally (research-grade,
  clearly labelled UNVERIFIED).
- One-time network need: the first perception run downloads PP-OCRv5 models
  into `~/.paddlex/official_models`; after caching, everything runs locally.
  This is documented in `README.md` § Perception engines and `docs/ocr.md`.

## 3. Demo data (Phase 18)

`DEMO-FOOD`, `DEMO-WATER`, `DEMO-OIL` are seeded at first boot through the
**real services** (intake → real OCR → evaluation → review → decision → audit),
not inserted as rows. See `docs/demo.md`. The seed fails loudly and honestly
(`demo_inspection_partial` / `demo_inspections_failed` log lines) and never
substitutes stub OCR. Disable with `SEED_DEMO_INSPECTIONS=false`.

Implementation note (recorded for maintainers): the seed calls several
services in one SQLAlchemy session. Service queries load relationships via
`selectinload` without `populate_existing`, so a relationship cached earlier
in the same session is served stale; the seed therefore calls `db.expire_all()`
between lifecycle steps. The HTTP path is unaffected (fresh session per
request).

## 4. Security hardening (Phases 10–11, 23)

- **Role enforcement:** every mutating route is role-gated. Four gaps found and
  closed in Prompt 9 (an AUDITOR could previously create inspections, attach
  images, run perception, create batches and record decisions). Regression
  tests enumerate all mutating routes dynamically — `tests/test_api_security.py`.
- **Path traversal:** the local storage backend's guard was vulnerable to a
  sibling-directory prefix collision (`../storage-secret` passed a string
  `startswith` check). Fixed with `Path.is_relative_to`; tested including the
  collision case.
- **Decompression bombs:** uploads are rejected above `MAX_IMAGE_DIMENSION`
  (8000 px) before decode, on top of the byte-size and minimum-resolution
  checks.
- **Error envelopes:** malformed input yields structured 400/404/422 JSON with
  a request ID — no stack traces leak to clients.
- **Secrets:** repo scanned for keys/tokens/passwords; no real credentials
  committed. `.env` is git-ignored; `.env.example` documents variable names
  with placeholder values only. The dev JWT secret is a known
  `dev-only-insecure-change-me` value, and the app logs a warning if it ever
  reaches a production environment with it.

## 5. Database integrity (Phases 9, 12)

- Found and fixed real ORM/migration drift (`packages.status`,
  `field_corrections.created_at`, missing `extracted_fields.corrected_by` FK)
  with an additive migration (`g9c5e3a1f7b2`) — no committed migration was
  modified.
- `tests/test_db_integrity_integration.py` now diffs `Base.metadata` against an
  alembic-upgraded scratch DB column-by-column and checks every FK materialises
  in SQLite — the drift cannot recur silently.

## 6. Reliability (Phases 7–8)

- Duplicate-guard: a repeated perceive/reanalyze request while runs are ACTIVE
  returns the in-flight run instead of queueing duplicates.
- Perception runs are terminal-state machines; partial failures produce
  `PARTIAL`/`FAILED` runs with per-stage errors, never silent success.
- Startup seeding is best-effort and cannot block or crash the app.

## 7. Confidence semantics & traceability (Phases 13–15)

- Every confidence surface in the UI states it is an OCR recognition/detection
  score, not legal confidence (badge tooltips + drawer copy).
- Human corrections never overwrite AI output: the AI original is preserved,
  and perception surfaces + evidence drawers show both values tagged AI/HUMAN.
- Evidence-graph nodes carry an explicit origin (AI / HUMAN / SYSTEM).

## 8. Risk radar (Phase 19) — position, deliberately unchanged

The existing Risk Radar is Prompt 1 demo-scoring over the clearly-labelled
mock adapter (`DEMO SCORING` badge; copy states it is a prioritisation
heuristic, "not a legal grading"). It does **not** consume real compliance
findings yet. Per the Phase 19 constraint, Prompt 9 did **not**:

- create a new backend risk score or black-box model,
- secretly modify the existing score,
- or represent any compliance result as a legal risk probability.

The structured signals a future wiring should consume (all already exposed by
the API, none invented here): finding status/severity, per-field OCR
confidence, image usability grade, and unresolved-review counts. Wiring the
radar to those signals — with its transparent weighted factors unchanged and
documented — is deferred work, listed in the Prompt 10 section of the final
report.

## 9. Known limitations

See the final Prompt 9 report for the full honest list, including: regulatory
dataset is UNVERIFIED research-grade; English OCR only (as configured and
actually tested); aggregate pages (Dashboard, Risk, Reports, Audit) still read
the labelled mock adapter rather than the live API; no frontend unit tests;
inspection `status` is not advanced by the perception/compliance/HITL services
(it reflects intake/analyze transitions only).
