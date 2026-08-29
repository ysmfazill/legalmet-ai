# LEGALMET AI

**Evidence-grounded, version-aware, AI-assisted compliance inspection for packaged commodities.**

> ⚠️ **DEMO REGULATORY DATA — NOT LEGAL ADVICE.** This build contains
> clearly-labelled placeholder regulatory data. Perception is **real** (local
> PaddleOCR + OpenCV read the actual uploaded images — Prompt 4), but the
> system has **no verified Legal Metrology requirements and no compliance
> evaluation for real inspections yet**; the demo analysis flow remains
> clearly labelled as demo. It must not be used for real compliance decisions.

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

> On startup the backend also creates tables (dev convenience) and seeds
> clearly-labelled **demo** users/rules when `SEED_DEMO_DATA=true`.

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
deselected by default; the fast suite runs entirely on deterministic fakes.

**Frontend / shared packages (from the repo root):**

```bash
npm run typecheck           # tsc --noEmit across all workspaces
npm run lint                # ESLint
npm run build:web           # production build of @legalmet/web
```

---

## Current limitations

- **DEMO regulatory data only.** Regulatory rules are placeholders, not verified
  Legal Metrology (Packaged Commodities) Rules, 2011 content — regulatory
  intelligence and compliance evaluation are deliberately **not implemented
  yet** (perception outputs are marked `AWAITING_REGULATORY_EVALUATION`).
- **Perception scope:** real OCR (PaddleOCR) and real QR/barcode detection
  (OpenCV) only — no logo/graphic segmentation, no product classification, no
  LLM assistance. Only English OCR models are configured by default.
- **Unbenchmarked accuracy:** no OCR/vision accuracy percentages are claimed
  anywhere; the engines have not been benchmarked on real Indian packaging.
- The **rule engine** runs real deterministic logic but over placeholder rules
  (demo flow only, clearly labelled).
- Auth uses demo credentials seeded on startup; secrets default to insecure dev
  values and must be overridden outside development.

---

## Future roadmap

1. ~~**Verified regulatory data**~~ — the regulatory-intelligence foundation
   (source/document/version/requirement hierarchy, version windows, candidate
   mapping) landed in Prompt 5. What remains: flipping the seeded source to
   VERIFIED after human checking against the official Gazette / India Code
   text, and broader document coverage.
2. ~~**Real OCR**~~ — done in Prompt 4 (PaddleOCR behind `OCRService`).
3. ~~**Computer vision**~~ — QR/barcode region detection done in Prompt 4
   (OpenCV behind `VisionService`); richer label-element detection remains
   future work.
4. **Product understanding** — real category/declaration-profile classification.
5. **Expanded deterministic rule coverage** across commodity categories.
6. **Human-in-the-loop review** — the corrected-value data model is in place
   (`extracted_fields.corrected_value`); correction UX, escalation and
   reporting/export remain future work.

> Compliance evaluation (the deterministic engine over *verified* regulatory
> data) and LLM assistance are not implemented — the architecture provides the
> interfaces and seams where each attaches without touching call sites. The
> regulatory intelligence layer (Prompt 5) is a knowledge foundation, not a
> legal determination.

---

## License

UNLICENSED — internal / hackathon use.
