# METRASIGHT — Regulatory Intelligence Layer (Prompt 5)

> **Status:** version-aware regulatory intelligence foundation. This layer
> organises **where legal requirements come from** — source, document, version,
> effective dates, requirement definitions — and connects perceived package
> fields to *candidate* requirements.
>
> **Scope guardrail: regulatory intelligence is not itself a legal
> determination.** Nothing in this layer evaluates compliance. The strongest
> statement it makes about a perceived field is *"candidate requirement —
> applicability not evaluated, awaiting the compliance engine"* (Prompt 6).

Sources: `services/api/app/models/regulatory.py`,
`services/api/app/services/regulatory/service.py`,
`services/api/app/services/regulatory/quality.py`,
`services/api/app/db/regulatory_seed.py`,
`services/api/app/api/routers/regulations.py`.

---

## 1. The provenance hierarchy

```
RegulatorySource          WHO publishes it (Department of Consumer Affairs, …)
      └── Regulation       the DOCUMENT (LM(PC) Rules 2011, G.S.R. 202(E))
              └── RegulationVersion   a dated text (original / amendments)
                      └── Rule        a REQUIREMENT definition (Rule 6(1)(a) …)
                              └── RuleApplicability   when it applies
```

The central design rule: **the system never behaves as though an LLM or a
hard-coded AI opinion is the source of law.** Every requirement must trace up
this chain to a named source. `GET /regulations/requirements/{id}` returns the
whole chain as a `provenance` object — authority, document title and
identifier, version label, effective window, source reference, source
verification status, canonical URL.

### Verification status ≠ OCR confidence

`verification_status` on a source describes whether **the regulatory data**
was checked against an official publication:

| Status | Meaning |
| --- | --- |
| `UNVERIFIED` | Research-grade content; ineligible for production compliance evaluation. |
| `VERIFIED` | A human checked it against the official Gazette / India Code text. Flipping to VERIFIED is an **audited ADMIN action** requiring a verification note. |
| `SUPERSEDED` | Replaced by a newer verified source. |
| `ARCHIVED` | Retained for audit only. |

This is completely separate from Prompt 4's OCR confidence (a recognition
score) — the two are never conflated, never averaged, never substituted.

## 2. Versioning

* Each version has an in-force window `[effective_from, effective_until)`.
* **Selection is deterministic**: the version whose window contains the
  requested date is used (`GET /regulations/versions/resolve?documentId&on`).
* **`NO_APPLICABLE_VERSION` is an explicit state.** If no version is in force
  at the requested date the resolver returns that status with `version: null`
  — it never silently falls back to the newest version.
* Superseded versions are **never overwritten or deleted**: each version owns
  its own frozen requirement set, so a historical inspection can always be
  re-resolved against the text that was in force at the time.
* Version sets are independent by design: the 2011 original carries 6
  declarations; the 2015 amendment adds consumer care; the 2017 consolidated
  version adds country-of-origin and best-before.

## 3. Seeded data — researched, honestly labelled

The seed (`services/api/app/db/regulatory_seed.py`) is deterministic,
repeatable and **idempotent** (natural-key upserts: source name / document
code / version label / rule code). It runs at startup behind
`SEED_REGULATORY_DATA=true` (independent of `SEED_DEMO_DATA`).

What it contains — the Legal Metrology (Packaged Commodities) Rules, 2011
(G.S.R. 202(E), Department of Consumer Affairs, in force 1 April 2011) with
three versions incorporating the amendments G.S.R. 385(E)/2015,
G.S.R. 858(E)/2016 and G.S.R. 629(E)/2017, and the Rule 6(1)/6(2)
declarations.

**Honesty contract.** The material was researched (2026-08-28) from a legal
database reproduction (indiankanoon.org doc 100694501) because the official
repositories were unreachable from the development environment. Therefore
every seeded record is `UNVERIFIED` with an explicit verification note
recording the discovery source and what remains to be checked. Nothing is
presented as an authoritative legal citation, and nothing fictional is
invented: no government notifications, rule numbers, section numbers, legal
requirements, effective dates, amendments, penalties, official URLs or
government citations are fabricated. Flipping the source to `VERIFIED`
requires a human to check the content against the official Gazette / India
Code text — an audited ADMIN action via
`PATCH /regulations/sources/{id}`.

The seed ends with a **data-quality gate**
(`app/services/regulatory/quality.py`): duplicates, orphans, missing
source/document/version, invalid or overlapping effective-date windows,
missing provenance and unverified-without-note all **fail loudly**
(`REGULATORY_DATA_INVALID`, HTTP 422) — structurally invalid regulatory data
is never silently repaired or imported.

## 4. The API

All reads require authentication; the only mutation is the ADMIN-only,
audited source verification change. Filters use camelCase query params
(`verificationStatus`, `documentId`, `effectiveOn`, `isDemo`, `fieldKey`,
`current`, …).

