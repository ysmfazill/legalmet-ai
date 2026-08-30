# Human-in-the-Loop Inspector Review, Correction & Final Decision (Prompt 8)

> **METRASIGHT provides AI-assisted inspection analysis and traceability. The
> authorized inspector remains responsible for the final inspection decision.**
>
> The system must never claim that an AI model itself determined a package to
> be illegal. Every legal conclusion recorded in the database is authored by
> an authenticated, role-authorized human — with a reason, an actor and an
> immutable audit trail.

Prompt 8 closes the loop that Prompts 4–7 opened: the perception pipeline sees
the package, the regulatory intelligence resolves the applicable requirements,
the deterministic engine produces findings, the evidence graph traces them —
and the **inspector reviews, corrects and decides**:

```
engine finding (frozen system output)
      → human review (CONFIRM / CORRECT / REJECT / OVERRIDE / ESCALATE)
      → (corrections feed a NEW evaluation — history is never mutated)
      → final decision (COMPLIANT / NON_COMPLIANT / REQUIRES_FURTHER_REVIEW)
```

Sources: `services/api/app/services/hitl/` (service, state machine, decision
gate), `services/api/app/models/hitl.py`, `services/api/app/api/routers/hitl.py`,
`apps/web/src/hitl/` (review controls + final-decision card).

---

## 1. Correction architecture (Phase 1) — append-only, never destructive

Correcting a value **never overwrites the AI output**. `extracted_fields`
keeps its original `raw_text`, `normalized_value` and `confidence` untouched;
the correction is a new row in `field_corrections`:

| Table | One row per | Key columns |
| --- | --- | --- |
| `field_corrections` | one human correction of one extracted value | `extracted_field_id`, `inspection_id`, `corrected_by`, `corrected_at`, `previous_value`, `previous_raw_text`, `corrected_value`, `reason` (NOT NULL), `triggered_by_evaluation_id` |

`extracted_fields.corrected_value / corrected_at / corrected_by /
corrected_reason` are **latest-correction pointers only** — a read model, not
a mutation. The full before/after history lives in `field_corrections`
(`GET /fields/{field_id}/corrections`, oldest first).

### Re-evaluation (Phase 3)

The compliance engine prefers `corrected_value` over the AI values, labels the
finding `detail.valueSource = HUMAN_CORRECTED` (vs `AI_EXTRACTED`), and
bypasses the low-confidence evidence gate for human-confirmed values (a
correction is sufficient evidence by definition). Re-evaluation **creates a
new `compliance_evaluations` row** — the historical evaluation and its
findings are preserved byte-for-byte, still showing the original AI values.

## 2. Finding review state machine (Phases 4, 20) — enforced in the backend

States (`FindingReviewState`): `PENDING_REVIEW`, `CONFIRMED`, `CORRECTED`,
`REJECTED`, `OVERRIDDEN`, `ESCALATED`.

Legal transitions (enforced in `HitlService._REVIEW_TRANSITIONS`; the
frontend can only *request* an action):

```
CONFIRM : PENDING_REVIEW/ESCALATED/CORRECTED → CONFIRMED
CORRECT : PENDING_REVIEW/ESCALATED           → CORRECTED   (creates a FieldCorrection)
REJECT  : PENDING_REVIEW/ESCALATED           → REJECTED    (terminal, reason mandatory)
ESCALATE: any non-terminal                   → ESCALATED   (reason mandatory)
OVERRIDE: CONFIRMED/CORRECTED/REJECTED/ESCALATED → OVERRIDDEN (terminal,
           SUPERVISOR/ADMIN only, reason mandatory)
```

Repeating the current state is an idempotent no-op (no duplicate events,
Phase 21). Illegal transitions are rejected with `409 CONFLICT`. Findings
with no review row are implicitly `PENDING_REVIEW` — the engine never writes
review rows (`reviews` are an overlay, one per finding, unique).

A review with no row yet is served as a synthetic `PENDING_REVIEW` overlay
(`id: null`) so reads stay honest.

## 3. Final decision (Phases 5, 13, 14) — the only legal conclusion

`InspectionDecisionType`: `COMPLIANT`, `NON_COMPLIANT`,
`REQUIRES_FURTHER_REVIEW`, `NOT_EVALUATED`. **The engine can never produce
any of these values** — they exist only as human-authored rows in
`inspection_decisions`.

- **Decision gate (Phase 13):** findings with severity `CRITICAL`/`MAJOR`
  still `PENDING_REVIEW` or `ESCALATED` block `COMPLIANT` /
  `NON_COMPLIANT` (409). `REQUIRES_FURTHER_REVIEW` is always available as the
  honest deferral.
- **Immutability (Phase 14):** decisions are append-only. A new decision
  supersedes the previous one via `supersedes_decision_id`; nothing is
  deleted. `GET /inspections/{id}/decision-history` returns the full chain.
