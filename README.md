# METRASIGHT

**Evidence-grounded, version-aware, AI-assisted compliance inspection for packaged commodities.**

METRASIGHT is an AI-assisted Legal Metrology inspection intelligence platform
that combines package perception, version-aware regulatory intelligence,
deterministic rule evaluation, evidence traceability, and human inspector
review.

> ⚠️ **DEMO REGULATORY DATA — NOT LEGAL ADVICE.** This build contains
> clearly-labelled UNVERIFIED research-grade regulatory data. Perception is
> **real** (local PaddleOCR + OpenCV read the actual uploaded images — Prompt 4)
> and the deterministic compliance engine really evaluates perceived fields
> against that unverified dataset — but nothing here has been checked against
> official Gazette text. Findings are decision support; the inspector decides.
> It must not be used for real compliance decisions.

---

## Problem statement (SIH26034)

- **ID:** SIH26034
- **Title:** Software system to check compliance of packaged commodities under
  the *Legal Metrology (Packaged Commodities) Rules, 2011* by scanning products,
  images and labels.
- **Ministry:** Ministry of Consumer Affairs, Food & Public Distribution
- **Category:** Software · **Theme:** Agriculture, FoodTech & Rural Development

The system inspects package labels, locates mandatory declarations (MRP, net
quantity, manufacturer/packer details, country of origin, dates, consumer care,
etc.), and evaluates them against version-aware regulatory rules — producing
**evidence-grounded** findings a human inspector can review, rather than an
opaque pass/fail.

---

## Current architecture (foundation phase)

A monorepo with a shared type contract, a FastAPI backend, and a React frontend.

```
legalmet-ai/
├─ packages/types    @legalmet/types   — shared enums, models, API contracts (TS)
├─ packages/config   @legalmet/config  — labels, status tones, app constants (TS)
├─ apps/web          @legalmet/web     — Vite + React + TS frontend (shell)
└─ services/api      FastAPI backend (Python 3.11+, SQLAlchemy, Alembic)
```

- **Shared contract:** domain enums are mirrored byte-for-byte between
  `@legalmet/types` (TS) and `app/core/enums.py` (Python) — one vocabulary
  across the stack.
- **Backend:** application-factory FastAPI app with a uniform error envelope,
  request-ID correlation, structured logging, JWT auth, a pluggable service
  layer, and a **deterministic** (non-AI) rule engine as the *only* component
  that concludes compliance.
- **Perception is real (Prompt 4):** real image intake (Prompt 3), then a real
  OCR engine (PaddleOCR, local CPU) and real QR/barcode detection (OpenCV)
  behind replaceable provider seams (`OCRProvider`, `VisionProvider`,
  `FieldExtractionProvider`, `ImagePreprocessor`). The legacy demo compliance
  flow keeps its clearly-labelled mock services.
- **Frontend:** Inspection Workspace with real package intake, an image viewer
  (zoom/pan, OCR/region overlays) and a perception panel with per-field
  evidence drawers, plus a Regulatory Intelligence page over the real
  Source → Document → Version → Requirement hierarchy.
- **Regulatory intelligence is real (Prompt 5):** version-aware, provenance-
  bearing requirement data for the Legal Metrology (Packaged Commodities)
  Rules, 2011 — deterministic effective-date selection with an explicit
  NO_APPLICABLE_VERSION state, a research-grade UNVERIFIED seed (nothing
  fabricated, nothing dressed up as official law) and a loud-failing
  data-quality gate. Perceived fields map to *candidate* requirements only;
  **no compliance verdict exists in this layer**.
- **Deterministic compliance engine (Prompt 6):** (detected field + applicable
  requirement + deterministic rule) → evaluation → finding, each with
  detected/expected values, a seven-question explanation, a frozen regulatory
  provenance snapshot and evidence references. No LLM anywhere; decimal-safe
  numerics; missing OCR is `NOT_DETECTED`, never a violation; insufficient
  evidence is `REVIEW_REQUIRED`, never a guess; summaries are counts only —
  no fake percentages. Evaluations are immutable history; the review queue is
  read-only. **Compliance findings are system-generated decision-support
  outputs — they are not, by themselves, legal enforcement determinations;
  the inspector remains responsible for the final decision.**

