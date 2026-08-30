# Demo guide

How to run METRASIGHT locally and demonstrate the full inspection lifecycle —
**entirely offline** after a one-time model download.

> ⚠️ **DEMO REGULATORY DATA — NOT LEGAL ADVICE.** The regulatory requirements
> in this build are research-grade and UNVERIFIED. Every demo inspection below
> is seeded through the real pipeline, but its findings are system-generated
> decision-support output against that unverified dataset — never a legal
> determination.

---

## 1. Prerequisites (one time)

```bash
# repo root
npm install                                   # frontend + shared packages

cd services/api
python -m venv .venv
source .venv/Scripts/activate                 # Windows bash; .venv/bin/activate elsewhere
pip install -r requirements.txt -r requirements-dev.txt
pip install "paddlepaddle==3.0.0" "paddleocr==3.1.0" "paddlex==3.1.0"
```

The **first** perception run (or first boot with demo seeding) downloads the
PP-OCRv5 detection + recognition models (~tens of MB each) into
`~/.paddlex/official_models`. After that one download, **no network access is
needed for anything**: OCR runs locally on CPU, the database is local SQLite,
the regulatory dataset is seeded locally, and the frontend talks only to
localhost. There is no external AI API key anywhere in the demo path.

## 2. Start the backend

```bash
cd services/api
source .venv/Scripts/activate
alembic upgrade head        # optional — startup also creates tables
uvicorn app.main:app --reload   # http://localhost:8000
```

On boot with a fresh database the backend seeds, in order: demo users,
research-grade regulatory data, deterministic compliance rules, and **three
full-lifecycle demo inspections** (below). The first boot pays the real-OCR
cost for those three inspections (~1–2 minutes on CPU — the log line
`demo_inspections_seeded` reports each one's real outcome). Later boots skip
them (idempotent). To boot without demo inspections:
`SEED_DEMO_INSPECTIONS=false`.

## 3. Start the frontend

```bash
# repo root
npm run dev:web             # http://localhost:5173 (proxies /api → :8000)
```

Log in as `inspector@legalmet.local` / `changeme-inspector`
(or `admin@legalmet.local` / `changeme-admin`; `auditor@legalmet.local` is
read-only — good for demonstrating role enforcement).

## 4. The seeded demo inspections (DEMO-FOOD / DEMO-WATER / DEMO-OIL)

Each was produced **through the real services at seed time** — nothing about
them is hand-written into the database:

| Stage | What happened | Where to show it |
| --- | --- | --- |
| Intake | the committed synthetic label PNG (`app/db/demo_images/`) uploaded through the real intake service, graded `ACCEPTABLE` by the real quality analyzer | Inspection Workspace → image viewer |
| Perception | a real local PaddleOCR run over the label (run status `REVIEW_REQUIRED` where fields fell below the review-confidence threshold — that is the honest outcome, not an error) | Perception panel → per-field evidence drawers (raw OCR text, bounding boxes, confidence) |
| Evaluation | the deterministic engine evaluated the perceived fields against the seeded requirements — 9 findings per inspection | Findings list with expected-vs-detected values and the seven-question explanation |
| Review | an inspector (the seeded demo user) CONFIRMED every finding through the real HITL service | Finding review history; evidence graph nodes tagged HUMAN vs AI |
| Decision | a final human decision (`NON_COMPLIANT` for all three — each label is missing declarations by design) | Decision panel + audit trail |
| Audit | ~27 audit events per inspection, written by the services themselves | Audit timeline; evidence graph |

The evidence-graph view is the demo's centerpiece: every finding traces back
through the requirement → version → document → source chain, and every node is
tagged with its origin (AI / HUMAN / SYSTEM).

## 5. Live demo flow (do this on stage)

1. **Login** as inspector; the Dashboard shows the three demo inspections.
2. Open **DEMO-FOOD** → walk the evidence chain for one NON_COMPLIANT finding:
   finding → extracted field (raw OCR text + confidence) → requirement in
   force (version + source).
3. **Upload a new label** (any packaged-commodity photo): create an inspection,
   upload the image — the real quality gate grades it (blur/glare/low-light
   rejections are honest and worth showing).
4. **Run perception** — real OCR, roughly 15–25 s per image on CPU; the panel
   polls while active. Show the field-level confidence and "review required"
   flags.
5. **Evaluate** — deterministic findings appear; open one and read the
   explanation.
6. **Correct a field** as the inspector would (the AI original is preserved and
   the correction is tagged HUMAN), then re-evaluate.
7. **Record a decision** — the gate blocks COMPLIANT while unresolved critical
   findings exist; demonstrate that with REQUIRES_FURTHER_REVIEW.
8. Log in as **auditor** in a second tab — every write button is gone (403 at
   the API level, not just hidden in the UI).

## 6. Demo failure plan (if something breaks on stage)

- **OCR engine fails to load / models missing** → perception runs fail with
  `AI_SERVICE_UNAVAILABLE` and the UI shows an honest error state. Fall back to
  the three seeded demo inspections — they already contain complete perception
  evidence, findings, reviews and decisions, and need no engine at runtime.
- **Fresh-database boot is slow** (first boot runs real OCR on three labels) →
  pre-boot once before the demo; subsequent boots are ~2 s and skip seeding.
  Worst case, boot with `SEED_DEMO_INSPECTIONS=false` and show the seeded
  demos from the pre-warmed database.
- **Upload rejected by the quality gate** → that is the system working
  correctly; narrate it (blur/glare/too-small detection), then upload a clean
  photo.
- **Wrong login** → demo credentials are in `README.md` § Backend startup.

## 7. What NOT to claim in the demo

- Do not present findings as legal determinations — the inspector decides.
- Do not quote accuracy percentages — no verified benchmark exists for this
  build; confidence numbers are OCR recognition scores, not legal confidence.
- Language support is English only (as configured and actually tested); Hindi
  and Kannada models exist in PaddleOCR but are **not** enabled or claimed.
