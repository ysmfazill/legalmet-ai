# LEGALMET AI

**Evidence-grounded, version-aware, AI-assisted compliance inspection for packaged commodities.**

> ⚠️ **DEMO DATA — NOT LEGAL ADVICE.** This build uses clearly-labelled
> placeholder regulatory data and **mock** perception services (OCR / computer
> vision / product understanding). It does **not** contain verified Legal
> Metrology requirements and must not be used for real compliance decisions.

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
- **Perception is mocked:** OCR/vision/product/quality services are deterministic
  stubs behind abstract interfaces, swappable at the service registry.
- **Frontend:** a minimal professional shell that consumes the shared packages
  and verifies backend connectivity.

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
python -m pytest            # 32 tests
python -m ruff check .      # lint
```

**Frontend / shared packages (from the repo root):**

```bash
npm run typecheck           # tsc --noEmit across all workspaces
npm run lint                # ESLint
npm run build:web           # production build of @legalmet/web
```

---

## Current limitations

- **DEMO DATA only.** Regulatory rules are placeholders, not verified Legal
  Metrology (Packaged Commodities) Rules, 2011 content.
- **No real OCR / computer vision.** Perception services are deterministic mocks
  that emit synthetic, seeded output; no image is actually read.
- **No real product classification** and **no LLM assistance** in this build.
- The **rule engine** runs real deterministic logic but over placeholder rules.
- The **frontend is a foundation shell**, not the final product UI — no
  inspection workflow screens yet.
- Auth uses demo credentials seeded on startup; secrets default to insecure dev
  values and must be overridden outside development.

---

## Future roadmap

1. **Verified regulatory data** — ingest official Legal Metrology requirements
   with version history, replacing placeholder rules (regulatory service).
2. **Real OCR** — attach a production OCR engine behind `OCRService`.
3. **Computer vision** — real label region/element detection behind
   `VisionService`.
4. **Product understanding** — real category/declaration-profile classification.
5. **Expanded deterministic rule coverage** across commodity categories.
6. **Full inspection UI** — capture/upload, analysis review, evidence graph
   visualisation, dashboards, batch workflows.
7. **Human-in-the-loop review** at scale, escalation, and reporting/export.

> None of the above (OCR, CV, real rules, advanced AI) is implemented in this
> foundation phase — the architecture provides the interfaces and seams where
> each attaches without touching call sites.

---

## License

UNLICENSED — internal / hackathon use.
