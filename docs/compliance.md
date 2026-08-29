# Deterministic Compliance Engine (Prompt 6)

> **Compliance findings are system-generated decision-support outputs. They are
> not, by themselves, legal enforcement determinations.**
>
> The system must never claim that an AI model itself determines legality. The
> deterministic engine records what was detected, what the applicable
> requirement expects, which rule was applied, and why the conclusion follows —
> **the inspector remains responsible for the final enforcement decision.**

The engine connects Prompt 4 (perception: image → OCR → vision → extracted
fields with evidence) to Prompt 5 (regulatory intelligence: source → document →
version → requirement with provenance):

```
detected field + applicable requirement + deterministic rule
        → evaluation → finding (evidence + explanation + provenance)
```

Sources: `services/api/app/services/compliance/` (engine, evaluators,
resolvers, applicability, seed rules), `services/api/app/models/compliance.py`,
`services/api/app/api/routers/compliance.py`.

---

## 1. Domain model

Three new tables (migration `e7a4c1f8b3d2`, fully reversible):

| Table | One row per | Key columns |
| --- | --- | --- |
| `compliance_evaluations` | evaluation **run** over an inspection | `inspection_id`, `regulatory_version_id`, `status`, `engine_version`, `context_date`, `summary` (counts only), `error`, `actor_id` |
| `compliance_rules` | deterministic rule bound to a real requirement | `requirement_id` (FK `rules.id`), `rule_code`, `rule_type`, `rule_version`, `configuration` (JSON), `active` |
| `evaluation_findings` | (evaluation, requirement) pair | `requirement_id`, `extracted_field_id`, `evidence_region_id`, `image_id`, `status`, `severity`, `applicability`, `detected_value`, `expected_value`, `explanation`, `provenance` (frozen snapshot), `detail` (rule trace) |

Prompt 1's demo `compliance_findings` / `evidence` tables are untouched. The
engine's findings live under a separate namespace (`evaluation_findings`) and
are exposed at `/inspections/{id}/compliance/findings` — deliberately **not**
at `GET /inspections/{id}/findings`, which continues to serve the demo flow.

### Evaluation lifecycle

`NOT_EVALUATED` → `EVALUATING` → one of `COMPLETED` / `PARTIAL` /
`REVIEW_REQUIRED` / `FAILED` / `NO_APPLICABLE_REQUIREMENT`.

Evaluations are immutable-by-convention: every run inserts a NEW row;
historical results (and the regulatory version they used) are never
overwritten and remain reproducible via
`GET /compliance/evaluations/{evaluation_id}`.

### Finding statuses (a closed, honest vocabulary)

| Status | Meaning |
| --- | --- |
| `COMPLIANT` | every rule passed, with adequate valid evidence **and** positive applicability |
| `NON_COMPLIANT` | at least one rule failed against the detected value |
| `REVIEW_REQUIRED` | evidence insufficient or ambiguous, or applicability UNKNOWN — **the engine does not guess** |
| `NOT_DETECTED` | no field of the requirement's type was perceived — *not* evidence the declaration is absent |
| `NOT_APPLICABLE` | deterministically resolved as not applying (decision + reason recorded) |
| `NOT_EVALUATED` | no deterministic rule is configured for the requirement |

`FIELD_NOT_FOUND` (nothing was perceived) is explicitly distinguished from
`FIELD_CONFIRMED_ABSENT` (the declaration is affirmatively absent) — only the
former occurs in practice, and it is **never** converted into legal
non-compliance.

---

## 2. Deterministic pipeline

```
ComplianceEngine
 ├─ RequirementResolver   version in force at the inspection's context date
 │                        (explicit NO_APPLICABLE_VERSION — never "newest")
 ├─ ApplicabilityResolver YES / NO / UNKNOWN from the requirement's
 │                        applicability_definition + product category +
 │                        import status (import status itself derived only
 │                        from IMPORTER_DETAILS evidence — never guessed)
 ├─ RuleResolver          active ComplianceRule rows for the requirement
 ├─ EvidenceResolver      best field for the requirement's field_key from the
 │                        latest perception run per image (highest OCR
 │                        confidence wins; RAW / NORMALIZED / UNIT / METHOD
 │                        preserved verbatim)
 ├─ DeterministicEvaluator one function per rule type (see §3)
 └─ FindingBuilder        status aggregation + explanation + provenance
                           snapshot + evidence references
```

