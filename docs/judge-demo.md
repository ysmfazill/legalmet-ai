# Judge demo — operator guide (Prompt 10, Phase 13)

This is the team's run book for demonstrating METRASIGHT at SIH. It assumes
the pre-demo checklist (§H) has been done the night before. Everything here
runs **offline on localhost** — no network, no cloud, no API keys.

> ⚠️ **DEMO REGULATORY DATA — NOT LEGAL ADVICE.** The regulatory dataset is
> research-grade and UNVERIFIED against the official Gazette text. Findings
> are decision support. Never present them as legal determinations.

---

## A. The 3-minute demo (elevator pitch + one walkthrough)

1. Login as `inspector@legalmet.local` / `changeme-inspector` (~10 s).
2. Open **Review** and switch the source toggle to **Engine findings** — this is
   the live queue of real system findings from the seeded inspections (14
   rows after a `--fresh` seed). Click the **Rule 6(2) consumer-care** row —
   the workspace opens with `DEMO-FOOD` in the eyebrow (15 s).
3. Open one **NON_COMPLIANT finding** (Rule 6(2) consumer care) and read the
   explanation: it names the requirement, the **version in force**, the
   detected vs expected value, and says *"system-generated decision-support
   output, not a legal enforcement determination"* (45 s).
4. Open the **Evidence drawer** for that finding and walk the chain once:
   finding → extracted field → raw OCR text + confidence → region on the
   image (45 s).
5. Open the **Evidence graph** view — every node tagged AI / HUMAN / SYSTEM,
   tracing to the requirement version and source (30 s).
6. Close with the one-liner: *“AI reads the label; a deterministic engine
   checks it against the rule version in force; a human inspector decides.
   Every conclusion is traceable to pixels.”* (10 s)

## B. The 5-minute demo (add the live pipeline)

Everything in A, plus:

1. **New Inspection** → create (`SUNRISE Masala`, category food). The pipeline
   map at the top shows the whole flow (create → image → validation → quality
   → run perception → OCR + vision → extraction → evaluation → findings →
   review) with the current step highlighted.
2. Upload `services/api/tests/dataset/images/food-clean-001.png`.
3. **Run perception** — narrate: real local PaddleOCR (PP-OCRv5 mobile
   models, engine pre-warmed at startup); measured **1–3 s per image** on CPU
   (baseline before optimisation was ~27–37 s). The panel shows the live
   stage checklist (✓ validation ✓ quality → OCR → vision → extraction) with
   an elapsed timer — no fake percentages — and refreshes automatically.
4. Show the perception panel: per-field **confidence**, `DETECTED` vs
   `REVIEW_REQUIRED` statuses (the honest states).
5. **Evaluate** → deterministic findings appear instantly.
6. Try recording a **COMPLIANT decision** → the gate **blocks it (409)** while
   the MAJOR finding is unresolved. Then CONFIRM the finding as the inspector
   and record the real decision. This is the human-in-the-loop centerpiece.
7. **Inspections page** → the source toggle defaults to **Live inspections**:
   the inspection you just created is right there, tagged LIVE INSPECTION.
8. **Evidence Explorer** → switch to **Live inspections**: real thumbnails of
   the images you uploaded, each declaration's region highlighted on the real
   pixels, the verbatim OCR line, and the engine finding status. Click a card
   → it deep-links into the workspace with the field's evidence drawer open
   and the region highlighted.

## C. The 10-minute technical demo (for a technical judge)

Add to B:

1. **Regulations page**: Source → Document → Version → Requirement hierarchy.
   Show the three versions of the LM (PC) Rules 2011 with effective dates, the
   ACTIVE consolidated version, and the **UNVERIFIED** status with its
   verification note — explain why unverified data is labelled, not hidden.
2. **`/inspections/{id}/compliance` endpoints** (Swagger at
   `http://localhost:8000/docs`): show the frozen provenance snapshot in an
   evaluation and immutable evaluation history.
3. **Review queue**: filter by status; show a field **correction** — the AI
   original is preserved and the correction is tagged HUMAN, then re-evaluate.
4. **Audit timeline** for the live inspection: ~20 events with actor identity.
5. **Failure honesty** (if time): upload a garbage file → clean 400
   `INVALID_IMAGE`; the system never fabricates output. Show the
   `NOT_DETECTED` findings in DEMO-OIL — absence of evidence is recorded as
   absence, never as a violation.
6. **Architecture** (one slide / the README diagram): the separation of
   AI perception ≠ regulatory interpretation ≠ inspector decision.

## D. Backup demo procedure (if the live pipeline is too slow or fails)

Use the seeded inspections — they contain the complete lifecycle (image,
perception, findings, reviews, decisions, audit) and need **no engine at
runtime**:

1. Login as inspector. Reach the seeded inspections through **Review → Engine
   findings**: click rows there to open each workspace (the eyebrow shows
   `DEMO-FOOD` / `DEMO-WATER` / `DEMO-OIL` / `DEMO-QUINOA`), or through the
   **Inspections** page with the source toggle switched to
   **Demonstration data**. Note: the Dashboard aggregates still show the
   labelled demo dataset (INS-…) — they are marked as demonstration data, not
   live counts.