Perception docs: [`docs/perception.md`](docs/perception.md) (pipeline),
[`docs/ocr.md`](docs/ocr.md) (engine setup, languages, licences),
[`docs/vision.md`](docs/vision.md) (region detection, licences).
Regulatory docs: [`docs/regulatory.md`](docs/regulatory.md) (provenance
hierarchy, versioning, seed honesty contract, candidate mapping).
Compliance-engine docs: [`docs/compliance.md`](docs/compliance.md)
(pipeline, rule vocabulary, explainability, legal-safety invariants).
Review/decision docs: [`docs/human-review.md`](docs/human-review.md).
Reporting docs: [`docs/reports.md`](docs/reports.md) (report lifecycle,
finalization gate, Evidence Pack, PDF/DOCX exports, versioning, audit).

**Production hardening (Prompt 9):** role enforcement on every mutating route,
storage path-traversal fix, upload dimension guard, ORM/migration drift
eliminated with a drift-guard integration test, duplicate-run guards,
measured performance (see [`docs/production-hardening.md`](docs/production-hardening.md)),
an offline local demo with four seeded full-lifecycle demo inspections
(`DEMO-FOOD` / `DEMO-WATER` / `DEMO-OIL` / `DEMO-QUINOA` — see [`docs/demo.md`](docs/demo.md)),
and honest confidence/AI-vs-HUMAN semantics throughout the UI.

See [`docs/architecture.md`](docs/architecture.md) for the full design.

---

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| **Node.js** | ≥ 20 (tested on 24) | Frontend + shared packages |
| **npm** | ≥ 10 | Ships with Node; workspaces used |
| **Python** | ≥ 3.11 | Backend |
| **Docker** | optional | Only for local PostgreSQL; SQLite works with zero config |

---

## Installation

> **Fastest path (one command):** after the prerequisites below are installed
> once, `npm run demo` starts the whole localhost demo (backend + frontend,
> Ctrl+C stops both). `npm run demo -- --fresh` also wipes the local demo
> database so first boot re-seeds through the real services. The full
> step-by-step equivalent is in the sections below.

### 1. Frontend / shared packages (from the repo root)

```bash
npm install
```

This installs all workspaces (`packages/*`, `apps/web`) and links the shared
packages.

### 2. Backend (Python)

```bash
cd services/api
python -m venv .venv
# Windows (bash):   source .venv/Scripts/activate
# macOS / Linux:    source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # optional; sensible SQLite defaults work as-is
```

### 3. Perception engines (optional — real OCR / symbol detection)

Real perception uses locally-installed engines (no API keys, no network calls
after setup):

```bash
pip install "paddlepaddle==3.0.0" "paddleocr==3.1.0" "paddlex==3.1.0"
```

`paddlex` **must** stay pinned to 3.1.0 (newer versions break paddleocr 3.1).
The first perception run downloads the PP-OCRv5 models into
`~/.paddlex/official_models` and caches them; if the engines or models are
missing, runs fail with a clear `AI_SERVICE_UNAVAILABLE` error rather than
faking output. Only English OCR models are configured by default — additional
Indian-script models are a `PERCEPTION_OCR_LANGS` setting plus first-run
download. Full details, verified versions and licences:
[`docs/ocr.md`](docs/ocr.md) and [`docs/vision.md`](docs/vision.md).

---

## Database startup

The backend runs **zero-config against SQLite** by default — nothing to start.

For the production-intended **PostgreSQL** (optional locally):

```bash
cp .env.example .env          # repo root — sets POSTGRES_* for docker-compose
docker compose up -d db       # Postgres on :5432 (+ Adminer UI on :8080)
```

Then point the backend at it in `services/api/.env`:

```
DATABASE_URL=postgresql+psycopg2://legalmet:legalmet@localhost:5432/legalmet
```