Aggregation per requirement: any rule failure → `NON_COMPLIANT`; no perceived
field at all → `NOT_DETECTED`; any indeterminate outcome (insufficient
evidence, ambiguity, engine failure) → `REVIEW_REQUIRED`; otherwise
`COMPLIANT`. An engine failure is **never** converted into `COMPLIANT`.

A uniform evidence-quality gate applies to every requirement: if the best
evidence field is flagged for review by perception or its OCR confidence is
below 0.6, the finding is `REVIEW_REQUIRED` regardless of what the rules
computed — a positive conclusion requires enough valid evidence.

### Error codes

Structural failures are recorded on the evaluation (`status=FAILED`,
`error.code`) and audited — never surfaced as compliance:

`REGULATORY_DATA_UNAVAILABLE`, `NO_APPLICABLE_VERSION`,
`NO_APPLICABLE_REQUIREMENT`, `INSUFFICIENT_EVIDENCE`, `AMBIGUOUS_VALUE`,
`RULE_EXECUTION_FAILED`, `INVALID_REGULATORY_DATA`.

---

## 3. Rule types (closed vocabulary, 13)

`PRESENCE`, `FIELD_REQUIRED`, `FIELD_NOT_REQUIRED`, `TEXT_MATCH`,
`TEXT_PATTERN`, `NUMERIC_VALUE`, `UNIT_MATCH`, `MRP_FORMAT`, `DATE_FORMAT`,
`CONTACT_FORMAT`, `DECLARATION_FORMAT`, `RANGE`, `COMPARISON`.

Properties:

- **No LLM anywhere.** `GET /compliance/engine` publishes the vocabulary and
  the `usesLlm: false` contract. A hard requirement of this phase.
- **Decimal-safe numerics.** All money/quantity comparisons use
  `decimal.Decimal` — floats are never used.
- **MRP parsing is deterministic.** A structural check (currency symbol +
  parseable amount + "inclusive of all taxes" wording on the RAW text). A
  price marker with unreadable digits is `AMBIGUOUS_VALUE` — the engine never
  invents a value.
- Every seeded rule corresponds to a **verified Prompt 5 requirement** (FK to
  `rules.id`). The engine never invents requirements, regulations, rule
  numbers or citations — Prompt 5 data is the source of truth. Seeding is
  idempotent on `(requirement_id, rule_code)` and controlled by
  `SEED_COMPLIANCE_RULES=true`.

---

## 4. Explainability

Every finding's explanation answers seven questions:

1. **What was detected?** (verbatim detected value)
2. **What does the applicable requirement expect?** (expected value/format)
3. **Which regulatory source, document and version apply?** (frozen
   provenance snapshot)
4. **Which rule was applied?** (rule type + configuration, per-rule outcome in
   `detail.rules`)
5. **Why does the conclusion follow?** (headline reason from the rule trace)
6. **Where is the evidence?** (`extracted_field_id`, `evidence_region_id`,
   `image_id` — real rows, never fabricated)
7. **When was it evaluated?** (`created_at`, with `engine_version`)

The summary is **counts only** — `{totalFindings, byStatus, reviewQueueCount,
requirementsEvaluated}`. There is deliberately no percentage, no "legal
confidence = 97%", no risk score. Severity (`INFO`/`MINOR`/`MAJOR`/`CRITICAL`)
is a deterministic triage label derived from the status — never a legal
penalty.

---

## 5. API (all bearer-token authenticated)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/inspections/{id}/evaluate` | run one evaluation — INSPECTOR/SUPERVISOR/ADMIN; a NEW run each time |
| GET | `/inspections/{id}/compliance` | latest evaluation, or explicit `NOT_EVALUATED` + `evaluation: null` |
| GET | `/inspections/{id}/compliance/findings` | findings of the LATEST evaluation |
| GET | `/compliance/evaluations/{id}` | one historical evaluation (reproducible) |
| GET | `/compliance/findings/{id}` | one finding with explanation + provenance |
| GET | `/compliance/engine` | engine version, rule vocabulary, no-LLM contract |
| GET | `/compliance/review/queue` | paginated findings awaiting an inspector decision |