- **Reasons (Phase 6):** mandatory for `NON_COMPLIANT` and
  `REQUIRES_FURTHER_REVIEW`, and for any decision that supersedes an earlier
  one. An unexplained override, rejection, escalation or non-compliance
  conclusion is structurally impossible (schema + service layers).

## 4. Authorization (Phase 7)

| Role | Read | Review / correct / decide | Override |
| --- | --- | --- | --- |
| `INSPECTOR` | ✓ | ✓ | ✗ (403) |
| `SUPERVISOR` | ✓ | ✓ | ✓ |
| `ADMIN` | ✓ | ✓ | ✓ |
| `AUDITOR` | ✓ (read-only) | ✗ (403) | ✗ (403) |

Enforced via `require_role(...)` in the router plus role checks in the
service (`OVERRIDE` is restricted to `SUPERVISOR`/`ADMIN`). Existing stricter
policies elsewhere in the codebase are untouched.

## 5. API (Phase 18)

| Endpoint | Purpose |
| --- | --- |
| `POST /fields/{field_id}/correct` | record a correction (append-only) |
| `GET /fields/{field_id}/corrections` | full correction history |
| `GET /fields/{field_id}/review` | original AI value vs latest correction |
| `POST /compliance/findings/{finding_id}/review` | one action: `{action, reason?, correctedValue?}` |
| `POST /compliance/findings/{finding_id}/confirm\|reject\|override\|escalate` | per-verb sugar — same state machine |
| `GET /compliance/findings/{finding_id}/review` | review state + transition events |
| `POST /inspections/{inspection_id}/decision` | record the final human decision |
| `GET /inspections/{inspection_id}/decision` | current decision (404 when none) |
| `GET /inspections/{inspection_id}/decision-history` | full supersede chain |
| `GET /inspections/{inspection_id}/review-status` | per-state counts, gate, current decision |

Every response carries the boundary note above.

## 6. Evidence graph integration (Phase 15) — AI ≠ HUMAN

Three new node types (`FIELD_CORRECTION`, `FINDING_REVIEW`,
`INSPECTION_DECISION`) and edges (`FIELD_CORRECTION_CORRECTS_FIELD`,
`FINDING_REVIEW_REVIEWS_FINDING`, `FINDING_REVIEW_LINKS_CORRECTION`,
`DECISION_FOR_INSPECTION`, `DECISION_BASED_ON_EVALUATION`,
`DECISION_SUPERSEDES_DECISION`). Every node carries `metadata.origin`:

- `AI` — machine output (OCR, regions, extracted fields, evaluations, findings)
- `HUMAN` — authorised human actions (corrections, reviews, decisions)
- `SYSTEM` — neutral records (inspections, images, regulatory data)

AI outputs and human actions are **never represented as identical**: a
correction is its own HUMAN node pointing *at* the untouched AI field node.

## 7. Audit trail (Phase 16)

Every human action is recorded (append-only, actor + role + previous/new
state + reason; never any credentials): `FIELD_REVIEWED`, `FIELD_CORRECTED`,
`FINDING_CONFIRMED`, `FINDING_REJECTED`, `FINDING_OVERRIDDEN`,
`FINDING_ESCALATED`, `DECISION_SUBMITTED`, `DECISION_CHANGED`,
`SUPERVISOR_REVIEWED`.

## 8. Frontend (Phases 8–12, 17)

- **Review queue** (`EngineReviewQueueSection`) — every row shows the system
  finding *and* the human review state as separate badges.
- **Workspace** — findings open the explanation drawer, which now embeds
  `FindingReviewControls` (confirm / correct / reject / escalate / override,
  mandatory reasons, before/after correction comparison).
- **Final decision card** (`FinalDecisionCard`) — review progress, the
  decision gate with blockers, explicit confirm step, supersede history.
- **Reports** — AI-assisted analysis and the inspector's decision are
  separate sections, each labelled.

## 9. Migration

`f8b2d6a4c1e9` (fully reversible; upgrade → downgrade → re-upgrade verified
on a scratch SQLite database). Adds `corrected_by` / `corrected_reason` to
`extracted_fields` and creates `field_corrections`, `finding_reviews`,
`finding_review_events`, `inspection_decisions`. No historical evaluation,
audit or correction data is modified.

## 10. Testing

`tests/test_hitl.py` (correction history, state machine, decision gate,
authorization matrix for all four roles, golden end-to-end flow:
image → perception → evaluation → correction → re-evaluation → review →
escalation → decision → audit trail → graph with HUMAN nodes) and
`tests/test_evidence_graph.py::TestHumanNodes` (AI-vs-HUMAN distinction,
before/after metadata, supersede chain edges, zero human nodes for
machine-only inspections).
