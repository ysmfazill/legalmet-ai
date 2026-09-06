# METRASIGHT — Reporting & Evidence Pack (UI-08)

> **Status:** Real reporting (UI-08). Reports are **DEFENSIBLE, TRACEABLE,
> VERSIONED, EVIDENCE-BACKED, INSPECTOR-REVIEWED** decision-support artifacts
> generated from frozen inspection snapshots. They do not replace the
> authority of the authorized Legal Metrology inspector.

Sources: `services/api/app/api/routers/reports.py`,
`services/api/app/services/report/service.py`,
`services/api/app/services/report/pdf.py`,
`services/api/app/services/report/docx.py`,
`services/api/app/services/report/evidence_media.py`,
`apps/web/src/pages/Reports.tsx`, `apps/web/src/pages/ReportDetail.tsx`,
`apps/web/src/reports/*`. Interactive contract: Swagger UI at `/docs`.

All routes are under the API prefix (default `/api/v1`). Bodies are
**camelCase** (`CamelModel`); errors use the uniform envelope
`{"error": {"code", "message"}}`.

---

## 1. Boundary statement

**Reports are decision-support artifacts generated from inspection evidence.
They do not replace the authority of the authorized Legal Metrology
inspector.** This sentence ships in every artifact: the detail page footer,
the Evidence Pack drawer, the PDF first page, and the DOCX. The AI is never
presented as the final legal authority — the phrasing everywhere is
*"AI-assisted assessment. Final decision recorded by authorized inspector."*

## 2. Architecture — no parallel report system

Reporting **reuses the existing entities**: `Inspection`, `Product`,
`InspectionDecision`, `ComplianceEvaluation`/`EvaluationFinding` (the
deterministic engine output — **not** the demo-flow `ComplianceFinding`),
`VerificationTask` (the Evidence Planner), `EvidenceItem`, `Complaint`,
`AuditEvent`, `User`. Two new tables were added:

- **`reports`** — one row per inspection (the lifecycle record: status,
  version, generated/finalized timestamps and actors, amendment reason).
- **`report_versions`** — one row per generated snapshot; the frozen JSON
  blob is the *only* authority for what an exported report claims.

Report statuses: `DRAFT → UNDER_REVIEW → FINALIZED → EXPORTED` (exports
append `EXPORTED` on top of a finalized report) and `AMENDED` (a new version
was issued on a finalized report). Findings themselves are the engine's
`COMPLIANT / NON_COMPLIANT / REVIEW_REQUIRED / NOT_DETECTED / NOT_APPLICABLE
/ NOT_EVALUATED`.

## 3. SOURCE vs OFFICIAL evidence (never merged)

Every findings row and every Evidence Pack item carries an origin chip:
**SOURCE** (citizen-submitted, from the complaint flow) or **OFFICIAL**
(inspector-captured during the inspection). They are reported in separate
columns/sections and never merged into one evidence category. Complaint-origin
inspections get a "Source Context" section quoting the complaint; routine
inspections state "Routine inspection — no citizen complaint origin."

## 4. Report lifecycle & the finalization gate

```
create (DRAFT)  →  generate (snapshot v1)  →  review  →  finalize  →  export
                        ↑                                   |
                        └── amend (v2, v3 …) ←──────────────┘
```

- **Generate** freezes a snapshot: findings (with the inspector's review
  state), regulatory basis (engine + `RegulationVersion.version_label`
  only — no legal text is invented in the report UI), physical measurements
  (manual entries labelled *manual entry — instrument integration not
  available in prototype*), lot intelligence (*AI-assisted inspection
  recommendation*, never a statutory sampling claim), the inspector decision,
  and the evidence manifest with stable **E-00N** identifiers.
- **The finalization gate is enforced server-side.** Finalization is blocked
  (`409`) while any REQUIRED Evidence Planner task is open or no inspector
  decision exists, with the exact message *"Report cannot be finalized until
  required evidence is resolved."* RECOMMENDED evidence never blocks.
- A low OCR confidence never by itself yields a NON_COMPLIANT finding —
  findings come only from the engine evaluation, and the report result is
  the inspector's decision or `NOT_EVALUATED`.
- **Versioning:** amending a finalized report issues a new snapshot version
  (v2, v3…) with a mandatory reason; previous finalized versions are
  preserved verbatim — never silently overwritten.

## 5. Audit events

All lifecycle actions emit events on the existing append-only audit
architecture: `REPORT_CREATED`, `REPORT_GENERATED`, `REPORT_REVIEWED`,
`REPORT_FINALIZED`, `REPORT_EXPORTED_PDF`, `REPORT_EXPORTED_DOCX`,
`REPORT_AMENDED` — each with actor, role, timestamp, and a report-scoped
`GET /reports/{id}/audit` view.