Every payload carries the boundary note:

> *System finding — inspector decision pending. Compliance findings are
> system-generated decision-support outputs. They are not, by themselves,
> legal enforcement determinations.*

The review queue lists only findings from each inspection's **latest**
evaluation with statuses `REVIEW_REQUIRED`, `NON_COMPLIANT`, `NOT_DETECTED` or
`NOT_EVALUATED` (`COMPLIANT`/`NOT_APPLICABLE` are informational and never
queued). The queue is **read-only** — recording the final enforcement decision
(approve/reject with reasons) is a later phase.

### Audit events

`COMPLIANCE_EVALUATION_STARTED`, `COMPLIANCE_EVALUATION_COMPLETED` (or
`COMPLIANCE_EVALUATION_FAILED` with the error code), and
`COMPLIANCE_FINDING_CREATED` per finding.

---

## 6. Frontend

- **Workspace (real inspections)** — a *Compliance engine* card (run button,
  evaluation status badge, count-only summary) and a *Compliance findings*
  card (status + applicability badges per requirement). Clicking a finding
  opens a drawer with the detected-vs-expected values, the deterministic
  explanation, the per-rule trace (PASS/FAIL/INDETERMINATE + reason) and the
  frozen regulatory provenance. No approve/reject control exists.
- **Review page** — an *Engine findings* tab (live mode) listing the
  read-only review queue.
- Shared types: `packages/types` (`EngineFinding`, `ComplianceEvaluation`,
  …); presentation metadata: `packages/config` (`ENGINE_FINDING_STATUS_META`,
  `EVALUATION_STATUS_META`, …).

No compliance logic lives in React components — the UI renders engine output
verbatim and never re-scores, aggregates into percentages, or fabricates
values.

---

## 7. Testing

`services/api/tests/test_compliance_engine.py` (68 tests) covers the
applicability resolver, all 13 evaluators (incl. decimal safety, MRP
ambiguity, `FIELD_NOT_FOUND` denial-of-absence), and the end-to-end engine
over the real seeded regulatory data — including the golden cases:

| Case | Scenario | Expected |
| --- | --- | --- |
| A | every declaration detected | `COMPLETED`, all `COMPLIANT` |
| B | no MRP field at all | `NOT_DETECTED` — never `NON_COMPLIANT` |
| C | MRP without "inclusive of all taxes" | `NON_COMPLIANT` |
| D | low OCR confidence MRP | `REVIEW_REQUIRED`, no conclusion |
| E | import status unknown | applicability `UNKNOWN` → `REVIEW_REQUIRED` |
| F | electronics category | best-before requirement `NOT_APPLICABLE` |

Plus determinism (same inputs → byte-identical explanations), history
preservation (re-evaluation never overwrites), counts-only summary, the
seven-question explanation, real evidence references, audit events, version
selection (2011/2016/2017), and the failure codes.
`services/api/tests/test_compliance_api.py` (31 tests) covers the HTTP
surface: RBAC (401/403), 404s, boundary notes on every payload, the explicit
`NOT_EVALUATED` before a run, never-overwrite semantics, the read-only queue
(no decision fields), and audit events.

---

## 8. Known limitations

- **Research-grade regulatory data.** The seeded Legal Metrology content is
  `UNVERIFIED` (see [regulatory.md](./regulatory.md)); the 2017 consolidated
  version boundary is a conservative modelling choice pending Gazette
  verification. Only VERIFIED data should inform real enforcement.
- **Rule coverage is narrow by design.** Only the 13 structural rule types
  exist; semantic checks (e.g. "is the declared quantity *truthful*") are out
  of scope and always will be for a deterministic engine.
- **Single-field evidence.** Each requirement is evaluated against the best
  single extracted field of its type; cross-declaration consistency checks are
  not implemented.
- **Import status inference** depends on an `IMPORTER_DETAILS` field being
  perceived; otherwise it is honestly `UNKNOWN`.
- **No inspector decision recording yet** — that is the next phase (Prompt 8);
  the review queue deliberately performs no approval.
