# METRASIGHT — Architecture

> **Status:** SIH-ready prototype (after Prompt 10). Perception is **real**
> (local PaddleOCR + OpenCV), regulatory intelligence and the deterministic
> compliance engine are real, and human review / decisions / audit are real.
> The regulatory dataset is research-grade and marked **UNVERIFIED** —
> **DEMO DATA — NOT LEGAL ADVICE**; aggregate pages (Dashboard, Risk Radar,
> Reports, Audit, Batches) still read clearly-labelled demo data.

---

## 1. Monorepo structure

The repository is an npm-workspaces monorepo (JS/TS) with a Python backend that
lives alongside it under `services/`.

```
legalmet-ai/
├─ package.json              # workspaces: packages/*, apps/*  (root scripts)
├─ tsconfig.base.json        # shared TS compiler options + path aliases
├─ docker-compose.yml        # local PostgreSQL (+ Adminer)
├─ .env.example              # root env for docker-compose
│
├─ packages/                 # shared, framework-agnostic TypeScript libraries
│  ├─ types/                 # @legalmet/types  — enums, models, API contracts
│  └─ config/                # @legalmet/config — labels, tones, app constants
│
├─ apps/
│  └─ web/                   # @legalmet/web — Vite + React + TS frontend (shell)
│
└─ services/
   └─ api/                   # FastAPI backend (Python 3.11+)
      ├─ app/
      │  ├─ core/            # config, logging, errors, security, enums
      │  ├─ db/              # engine/session, init, seed
      │  ├─ models/          # SQLAlchemy ORM models
      │  ├─ schemas/         # Pydantic request/response schemas
      │  ├─ services/        # business logic + pluggable AI/perception seam
      │  └─ api/             # routers + dependency wiring
      ├─ alembic/            # migrations (source of truth for schema)
      └─ tests/              # pytest suite
```

**Root scripts** (`package.json`):

| Script | Effect |
| --- | --- |
| `npm run demo` | One-command localhost demo: backend + frontend together (`bash scripts/demo.sh`; `--fresh` also wipes the local demo DB) |
| `npm run dev:web` | Start the Vite dev server for `@legalmet/web` |
| `npm run build:web` | Production build of the frontend |
| `npm run typecheck` | `tsc --noEmit` across every workspace |
| `npm run lint` | ESLint across every workspace that defines a `lint` script |

---

## 2. Shared contract & single source of truth

> This is the section referenced from `packages/types/src/enums.ts`,
> `services/api/app/core/enums.py`, and `services/api/app/db/init_db.py`.

The domain vocabulary is defined **once per language** and kept byte-for-byte
identical across the stack:

- **TypeScript:** `packages/types/src/enums.ts` — each enum is a `const` string
  array plus a derived union type, so values exist at runtime (dropdowns,
  iteration, validation) while staying strictly typed.
- **Python:** `services/api/app/core/enums.py` — mirrors the **exact same string
  values**.

**Rule:** when an enum value changes on one side, it MUST change on the other.
The string values are the wire contract; both sides serialise/deserialise them
verbatim. There is no code generation step — the mirror is maintained
deliberately and verified by review + tests.

Presentation metadata (human labels, semantic `tone`) lives separately in
`@legalmet/config` (`packages/config/src/domain.ts`) so pure types stay free of
UI concerns. The `tone` values map to the `--tone-*` design tokens in
`apps/web/src/styles/tokens.css`.

**Schema source of truth:** the database schema is owned by Alembic migrations
(`services/api/alembic/`), not by ad-hoc table creation. `create_all` exists
only as a dev/demo convenience.

---

## 3. Shared TypeScript contracts (`packages/*`)

### `@legalmet/types`
Pure types, no runtime dependencies beyond its own const enums.

- `enums.ts` — canonical enumerations (roles, inspection lifecycle, compliance
  outcomes, field types, review actions, image/region types, regulation/rule
  statuses, evidence & model-service types, audit events, batch statuses).
- `models.ts` — domain entity shapes (Inspection, Package, Product, User,
  ComplianceFinding, Evidence, EvidenceGraph, Regulation, Rule, AuditEvent, …).
- `api.ts` — request/response contracts and envelopes (`ApiError`,
  `Paginated<T>`, auth/inspection/review requests, `HealthResponse`, response
  aliases). Mirrors the live FastAPI OpenAPI contract at `/openapi.json`.

### `@legalmet/config`
Runtime constants and presentation metadata that both depend on `@legalmet/types`.

- `app.ts` — `APP_NAME`, `APP_TAGLINE`, `PROBLEM_STATEMENT` (SIH26034),
  `DEMO_DATA_LABEL`/`DEMO_DATA_NOTICE`, `DEFAULT_PAGE_SIZE`,
  `CONFIDENCE_THRESHOLDS`.
- `domain.ts` — `*_META` maps resolving each enum value to a `{ label, tone,
  description }` for the UI.

Both packages export raw `src/index.ts`. Consumers resolve them through the path
aliases in `tsconfig.base.json`; the frontend additionally aliases them in
`vite.config.ts` so Vite transpiles them as project source.

