# UI-09 — Search, History & Operational Intelligence

Global search, inspection history, product repository and operational
intelligence for METRASIGHT. Everything below is **database-backed**: every
number on these pages comes from a `COUNT()`/aggregation the backend computed
over real rows, or it is not shown (`N/A` / "Not enough data" instead of a
fake value).

New routes (frontend): `/history`, `/products`, `/products/:id`, `/analytics`,
plus a global search box in the TopBar.
New endpoints (backend, all under `/api/v1`):
`GET /search`, `GET /history/inspections`,
`GET /history/inspections/{id}/timeline`, `GET /products`,
`GET /products/{id}`, `GET /analytics/operational`.

---

## 1. Global search — architecture & indexing

- **No search index is built.** The dataset (departmental SQLite) is small
  enough that indexed `ILIKE`-style scans are correct and fast; a dedicated
  index (trigram/FTS) would add migration surface without a measurable win.
  Searches run server-side (`services/discovery/service.py`, `search()`) with
  SQL `LIKE` over `lower()`-ed columns, so **the whole database is never
  loaded into the browser** (§3 of the spec).
- **What is searched** (where existing data supports it): inspection
  references and product name, complaint reference / product / issue /
  location, product name / GTIN / brand / category, report reference, finding
  rule codes and detected values, extracted evidence values (`ExtractedField`).
  Queries are trimmed and case-insensitive.
- **Grouping**: hits return in six categories — inspections, complaints,
  products, reports, findings, evidence — each capped (default 5) and grouped
  in the UI panel.
- **Cross-linking**: every hit links to an **existing** detail page
  (`/inspections/:id`, `/complaints/:id`, `/products/:id`, `/reports/:id`);
  findings and evidence link to their parent inspection. No duplicate detail
  pages were created.
- **Debounce**: the input is debounced 300 ms client-side (`GlobalSearch.tsx`)
  and requires ≥2 characters; Enter jumps to `/history?q=…` for the full
  filtered history.
- **Privacy** (§28): complaint hits expose only reference / product / issue /
  location / status / createdAt / inspectionId. Reporter name, e-mail, phone
  and any other citizen PII are **never selected** by the search query —
  privacy by construction, not by frontend filtering. Internal notes and
  credentials are not part of any searchable column.

## 2. Inspection history (`/history`)

- KPI cards (Total / Compliant / Non-Compliant / Review Required / Open) are
  `COUNT()`s over the **filtered** set, computed server-side alongside the
  page (`inspection_history()` returns `kpis` + `items` in one response).
- Table columns: Inspection ID (+ originating complaint reference), Date,
  Product, Establishment, Inspector, Source, Result, Evidence, Report, Status,
  Timeline. *Establishment* is the shop from the linked citizen complaint
  (`CitizenReport.shop`); direct inspections show `—` (no establishment column
  exists on inspections today). *Evidence* is the count of captured package
  images (`Image` joined through `Package.inspection_id`).
- **Server-side pagination** (`page`/`pageSize`, default 20/page) — the page
  envelope carries `items/total/page/pageSize`.
- Filters: free-text q, status, result, source (`DIRECT_INSPECTION` /
  `CITIZEN_COMPLAINT`), inspector, date-from/date-to. The filter state lives
  in the **URL query string** (e.g. `/history?result=NON_COMPLIANT&source=CITIZEN_COMPLAINT`),
  applied on [Apply], cleared on [Clear] — so filtered views are shareable
  bookmarks. All filtering happens in SQL, not in the browser.
- **Timeline** (`/history/inspections/{id}/timeline`): built ONLY from events
  actually recorded in the database — audit events for
  `INSPECTION_CREATED` / `PACKAGE_CAPTURED` / `OCR_PROCESSED` /
  `FINDINGS_GENERATED` / `REPORT_GENERATED`, plus `EVIDENCE_REVIEWED`,
  `PHYSICAL_VERIFICATION`, `DECISION` and `REPORT_FINALIZED` stages derived
  from their real records (HITL reviews, verification tasks, decisions,
  finalized reports). **If an event does not exist it is not fabricated** —
  the drawer states this explicitly.

## 3. Product repository (`/products`, `/products/:id`)

- Products are the existing `Product` rows created by package intake; the
  list is server-side searchable (name / GTIN / brand / category) and
  paginated.