Apply migrations (Alembic is the schema source of truth):

```bash
cd services/api
alembic upgrade head
```

> On startup the backend also creates tables (dev convenience), seeds
> clearly-labelled **demo** users/rules when `SEED_DEMO_DATA=true`, and — on a
> fresh database — seeds **four full-lifecycle demo inspections**
> (`DEMO-FOOD` / `DEMO-WATER` / `DEMO-OIL` / `DEMO-QUINOA`) through the real
> services, including real local OCR (~2 minutes on CPU, first boot only;
> later boots skip). Disable with `SEED_DEMO_INSPECTIONS=false`. Details:
> [`docs/demo.md`](docs/demo.md).

---

## Backend startup

```bash
cd services/api
source .venv/Scripts/activate      # or .venv/bin/activate on macOS/Linux
uvicorn app.main:app --reload      # http://localhost:8000
```

- API base: `http://localhost:8000/api/v1`
- Health check: `GET http://localhost:8000/api/v1/health`
- Swagger UI: `http://localhost:8000/docs` · OpenAPI: `/openapi.json`

Default demo credentials (override for any real use):
`admin@legalmet.local` / `changeme-admin`,
`inspector@legalmet.local` / `changeme-inspector`.

---

## Frontend startup

```bash
# from the repo root
npm run dev:web                    # http://localhost:5173
```

The dev server proxies `/api` → `http://localhost:8000`, so with the backend
running the shell shows a live **"Connected"** status. To target a different
backend, set `VITE_API_BASE_URL` (see `apps/web/.env.example`).

