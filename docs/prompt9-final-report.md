# Prompt 9 — Final Report (Production Hardening + Real-World Validation)

All numbers below are **measured on this machine** (Windows 11 laptop, CPU-only
PaddleOCR, local SQLite) or **verified by the test suite / live walkthrough**.
Nothing is estimated. No commit / push was made (per instructions).

---

## 1. Completion

28/28 Prompt 9 phases addressed: baseline audit, golden-path test, real test
dataset, OCR robustness + language validation, quality gate, resource limits,
reliability/duplicates, DB integrity, API security, frontend error handling,
inspector UX, traceability, regulatory integrity, confidence semantics,
benchmarks, offline demo, demo data, risk-radar position, docs, suite
strengthening, no-fake-AI review, secret scan, full regression, manual
walkthrough, failure plan, final audit, this report. Remaining gaps are honest
limitations (§19) and Prompt 10 work (§20) — nothing was silently skipped.

## 2. Baseline (start of Prompt 9)

- Tests: 374 passing (fast suite), 0 failing.
- Working tree: clean on `main` at `c2cb93e`.
- Known debt found by the baseline audit and fixed during Prompt 9: ORM/
  migration schema drift, 4 missing role checks, a storage path-traversal
  prefix collision, quality/dimension guards, duplicate-run guards, stale demo
  mock UX states.

## 3. Final test state

- **Fast suite: 420 passed** (63 s, in-memory SQLite).
- **Integration suite: 22 passed** (243 s, real PaddleOCR + OpenCV).
- Total: **442/442 passing**, zero regressions from every Prompt 9 change.
- `ruff`: clean on all files touched in Prompt 9. Pre-existing debt (~23
  findings: `UP042` on two Prompt 1 enum classes, E501s in untouched files)
  was **not** touched — out of scope, recorded here instead of hidden.
- `tsc --noEmit`: clean. `eslint`: 0 errors, 2 pre-existing warnings.

## 4. Golden path

`tests/test_golden_e2e_integration.py` runs the full chain with the **real**
OCR engine: intake → quality grade → real PaddleOCR perception → verbatim OCR
text/bbox persistence → deterministic field extraction → compliance evaluation
→ findings → evidence → audit. It also re-verifies the pipeline invariants
(original image preserved, derivative stored separately, confidence semantics).
Passing (part of the 22 above).

## 5. Test dataset

`services/api/tests/dataset/` — 15 **locally rendered synthetic labels**
(Pillow; no third-party/copyrighted material) across realistic Indian
packaged-commodity conditions: clean, blur, glare, low light, perspective,
curved surface, dense text, multi-block layout, obstruction, extreme darkness,
bilingual (English+Hindi), cosmetics/water/oil variants. The manifest carries
an explicit accuracy disclaimer: expected fields describe what is printed on
the synthetic label — **no OCR accuracy percentage is claimed**.

## 6. OCR benchmark

Honest, per `tests/test_ocr_robustness_integration.py` + live measurement:

- **No accuracy percentage is claimed anywhere** — there is no verified
  benchmark on real Indian packaging, so none is invented.
- Verified behaviours: clean, structured failure on malformed/empty bytes
  (no crash, no fake output); oversized images capped by the preprocessor and
  still processed; rotated labels degrade gracefully (still yield text);
  confidences are bounded recognition scores.
- Timings (measured): first-run engine init + inference 35.2 s; warm
  inference 25.1 s per image (CPU).

## 7. Image-quality benchmark

The real usability grader (pixel-based, deterministic: blur, glare, low light,
resolution) is exercised over the degraded dataset conditions in the fast
suite and the intake gate tests: unusable images are REJECTED with an explicit
reason; usable-but-degraded images pass with an honest degraded note. The
grade is image usability — never AI confidence, never compliance.

## 8. Performance (Phase 16, all measured — `scripts/benchmark_phase16.py`)