- Product detail shows: overview KPIs, declared-field history (latest
  extracted values with the inspection they came from), full inspection
  history, **repeated findings** ("A historical pattern — not a verdict on
  the current package") and a package-image gallery that links into the
  existing inspection evidence views.
- Every page carries the boundary wording: **"Historical inspection record —
  previous inspections do not prove current compliance."** The repository is
  memory, not a clearance certificate.

## 4. Operational intelligence (`/analytics`)

All figures come from `GET /analytics/operational?granularity=day|week|month`
(server-side aggregation over the whole inspections/complaints/reports
dataset; date range filterable). Calculation sources:

| Metric | Source |
| --- | --- |
| Total inspections | `COUNT(Inspection)` in range |
| Complaint-led inspections | inspections with a linked `CitizenReport` |
| Compliance / non-compliance rate | decided inspections (`InspectionDecision` / evaluation), `null` → **N/A** (insufficient data is never displayed as 0%) |
| Review required / open | result derivation + `InspectionStatus` |
| Trend chart | inspections grouped by day/week/month (granularity selector) |
| Outcome distribution | result counts + percentages |
| Complaint → inspection pipeline | real counts per stage: complaints → reviewed → accepted → inspections → completed → findings, and the conversion rate (complaints→inspections). No example/demo numbers. |
| Evidence completeness | Evidence Planner data: inspections with a planner, average completeness, incomplete, missing required evidence, measurements pending, reports blocked by evidence |
| Finding categories | the existing rule engine (`Rule` codes + `EvaluationFinding` counts) — no invented categories |
| Repeat findings | rule codes occurring on ≥2 inspections of the same product (neutral wording "Repeated inspection finding") |
| Location intelligence | complaint `location` values with real complaint/inspection/finding counts; when insufficient the page shows "Location intelligence will appear as inspection locations accumulate." — no fake map, no GPS |
| Report analytics | report counts by status + [View Reports] cross-link |
| Audit | [View Audit Trail] cross-link (ADMIN/AUDITOR/SUPERVISOR per existing RBAC) |

- Small datasets: the backend attaches a `dataNote` ("Limited data —
  analytics are based on available inspection records.") which the page shows
  as a banner.
- **No new opaque AI risk score** was introduced. Existing prioritization
  surfaces remain as-is and are labelled "AI-assisted prioritization".
- Export (§26): left as a **future-ready disabled action** ("Export
  Analytics") rather than faked — no export infrastructure exists to reuse.

## 5. RBAC & privacy

- All six new endpoints require an authenticated staff user
  (`get_current_user`): anonymous requests get **401** (verified live).
  Citizens interact only through the existing anonymous complaint/scan
  endpoints, which never expose other complaints, inspections, evidence or
  analytics — so "citizen sees only their own complaint/report" continues to
  hold by construction.
- Read access follows the app's existing operational pattern
  (INSPECTOR / SUPERVISOR / ADMIN / AUDITOR where read-only); write endpoints
  elsewhere already use `require_role(...)`. No frontend-only hiding was
  added: the backend is the enforcement point.
- Establishment history is internal (department view), not a public
  blacklist; the product repository's boundary note keeps historical records
  from being read as verdicts.

## 6. Performance

- Search input debounced 300 ms, ≥2 chars, results capped per group.
- History, products and search are paginated server-side (`limit`/`offset`
  with a `total` count); KPIs and page rows share one request/response.
- All analytics aggregation happens in SQL on the backend; the browser only
  renders the summary.

## 7. Known limitations (honest)

- Search is `LIKE`-based over lowered columns — no typo tolerance, no
  ranking, no FTS index (deliberate; see §1).
- Establishment is known only for complaint-led inspections (from the
  complaint's shop field); direct inspections have no establishment column
  today, so they show `—`.
- Location intelligence depends on free-text complaint locations; it
  aggregates exact strings (no geocoding, no map).
- Analytics export is not implemented (future-ready disabled button).
- Timeline events depend on audit rows existing; very old rows created
  before audit logging show only the stages that were recorded.

## 8. Tests & verification

- Backend: `tests/test_discovery.py` — 35 tests (search grouping/privacy,
  history filters + pagination + KPI consistency, timeline recorded-events
  only, products, analytics aggregation, RBAC 401s).
- Frontend: `apps/web/src/pages/Discovery.test.tsx` — 22 tests (debounced
  search + grouped results + cross-links, URL-persisted filters, empty
  states, N/A semantics, real pipeline numbers, boundary wording).
- Live checkpoints (§32 1–8) verified against running servers: history
  table/filters/pagination, timeline from real events, products list +
  detail, analytics from real DB (26 inspections, 17 complaint-led, pipeline
  20→17→17, conversion 85%), anonymous 401 on all new endpoints, search
  cross-navigation, URL filters hitting the backend.
