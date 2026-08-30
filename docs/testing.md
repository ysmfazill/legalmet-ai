# Testing

How the METRASIGHT system is tested — what is actually verified, what is
deliberately excluded from the fast suite, and what remains untested (stated
honestly, not hidden).

---

## Layout

All automated tests live in `services/api/tests/` (pytest). The frontend has
**no unit-test runner** — it is covered by `tsc --noEmit` (typecheck) and
ESLint only, plus the backend-driven end-to-end flow. This is a known
limitation, listed in the Prompt 9 known-limitations section.

```
services/api/tests/
├─ conftest.py                        # in-memory SQLite (StaticPool), app + services fixtures
├─ test_health.py                     # liveness + readiness probes
├─ test_auth.py                       # JWT login, roles, protected routes
├─ test_api_security.py               # Prompt 9: no anonymous writes, read-only role, storage traversal, error envelopes
├─ test_inspection_flow.py            # inspection lifecycle over the API
├─ test_intake.py / test_storage.py   # real image intake, quality gate, local storage backend
├─ test_quality_analyzer.py          # image usability grading (blurriness, glare, low light, resolution)
├─ test_perception_api.py             # perception routes, 202 kickoff, run lifecycle
├─ test_perception_pipeline.py        # pipeline orchestration, run status transitions
├─ test_perception_extract.py         # field extraction from OCR text (deterministic)
├─ test_ocr_robustness_integration.py # MARKED integration — real PaddleOCR on perturbed labels
├─ test_ocr_languages_integration.py  # MARKED integration — real OCR per configured language
├─ test_perception_integration.py     # MARKED integration — real OCR end-to-end
├─ test_golden_e2e_integration.py     # MARKED integration — full golden path with real OCR
├─ test_compliance_engine.py          # deterministic rule engine unit tests
├─ test_rule_engine.py                # rule evaluation primitives, decimal-safe numerics
├─ test_compliance_api.py             # evaluation endpoints, immutable evaluation history
├─ test_regulatory_intelligence.py    # version-aware requirement resolution, provenance
├─ test_regulatory_api.py             # regulatory routes, candidate mapping
├─ test_evidence.py / test_evidence_graph.py  # evidence references + graph builder (AI vs HUMAN origin)
├─ test_hitl.py                       # review, corrections, decision gate, audit
├─ test_hardening.py                  # Prompt 9: quality gate, resource limits, duplicate guards
└─ test_db_integrity_integration.py   # MARKED integration — alembic-migrated schema == ORM models, FK integrity
```

## Running

```bash
cd services/api
source .venv/Scripts/activate        # or .venv/bin/activate

pytest                               # fast suite (unit + API, in-memory SQLite) — excludes integration
pytest -m integration                # real-engine tests (PaddleOCR CPU; minutes, needs cached models)
pytest -m integration test_ocr_robustness_integration.py   # one integration file
```

The default addopts is `-m 'not integration'`; a CLI `-m integration`
overrides it. Integration tests need the perception engines installed
(`paddlepaddle==3.0.0 paddleocr==3.1.0 paddlex==3.1.0`) and the PP-OCRv5
models cached in `~/.paddlex/official_models` (downloaded on first run).

### Lint / types

```bash
cd services/api && ruff check app tests scripts
cd apps/web && npm run lint && npm run typecheck   # repo root: npm run lint -w @legalmet/web
```

## Why integration tests are a separate mark

Real OCR inference is CPU-only PaddleOCR: ~15–25 s **per image** on this
machine. Mixing that into the default suite would make the fast feedback loop
minutes long, so everything touching a real engine is marked `integration`.
Everything else runs against in-memory SQLite with the perception pipeline's
provider seams — the seam implementations used in unit tests are the *real*
preprocessor/extractor logic; only the OCR/vision engines are swapped.

## What the tests actually guarantee

- **No silent mock fallback in real mode:** the real-mode perception service
  raises `AI_SERVICE_UNAVAILABLE` when engines are missing; there is no code
  path that substitutes stub OCR output for a real run. Verified by test and
  by the Phase 22 no-fake-AI code review.
- **Schema truth:** `test_db_integrity_integration.py` diffs
  `Base.metadata` against an alembic-upgraded scratch database column by
  column, so ORM/migration drift (the Prompt 9 finding) cannot recur silently.
- **API security:** every mutating route is enumerated dynamically and tested
  for 401 (anonymous) and 403 (read-only AUDITOR); storage keys are tested
  against path traversal including the sibling-prefix collision case.
- **Human-in-the-loop invariants:** the decision gate blocks COMPLIANT while
  unresolved critical findings exist; the engine never writes a decision.

## Known gaps (honest)

- No frontend unit tests (typecheck + lint only).
- Integration tests depend on locally cached OCR models — on a machine without
  them, the first run needs network access to download (documented in
  `docs/ocr.md`).
- Performance benchmarks are a script (`services/api/scripts/benchmark_phase16.py`),
  not an assertion suite — see `docs/production-hardening.md` for the recorded
  numbers and the machine they were measured on.