2. DEMO-QUINOA is the fully COMPLIANT imported package (shows the
   country-of-origin applicability resolving deterministically).
3. DEMO-OIL shows honest NOT_DETECTED findings for absent declarations.
4. Everything in demo A (evidence chains, versions, graph) works on seeded
   data without running perception live.

## E. If OCR fails on stage

- Perception runs will show `AI_SERVICE_UNAVAILABLE` / failed run status with
  an honest error state — narrate this as designed behaviour (no fake output).
- Switch to plan D (seeded inspections) — nothing else changes.

## F. If the backend fails on stage

- Restart: `bash scripts/demo.sh` (or `cd services/api && uvicorn
  app.main:app --port 8000` + `npm run dev:web` in a second terminal).
- Backend boots in ~2 s with the pre-warmed DB (seeding is skipped — it is
  idempotent).
- If the DB itself is corrupted: `bash scripts/demo.sh --fresh` re-seeds
  (~2 minutes, real OCR) — do this before the demo, not during.

## G. Which package image to use (live upload)

`services/api/tests/dataset/images/food-clean-001.png` — a clean synthetic
label with all declarations; OCR reads it reliably in **1–3 s** (mobile
models, pre-warmed engine). For a quality-gate moment, also show
`food-blur-011.png` (graded POOR — honest degradation).

## H. Which finding to open

**DEMO-FOOD → the NON_COMPLIANT consumer-care finding (Rule 6(2))** — the
label has an e-mail but no telephone, so the CONTACT_FORMAT rule fails
deterministically. It has a complete evidence chain and a clear expected-vs-
detected story.

## I. Which evidence chain to show

From the H finding: open the evidence drawer → extracted field (raw OCR text
`Consumer Care: care@sunrise.example`, confidence ~0.94) → region overlay on
the image → then the finding's evidence **graph**: Finding → Field → OCR →
Region → Image and Finding → Requirement → Version → Document → Source, every
node tagged with origin (AI / HUMAN / SYSTEM).

## J. Which regulatory version screen to show

Regulations → the **LM-PC-RULES-2011 document** → version timeline: the 2011
original (SUPERSEDED) → G.S.R. 385(E)/2015 amendment → the consolidated
**ACTIVE** version effective 2017-06-23 (G.S.R. 629(E)). Point out the
effective-date windows and that the evaluator records which version was in
force inside every finding's provenance snapshot.

## K. Which report to open

The **Reports page** (also linked from the live workspace's `Report` button) —
select an inspection report card and the preview renders with the
`DEMO DATA — NOT LEGAL ADVICE` banner and the system-role notice
("METRASIGHT provides AI-assisted inspection intelligence... Final regulatory
determination remains with the authorized inspector."), findings table with
expected-vs-detected values, and the audit timeline. Be honest that the report
list itself is the labelled demo dataset in this build.

## L. Which innovation to explain (the pitch, in order)

1. **Version-aware regulatory engine** — rules carry versions/effective
   dates; every finding records the version in force. Not "is it compliant"
   but "against which law, as of when".
2. **Evidence graph** — every finding traces to pixels (image → region → OCR
   → field) and to law (requirement → version → source). Defensible by
   construction.
3. **Confidence-aware perception** — below the confidence floor the system
   says REVIEW_REQUIRED; it never guesses. NOT_DETECTED ≠ violation.
4. **Multimodal perception** — real OCR + real QR/barcode vision + structured
   extraction, locally, offline.
5. **Human-in-the-loop** — the decision gate structurally prevents the system
   from concluding compliance; only an authorised inspector decides.
6. **Auditable workflow** — append-only audit trail with actor identity;
   immutable evaluation history; AI vs HUMAN provenance on every node.
7. **Batch intelligence** — real batch intake exists (New inspection → Batch
   mode validates and uploads up to 20 files through the live backend), but
   the Batches/Risk/Dashboard aggregate analytics pages are mock-backed in
   this build — say so plainly if asked.

---

## Pre-demo checklist (run the night before)

- [ ] `bash scripts/demo.sh --fresh` — fresh DB, watch 4 inspections seed
- [ ] Login works (inspector + auditor accounts)
- [ ] All 4 DEMO-* inspections reachable: Review → Engine findings →
      click rows (workspace eyebrow shows `DEMO-*`)
- [ ] One live upload + perception run completes (~1–3 s after startup
      pre-warm; the first boot pays ~1 min of engine warm-up)
- [ ] Inspections page: Live source toggle shows newly created inspections
- [ ] Evidence Explorer: Live source shows real thumbnails with regions
- [ ] Swagger reachable at `http://localhost:8000/docs`
- [ ] `services/api` fast suite green: `python -m pytest` (424 passed)
- [ ] Laptop plugged in, CPU power mode set to high (OCR is CPU-bound)
- [ ] Browser zoom ~90%, tabs pre-opened: app, Swagger, this document