**Entry flow:** the app opens on a public entry page (`/`) with three access
modes — **Citizen** (anonymous, no account, straight into Citizen Mode),
**Inspector Login** and **Department Login** (both real `POST /auth/login`;
they land on the Inspector Workspace and the Department Command Center
respectively). Staff sessions persist via the stored JWT and restore on
refresh; the top bar has a **Sign out** button. All staff routes redirect
anonymous visitors back to the entry page (UX only — real authorization is
the backend's per-endpoint JWT + role checks).

---

## Testing & verification

**Backend (pytest):**

```bash
cd services/api
python -m pytest            # fast suite (no AI engines, no model downloads)
pytest -m integration       # REAL PaddleOCR + OpenCV over rendered label images (slow)
python -m ruff check .      # lint
```

Integration tests need the perception engines installed (see above) and are
deselected by default; the fast suite runs on in-memory SQLite with the real
preprocessor/extractor logic and only the OCR/vision engines swapped at the
provider seams. Full layout and guarantees: [`docs/testing.md`](docs/testing.md).

**Frontend / shared packages (from the repo root):**

```bash
npm run typecheck           # tsc --noEmit across all workspaces
npm run lint                # ESLint
npm run build:web           # production build of @legalmet/web
```

**Demo:** how to run the full local demo (offline after one model download)
and what each seeded inspection contains: [`docs/demo.md`](docs/demo.md).
**For the SIH presentation itself** — the 3/5/10-minute judge walkthroughs and
the backup/failure plans: [`docs/judge-demo.md`](docs/judge-demo.md).

### Final verification matrix (UI-10 hardening pass, 2026-09-06)

| Check | Result |
| --- | --- |
| Frontend typecheck (`tsc --noEmit`) | PASS — 0 errors |
| Frontend lint (ESLint) | PASS — 0 errors (4 pre-existing warnings) |
| Frontend test suite (vitest) | PASS — 108 passed |
| Frontend production build (Vite) | PASS |
| Backend unit/API suite (pytest, in-memory SQLite) | PASS — 707 passed |
| Backend integration suite (real PaddleOCR + OpenCV) | PASS — 22 passed (Prompt 10 run) |
| OCR / vision / perception pipeline tests | PASS (integration marks above) |
| Regulatory / compliance-engine tests | PASS (in the 707) |
| Evidence / evidence-graph tests | PASS (in the 707) |
| Review (HITL) / decision-gate tests | PASS (in the 707) |
| API security (auth, roles, traversal, IDOR) tests | PASS (in the 707) |
| Audit-trail tests | PASS (in the 707) |
| PDF/DOCX export from all four demo inspections (incl. embedded evidence images, no placeholders, no fake seals) | PASS — 8/8 files |
| Live RBAC/IDOR probes (anonymous, auditor-write, dummy-UUID IDOR) | PASS — all correctly rejected |
| Secrets scan of tracked files | PASS — no real secrets tracked |

---

## Current limitations

- **UNVERIFIED regulatory data.** The seeded Legal Metrology requirements are
  research-grade with full provenance but have **not** been checked against
  official Gazette / India Code text. Findings are decision support against
  that dataset — never legal determinations.
- **Perception scope:** real OCR (PaddleOCR, English only as configured and
  actually tested) and real QR/barcode detection (OpenCV) — no logo/graphic
  segmentation, no product classification, no LLM assistance. Hindi/Kannada
  script models exist in PaddleOCR but are not enabled; no language support is
  claimed beyond what is configured and tested.
- **Unbenchmarked accuracy:** no OCR/vision accuracy percentages are claimed
  anywhere; the engines have not been benchmarked on real Indian packaging.
- **Some aggregate UI pages still on the labelled mock adapter:** the Command
  Center (Dashboard), Risk Radar, Batches and Audit pages render clearly
  labelled demonstration data for their aggregate figures (each carries a
  visible demo-data notice). The live API powers auth, inspections, intake,
  perception, compliance, review, decisions, complaints, reports (list +
  detail + PDF/DOCX export), search, history, products and analytics. The Risk
  Radar score is demo scoring — no real risk model exists.
- **Legacy mock analyze path retained:** the early `/analyze` demo endpoint
  and its clearly-labelled mock finding flow remain (covered by tests); the
  production UI exclusively uses the real perception → deterministic-engine
  path. Analytics counts union both sources — they are mutually exclusive per
  inspection, so nothing is double-counted.
- **Demo credentials / dev secrets:** auth uses demo credentials seeded on
  startup; the secret key defaults to an insecure dev value and must be
  overridden outside development (the app refuses to run silently with it in
  production mode).
- **First-boot OCR cost:** on a fresh database the demo seeding runs the real
  local OCR engine (~1–2 minutes on CPU); subsequent boots skip it.
- **Test-suite sensitivity:** the frontend vitest suite occasionally hits its
  5s per-test timeout on a busy machine (dev servers + OCR running); a clean
  re-run passes 108/108. Backend suite: 707/707.

---

## Future roadmap

1. **Verified regulatory data** — flip the seeded source to VERIFIED after
   human checking against the official Gazette / India Code text, and broaden
   document coverage.
2. **Wire the remaining aggregate pages** (Command Center, Risk Radar,
   Batches, Audit) to the live API. For the Risk Radar: consume the
   already-exposed structured signals (finding status/severity, per-field OCR
   confidence, image usability grade, unresolved-review counts) with the
   transparent weighted factors unchanged and documented — not a new
   black-box score. *(Reporting, search, history, products and analytics are
   already live.)*
3. **Product understanding** — real category/declaration-profile classification.
4. **Expanded deterministic rule coverage** across commodity categories.
5. **More OCR languages** — enable + actually validate Hindi/Marathi
   (Devanagari) and other Indian-script models before claiming them.

> Done since the Prompt 10 roadmap was written: inspection status lifecycle
> (finalized reports now complete their inspections), reporting/export of
> completed inspections (report lifecycle, finalization gate, versioned
> snapshots, PDF/DOCX exports with embedded evidence images), and the
> search / history / products / analytics surfaces (UI-09).
>
> LLM assistance is not implemented — the architecture provides the interfaces
> and seams where it attaches without touching call sites. The regulatory
> intelligence layer is a knowledge foundation, not a legal determination.

---

## License

UNLICENSED — internal / hackathon use.