---

## 4. FastAPI backend (`services/api`)

An application-factory FastAPI service (`app/main.py::create_app`) with no
import-time side effects.

**Cross-cutting wiring:**
- **CORS** — origins from `settings.cors_origins`.
- **Request context** — every request gets an `X-Request-ID` (generated if
  absent), bound into the structured logging context and echoed back on the
  response.
- **Uniform error envelope** — all errors (domain `AppError`, validation
  errors, and unexpected exceptions) are rendered as
  `{"error": {"code", "message", "details?", "requestId?"}}`. Internals are
  never leaked; 5xx causes are logged server-side only.
- **Lifespan** — creates tables (dev convenience) and, when
  `SEED_DEMO_DATA=true`, seeds clearly-labelled demo users/rules.

**Core (`app/core`):** `config.py` (pydantic-settings; SQLite default for
zero-config dev/test, PostgreSQL via env in production), `logging.py`
(structlog), `errors.py` (`AppError` + `ErrorCode`), `security.py`
(JWT + password hashing), `enums.py` (Python mirror of the shared enums).

---

## 5. Database layer (`app/db`, `app/models`, `alembic`)

- **Engine/session** — `app/db/session.py` builds the SQLAlchemy engine and
  `SessionLocal`; `app/db/base.py` is the declarative base / metadata.
- **Models** — `app/models/*` define the ORM entities (users, products,
  batches, inspections, images, extractions, findings, reviews, regulatory
  entities, model versions, audit events).
- **Migrations** — `alembic/` holds the versioned schema; the initial migration
  creates the full schema. Alembic is the schema source of truth; `init_db.py`'s
  `create_all` is a dev/demo shortcut only.
- **Seeding** — `app/db/seed.py` inserts DEMO users and placeholder rules on
  startup (guarded by `SEED_DEMO_DATA`).

Default dev/test database is **SQLite** (no external service). Production points
`DATABASE_URL` at PostgreSQL (`postgresql+psycopg2://…`), provisioned locally by
`docker-compose.yml`.

---

## 6. Service layer (`app/services`) — the pluggability seam

Business logic lives in services; **every AI/perception capability is an
abstract interface** with a swappable implementation.

- **`interfaces.py`** — abstract base classes (`OCRService`, `VisionService`,
  `ProductUnderstandingService`, `ImageQualityAnalyzer`, `RuleEngine`) plus
  plain-dataclass value objects (`BBox`, `ServiceDescriptor`, `OcrResult`,
  `FieldCandidate`, `ProductProfile`, `FieldObservation`, `RuleSpec`,
  `FindingResult`).
- **`registry.py`** — the composition root. `build_services()` assembles every
  concrete implementation into a `Services` container consumed via FastAPI
  dependencies. **Swapping a mock for a real model is a change here only** —
  call sites depend on interfaces, never implementations. Selection is
  config-driven.
- **`provenance.py`** — records which service (name/version/provider) produced
  each observation, for auditability.

**Critical separation of concerns:**
> Perception services only *describe* what they observe, **with confidence**.
> They never assert legal conclusions. The **`RuleEngine` is the only component
> that decides compliance**, and it does so **deterministically** from verified
> rule data + observations. No LLM sits in the compliance-decision path — this
> is intentional and is *not* configurable to an LLM backend.

### 6a. Real OCR / computer vision (Prompt 4)
Perception is real: `services/ocr/paddle.py` (local PaddleOCR, English as
configured and tested), `services/vision/opencv.py` (QR/barcode detection),
`services/quality/analyzer.py` (real usability grading) and
`services/perception/extract.py` (deterministic field extraction). Deterministic
**mocks** remain only behind test seams. When the real engines are missing,
runs fail loudly with `AI_SERVICE_UNAVAILABLE` — there is no stub fallback.

### 6b. Regulatory service (Prompt 5)
`services/regulatory/service.py` resolves the requirement set in force via the
Source → Document → Version → Requirement → Applicability hierarchy with an
explicit `NO_APPLICABLE_VERSION` state (never a silent fallback to newest).
The dataset is researched Legal Metrology (Packaged Commodities) Rules, 2011
content marked **UNVERIFIED** with a full provenance chain and verification
notes — not fiction, and not yet verified against the Gazette.

### 6c. Compliance engine (Prompt 6)
`services/compliance/engine.py` + `evaluators.py` + `resolvers.py` +
`applicability.py`: (detected field + applicable requirement + deterministic
rule) → evaluation → finding, with decimal-safe numerics, a per-finding
seven-question explanation, a frozen regulatory provenance snapshot and
evidence references. Missing OCR is `NOT_DETECTED`, never a violation;
insufficient evidence is `REVIEW_REQUIRED`, never a guess. Evaluations are
immutable history.

### 6d. Evidence + evidence graph (Prompts 5–7)
`services/evidence/service.py` and `services/evidence_graph/builder.py` build
the traceable chain: Finding → Rule → Requirement → Version → Document → Source
AND Finding → Field → OCR → Region → Image. Every node is tagged with its
origin (AI / HUMAN / SYSTEM). Every conclusion is traceable to its grounding —
this is what makes findings defensible and reviewable.