| Measurement | Result |
| --- | --- |
| Backend startup (warm DB) | 2.1 s |
| Backend first boot, fresh DB (seeds 3 demo inspections with real OCR) | ~1.5 min |
| Frontend dev-server startup | 2.5 s |
| Cold OCR run (engine init + first inference) | 35.2 s |
| Warm OCR run | 25.1 s |
| Compliance evaluation | 0.1 s |
| Single-image end-to-end (create→evaluate) | 26.0 s |
| 3-image end-to-end | 74.7 s |

Verdict: acceptable for a fully-local CPU demo; the OCR engine is the proven
bottleneck; no architecture change made (per spec). Observation recorded
during the live walkthrough: while OCR saturates the CPU, API reads can take
>10 s — the frontend's polling tolerates this; a <10 s client timeout would
not.

## 9. Language support (actually verified only)

- **English (en): configured, integration-tested end-to-end, and the only
  language claimed by the product.**
- Hindi (Devanagari) and Kannada: verified to work **at the engine level** by
  `test_ocr_languages_integration.py`, but deliberately **not enabled** in the
  product config — so no product-level claim is made.
- Malayalam (and any language not in the verified set): explicitly rejected
  with `UNSUPPORTED_LANGUAGE` — never silently degraded.

## 10. API security

- 4 real role-gaps found and closed (an AUDITOR could previously create
  inspections, attach images, run perception and create batches). All mutating
  routes now role-gated; `tests/test_api_security.py` (36 tests) enumerates
  routes **dynamically**, so new endpoints can't ship unguarded silently.
- Storage path traversal fixed (prefix-collision case included in tests).
- Upload guards: byte size, MIME allow-list, min resolution, 8000 px decode
  ceiling.
- Anonymous writes → 401; read-only role → 403 on every write (verified live);
  malformed input → structured 400/404/422 envelopes with request IDs.

## 11. Database integrity

- Real ORM/migration drift found (`packages.status`, `field_corrections.
  created_at`, missing FK on `extracted_fields.corrected_by`) and fixed with
  an **additive** migration (`g9c5e3a1f7b2`) — no committed migration touched.
- New drift-guard integration tests: column-level diff of ORM metadata vs an
  alembic-upgraded scratch DB, full downgrade-to-base check, FK materialisation
  check, FK integrity check. All passing.

## 12. Evidence graph

Built from real rows only. On DEMO-FOOD: **95 nodes / 138 edges** —
inspection → evaluation → image → run → OCR lines / regions / fields →
findings → requirements → versions → document → source, plus review and
decision nodes, each tagged **AI / HUMAN / SYSTEM** origin. Human corrections
never overwrite AI output (original preserved, both rendered, verified live
through the API).

## 13. HITL regression

Full HITL suite passing. Verified **live** during the walkthrough: finding
review accepted through the real route; the decision gate blocked a premature
COMPLIANT with **409 CONFLICT** ("Critical findings remain unresolved…");
REQUIRES_FURTHER_REVIEW accepted; the engine never writes a decision — only an
authenticated human in a decision role.

## 14. Demo readiness

- Three seeded full-lifecycle inspections (`DEMO-FOOD` / `DEMO-WATER` /
  `DEMO-OIL`): each with package image, real OCR run, 7–8 extracted fields,
  evaluation, 9 findings, 9 inspector reviews, final NON_COMPLIANT decision,
  ~27 audit events, full evidence graph — **all produced through the real
  services at seed time**, nothing hand-inserted.
- The demo database currently on disk is pristine (benchmarks and walkthrough
  artifacts wiped; rebuilt from migrations + seeds, verified through the
  running servers).
- Fully offline after a one-time model download; no external AI API key.
- Failure plan documented (`docs/demo.md` §6).

## 15. Manual walkthrough — ACTUALLY PERFORMED

Run against live servers (uvicorn :8000 + vite :5173, the documented demo
flow), every step through the real HTTP API / proxy:

health 200 · inspector login · 3 demo inspections listed · create inspection
201 · upload graded ACCEPTABLE · anonymous write 401 · perceive 202 → real OCR
→ terminal run · 8 fields with rawText+confidence · evaluate → 9 engine
findings · evidence graph 75 nodes / 117 edges · audit trail 18 events ·
auditor write 403 / read 200 · finding review accepted · decision gate blocked
premature COMPLIANT (409) · field correction accepted with AI original
preserved · REQUIRES_FURTHER_REVIEW accepted · frontend served on :5173 with
`/api` proxy verified (health + login 200 through the proxy).

Honest scope note: performed at the HTTP level through the real servers and
proxy — the exact endpoints the UI calls — not by clicking in a browser (no
browser available in this environment). UI rendering is covered by typecheck
and the same client code paths.

## 16. Failed-image behaviour (tested)

Malformed bytes and empty uploads fail cleanly with structured errors (no
crash, no fabricated output) — integration-tested and re-verified live.
Oversized images are capped; degraded-but-usable images proceed with honest
grades; rejected images never reach OCR ("attach at least one usable image"
guard).

## 17. Documentation

New: `docs/production-hardening.md` (all hardening evidence + measured
numbers), `docs/testing.md` (suite layout, guarantees, honest gaps),
`docs/demo.md` (run book, seeded-demo contents, stage script, failure plan).
Updated: `README.md` (honest current limitations, Prompt 10 roadmap, demo
seeding, doc links). Existing domain docs unchanged.

## 18. Secrets

- Pattern scan over all tracked files (API keys, tokens, private keys, JWTs,
  cloud credentials): **no hits**.
- Hard-coded credential-assignment scan: only documented demo/dev placeholders
  (`changeme-*`, `dev-only-insecure-change-me`) in `.env.example` and config
  defaults; the app warns if the dev secret reaches production.
- `.gitignore` covers `.env*` (with `!.env.example`), `*.db`, `storage/`.
- The Prompt 9 dev-DB backup file was deleted from the working tree.
- No secret values are printed in this report.

## 19. Known limitations (honest)

1. Regulatory dataset is research-grade **UNVERIFIED** (sourced from a legal
   database reproduction; official Gazette not reachable at research time).
   No compliance finding is a legal determination.
2. English OCR only (as configured and verified); Hindi/Kannada verified at
   engine level but not enabled.
3. Aggregate UI pages (Dashboard, Risk Radar, Reports, Audit, Batches) still
   read the clearly-labelled mock adapter; the live API powers auth,
   inspections, intake, perception, compliance, review and decisions.
4. Risk Radar is demo scoring — no real risk model exists; none was added
   (Phase 19 constraint respected).
5. Inspection `status` is not advanced by perception/evaluation/decision
   services (stays at the intake transition).
6. No frontend unit tests (typecheck + lint only).
7. No OCR/vision accuracy percentages (no verified benchmark).
8. Pre-existing lint debt in untouched files (recorded in §3).
9. CPU-only OCR: ~25 s/image, and API reads slow (>10 s possible) while OCR
   saturates the CPU.

## 20. Remaining work (Prompt 10 — NOT started)

1. Flip the regulatory source to VERIFIED after human checking against the
   official Gazette / India Code; broaden document coverage.
2. Wire aggregate pages (Dashboard, Risk, Reports, Audit) to the live API;
   Risk Radar to consume the already-exposed structured signals (finding
   status/severity, field confidence, image grade, unresolved reviews) —
   transparent factors, no new black box.
3. Product/category classification; expanded deterministic rule coverage.
4. Enable + product-level validate Hindi/Marathi and other Indian scripts
   before claiming them.
5. Inspection status lifecycle wiring.
6. Reporting/export of completed inspections.
7. Frontend unit tests; clearing pre-existing lint debt.

---

**Per instructions: Prompt 10 was NOT started. Nothing was committed or pushed.**