| Endpoint | Purpose |
| --- | --- |
| `GET /regulations/sources` | Sources (+ verification filters) |
| `GET /regulations/sources/{id}` | One source |
| `PATCH /regulations/sources/{id}` | **ADMIN, audited** verification change |
| `GET /regulations/documents` | Documents (+ source/type/demo filters) |
| `GET /regulations/documents/{id}` | One document incl. its versions |
| `GET /regulations/versions` | Versions (+ document/status/effectiveOn) |
| `GET /regulations/versions/resolve` | Deterministic effective-date selection |
| `GET /regulations/requirements` | Paginated requirements (all filters) |
| `GET /regulations/requirements/{id}` | Requirement + full provenance |
| `GET /inspections/{id}/regulatory-candidates` | Field → candidate requirements |

Prompt 1's demo endpoints (`GET /regulations`, `GET /rules`,
`GET /rules/validators`) are unchanged and still serve only `is_demo` data.

## 5. Candidate mapping (perception → regulations, no evaluation)

`GET /inspections/{id}/regulatory-candidates` takes the extracted fields from
the latest perception run per image and maps each to the requirement
definitions in force at the inspection's context date (override with `on=`).
The mapping is a **deterministic read-time join** on
`field_type ↔ rule.field_key` — nothing is persisted, so regulatory updates
can never leave stale field→requirement links behind.

Every entry is explicitly marked:

```
mappingStatus       = CANDIDATE
applicabilityStatus = APPLICABILITY_NOT_EVALUATED
evaluationStatus    = AWAITING_COMPLIANCE_ENGINE
```

and the payload carries the constant `regulatoryEvaluation:
"AWAITING_REGULATORY_EVALUATION"`. An empty candidate list means *no
definition in force maps to this field type* — an absence of a definition,
never a statement of compliance. **No COMPLIANT / NON-COMPLIANT verdict
exists anywhere in this layer.**

The demo compliance flow is protected from real requirements:
`get_applicable_rules` filters `Regulation.is_demo == true`, so the Prompt 1
demo findings never mix in the (unverified) researched requirements.

## 6. Evidence chain

Prompt 4's evidence model is untouched. The chain now reads:

```
IMAGE → REGION → OCR RESULT → EXTRACTED FIELD
                                       └─(read-time join)→ REQUIREMENT
                                                            → VERSION
                                                            → DOCUMENT
                                                            → SOURCE
```

The regulatory half is FK-based (`source_id`, `regulation_version_id`), the
perception half keeps its Prompt 4 FKs — provenance is followed through
references, not duplicated text.

## 7. Auditability

Every modification of authoritative regulatory data is audited:
`REGULATORY_SOURCE_UPDATED` (with before/after verification states),
`REGULATORY_SOURCE_CREATED`, `REGULATORY_DOCUMENT_CREATED`,
`REGULATORY_VERSION_CREATED`, `REGULATORY_VERSION_SUPERSEDED`,
`REGULATORY_REQUIREMENT_CREATED`, `REGULATORY_REQUIREMENT_UPDATED`,
`REGULATORY_DATA_SEEDED`. Ordinary inspectors can never alter authoritative
regulatory records — only the ADMIN role can, and only through the audited
verification endpoint.

## 8. UI

The Regulations page renders the real hierarchy (Documents / Requirements /
Versions / Sources tabs) with verification badges distinguishing VERIFIED /
UNVERIFIED / SUPERSEDED sources, DEMO rows clearly labelled, and loading /
empty / error states throughout. The declaration evidence drawer
(Workspace → click a perceived field) gained a *Candidate requirements*
section showing the definitions mapped to that field, each with its version,
source reference and source verification status — always ending at the
"candidate association only" boundary note.

## 9. Security notes

* No secrets, credentials or API keys are stored in seed data or source code.
* Source URLs in the seed are fixed, curated values; externally supplied URLs
  are validated/sanitised before use.
* Only the ADMIN role can modify authoritative regulatory records, and only
  via the audited endpoint; all other routes are read-only for authenticated
  users.

## 10. Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `SEED_REGULATORY_DATA` | `true` | Idempotent regulatory seed at startup (set `false` to manage the layer purely via import/API). |

## 11. Testing

`tests/test_regulatory_intelligence.py` + `tests/test_regulatory_api.py`
cover: hierarchy provenance, deterministic and boundary-date version
selection, `NO_APPLICABLE_VERSION`, old/new version independence, historical
requirement retrieval, idempotent seed, the loud-failing quality validator
(each issue class), candidate mapping (including context-date resolution and
unknown field types), the no-compliance-verdict guarantee, RBAC (403/401),
audited verification changes (before/after), pagination/filtering, and the
Prompt 1–4 regression suites. The Alembic migration is exercised
upgrade → downgrade → upgrade on a scratch database.