### 6e. Audit service
`services/audit/service.py` records an append-only trail of real domain events
(inspection created, image uploaded, perception run, evaluation, finding
review, decision supersession) with actor identity — accountability by
construction, ~20+ events per full-lifecycle inspection.

### 6f. Orchestration, HITL & analytics
`services/inspection/service.py` and `services/perception/service.py` orchestrate
intake → quality gate → OCR → vision → extraction. `services/hitl/service.py`
owns the human-in-the-loop workflow: finding review
(CONFIRM/REJECT/CORRECT/ESCALATE), field corrections (AI original preserved,
correction tagged HUMAN) and the final decision gate — a COMPLIANT decision is
blocked while unresolved CRITICAL/MAJOR findings exist, and only an authorised
human ever records a legal conclusion. `services/analytics/service.py`
aggregates summaries (the aggregate UI pages remain on the labelled mock
adapter — see README limitations).

---

## 7. API layer (`app/api`)

- **`api/__init__.py`** aggregates domain routers into `api_router`, mounted
  under `settings.api_prefix` (default `/api/v1`).
- **`api/deps.py`** provides FastAPI dependencies (settings, DB session,
  current user, wired services).
- **`api/routers/*`** — one module per domain:

| Router | Responsibility |
| --- | --- |
| `health` | Unauthenticated liveness (`GET /health`) |
| `auth` | Login / token issuance |
| `inspections` | Create, list, fetch, analyze inspections |
| `findings` | Compliance findings for an inspection |
| `review` | Record human review actions |
| `regulations` | Browse regulations / versions / rules |
| `audit` | Read the audit trail |
| `analytics` | Dashboard summaries |
| `batch` | Batch grouping of inspections |
| `storage` | Image/object storage endpoints |

Interactive contract: **Swagger UI at `/docs`**, raw schema at `/openapi.json`.

---

## 8. Frontend (`apps/web` — foundation shell)

Vite + React 18 + TypeScript. **This is a minimal application shell, not the
final product UI.**

- Consumes `@legalmet/types` (enums/contracts) and `@legalmet/config`
  (labels/tones/constants) directly — the shell renders the shared compliance
  vocabulary to prove the contract works end-to-end.
- `src/api/client.ts` — minimal typed `fetch` wrapper returning shared types and
  raising `ApiClientError` (carrying the backend error envelope) on failure. It
  calls `GET /health` on load to verify backend connectivity.
- Dev server proxies `/api` → `http://localhost:8000`, so the browser only ever
  talks to the frontend origin during development.
- Design tokens in `src/styles/tokens.css` implement the `tone` palette from
  `@legalmet/config`.

---

## 9. Data & request flow (as built)

```
Client (apps/web)
  │  fetch /api/v1/...            (shared @legalmet/types contracts)
  ▼
FastAPI router (app/api/routers)      role-gated on every mutating route
  │  → deps: settings, db session, current user, Services
  ▼
Service layer (app/services)
  intake + quality gate → real OCR → vision → field extraction
  → version-aware requirement resolution → deterministic rules
  ▼
Persistence (app/models + SQLAlchemy)  +  Evidence graph  +  Audit trail
  ▼
Structured response envelope  → Client
```

## 10. The METRASIGHT pipeline

```
                        METRASIGHT

                            │
              ┌─────────────┴─────────────┐
              │                           │
        Package Input              Regulatory Data
              │                           │
        Image Quality               Version Control
              │                           │
        OCR + Vision               Rule Selection
              │                           │
              └─────────────┬─────────────┘
                            │
                    Field Extraction
                            │
                   Deterministic Rules
                            │
                      Evidence Graph
                            │
                     Human Review
                            │
                   Audit + Reporting
                            │
                       Analytics
```

## 11. Separation of powers (the core architectural strength)

Three responsibilities are deliberately kept in three different layers, with
the boundaries enforced in code:

1. **AI perception** (OCR, vision, extraction) — *describes* what is on the
   package, with confidence. It never asserts a legal conclusion; below the
   confidence floor its output becomes `REVIEW_REQUIRED`, never a guess.
2. **Regulatory interpretation** (version resolution + deterministic rules) —
   *evaluates* perceived fields against the requirement version in force.
   Deterministic and decimal-safe; no LLM anywhere in the decision path. It
   produces decision-support findings, not verdicts.
3. **Final inspector decision** (HITL) — the *only* place a legal conclusion is
   recorded, by an authorised human, with the decision gate enforcing that
   unresolved CRITICAL/MAJOR findings are addressed first.

```
   AI perception  ≠  regulatory interpretation  ≠  final inspector decision
```

This separation means a wrong OCR reading can never silently become a
"violation", an unverified rule can never masquerade as law (the dataset is
marked UNVERIFIED with provenance), and the inspector's authority is
structurally — not just rhetorically — preserved.

Every non-2xx response is the uniform `{"error": {...}}` envelope; every request
is correlated by `X-Request-ID`.