## 6. PDF / DOCX exports and the Evidence Pack

- **PDF** — a real structured document via **reportlab** (never a
  screenshot): cover/summary, source context, findings table, evidence
  images (downscaled via Pillow; missing images stated as *"Evidence image
  unavailable."*), regulatory basis, physical verification, lot
  intelligence, inspector decision, traceability table, and the boundary
  statement. **No fake government letterhead, no official seals** — the
  footer says *"Not a government-issued document; no official seal."*
- **DOCX** — the same snapshot via **python-docx** (headings + tables,
  editable downstream).
- **Evidence Pack** — `GET /reports/{id}/evidence-pack`: the full item list
  with stable E-00N refs, provenance (origin, source, evaluation links)
  preserved, completeness summary, and the frozen decision.
- Export failure surfaces the exact spec strings: *"PDF generation failed.
  Your inspection data has not been changed."* / *"Document generation
  failed."* — no fake success, ever.

## 7. RBAC (server-side)

- **Write roles** (create/generate/review/finalize/amend): `INSPECTOR`,
  `SUPERVISOR`, `ADMIN` — enforced by `require_role` on every mutation.
  The inspector must also be assigned to the inspection (or be a supervisor
  over it) — assignment is checked server-side.
- **Read roles** (list/detail/pack/audit/exports): all authenticated roles
  including `AUDITOR`.
- Anonymous access → `401`. The frontend hides write buttons for read-only
  roles, but **hiding is never the authorization** — the backend rejects
  independently (verified: auditor finalize/amend/create → `403`).

## 8. API endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| POST | `/reports` | write | Create DRAFT report for an inspection |
| GET | `/reports` | read | List + filter (status, inspectionId, `q` search over reference/product/inspector/complaint) |
| GET | `/reports/kpis` | read | Live counters: total/draft/finalized/exported/underReview/amended/requiresReview |
| GET | `/reports/{id}` | read | Detail: metadata, frozen snapshot, gate, versions |
| POST | `/reports/{id}/generate` | write | Freeze snapshot (new version; requires evaluation + closed required evidence) |
| POST | `/reports/{id}/review` | write | DRAFT → UNDER_REVIEW |
| POST | `/reports/{id}/finalize` | write | Gate-checked finalization |
| POST | `/reports/{id}/amend` | write | New version with mandatory reason |
| GET | `/reports/{id}/evidence-pack` | read | E-00N manifest with provenance |
| GET | `/reports/{id}/export/pdf` \| `/export/docx` | read | Real file download (`Content-Disposition`, sanitized filename) |
| GET | `/reports/{id}/audit` | read | Report-scoped audit events |

## 9. Security (spec §30)

- **Export filenames** are built from sanitized tokens only
  (`[^A-Za-z0-9._-]+` → `-`, 60-char cap) — no user-controlled path
  component, no traversal. Verified by test.
- **PDF text**: every user-controlled string (product names, observations,
  complaint text, evidence filenames) passes through XML-escaped reportlab
  `Paragraph`s — markup in a product name renders as literal text, never as
  PDF content markup. Regression-tested with a hostile product name.
- **DOCX**: python-docx escapes cell/paragraph text by construction.
- **No credentials inside reports**; no secrets or API keys in the frontend;
  all report endpoints require a bearer token and enforce roles server-side;
  evidence images are loaded through the existing storage service only.

## 10. Frontend surfaces

- **`/reports` (Report Center)** — live KPIs (Total / Draft / Finalized /
  Exported / Requires Review), server-side search + status filter, and the
  real records table (Reference, Product, Date, Inspector, Result, Evidence,
  Status, Updated, actions). Empty state: *"No finalized reports yet."* with
  an **[Open Inspection]** CTA.
- **`/reports/:id`** — three columns: LEFT metadata + inspection + source
  context (SOURCE chip); CENTER the frozen snapshot sections; RIGHT the
  finalization gate checklist, lifecycle actions (generate / review /
  finalize / amend-with-reason modal / export PDF / export DOCX / Evidence
  Pack drawer), version history, and the audit trail. Errors and successes
  surface verbatim backend messages (`role=alert` / `role=status`) — no
  fake success.

## 11. Known limitations

- Instrument integration for physical measurements is not available in the
  prototype — measurements without an instrument are labelled manual entry.
- The regulatory dataset is research-grade (**UNVERIFIED — DEMO DATA, NOT
  LEGAL ADVICE**); the report quotes the engine output only.
- PDF image embedding is capped (first N evidence images embedded; the rest
  are counted in the manifest) to keep exports a sane size.
- Reports state lot sampling as an AI-assisted recommendation — no statutory
  sampling procedure is claimed.
