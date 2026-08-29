# Evidence Graph & Full Traceability (Prompt 7)

> **The Evidence Graph is a traceability representation of system inputs,
> transformations, regulatory references, and findings. It does not
> independently determine legal compliance.**

The graph connects the three real pipelines end-to-end, in both directions:

```
Prompt 4 (perception)   IMAGE → REGION → OCR → EXTRACTED FIELD
Prompt 5 (regulatory)   SOURCE → DOCUMENT → VERSION → REQUIREMENT
Prompt 6 (compliance)   FIELD + REQUIREMENT + RULE → FINDING
Prompt 7 (this doc)     the above, traversed as ONE auditable chain
```

Sources: `services/api/app/services/evidence_graph/` (builder),
`services/api/app/api/routers/evidence_graph.py` (routes),
`services/api/app/schemas/evidence_trace.py` (contract),
`apps/web/src/evidence/` (frontend).

---

## 1. What the graph is — and is not

The Evidence Graph is a **read-only traversal over existing persisted rows**.
It introduces **no new tables and no migration** — every node is an existing
record and every edge is an existing foreign-key or provenance relationship:

- A node id is `"<TYPE>:<uuid>"` where the uuid is the primary key of a real
  row in Prompt 3–6 tables (plus the audit trail).
- An edge exists only because the database records that relationship (a
  foreign key, a recorded provenance snapshot, or an audit event).
- Nothing is ever inferred, predicted, or hard-coded for display. There is no
  "fake visualization" mode: the demo and production flows use the **same
  graph engine over the same tables**.

What it does not do:

- It does **not** compute or alter compliance outcomes (Prompt 6's engine owns
  conclusions; the graph only traces them).
- It does **not** convert missing evidence into non-compliance — a finding
  with no evidence is labelled `MISSING` strength and stays whatever status
  the engine gave it.
- It does **not** record inspector decisions (Prompt 8).

## 2. Node and edge vocabulary

14 node types (`EvidenceNodeType`) and 20 edge types (`EvidenceEdgeType`),
mirrored in `packages/types/src/enums.ts`:

| Node | One per persisted record |
| --- | --- |
| `INSPECTION` | the inspection |
| `IMAGE` | a stored package image |
| `IMAGE_REGION` | a detected region on an image |
| `OCR_RESULT` | one raw OCR line |
| `EXTRACTED_FIELD` | one extracted declaration candidate |
| `REGULATORY_SOURCE` / `REGULATORY_DOCUMENT` / `REGULATORY_VERSION` | the Prompt 5 hierarchy |
| `REQUIREMENT` | a requirement definition (`rules` table) |
| `RULE` | a deterministic compliance rule (`compliance_rules`) |
| `EVALUATION` | one engine run (`compliance_evaluations`) |
| `FINDING` | one engine finding (`evaluation_findings`) |
| `PROCESSING_RUN` | one perception run |
| `AUDIT_EVENT` | one immutable audit-trail record |

Edges are typed (e.g. `OCR_SUPPORTS_FIELD`, `REQUIREMENT_EVALUATED_BY_RULE`,
`RULE_PRODUCED_FINDING`, `FINDING_SUPPORTED_BY_EVIDENCE`,
`AUDIT_RECORDS_ACTION`) — see `app/core/enums.py` for the full list. Every
edge endpoint is a node that exists in the same payload; edges are deduplicated
by `(type, source, target)` so the traversal is cycle-free.

## 3. API

All routes are GET, bearer-authenticated, and read-only:

| Route | Purpose |
| --- | --- |
| `GET /inspections/{id}/evidence-graph` | full graph; `?evaluationId=` selects a **historical** evaluation |
| `GET /compliance/findings/{id}/evidence-graph` | focused trace for one engine finding (both directions) |
| `GET /fields/{id}/evidence-graph` | reverse trace for one extracted field (+ findings that used it) |
| `GET /evidence-graph` | vocabulary + evidence-strength semantics + boundary note |

Namespace note: the spec-level `GET /findings/{id}/evidence-graph` is owned by
the Prompt 1 demo finding flow, so the engine trace lives under
`/compliance/findings/...` exactly as Prompt 6 established.

### Historical traceability

Findings freeze their provenance at evaluation time. When `?evaluationId=` is
passed, the graph traces **that run's** regulatory relationships — the version,
document and source as they were recorded — never the newest regulatory data.
Rules that have since been deactivated still appear (with `active: false`),
because the finding's deterministic trace (`detail.rules`) recorded them.

### Bounded traversal

The traversal is capped server-side (`MAX_NODES=400`, per-image OCR/region
caps, findings caps, audit-event cap). When a cap is hit the payload sets
`truncated: true` rather than silently dropping data.

## 4. Evidence strength

Each finding node/edge carries a strength label — a statement about the
**chain**, never a compliance verdict:

| Strength | Meaning |
| --- | --- |
| `DIRECT` | the finding links to a specific OCR result and/or image region |
| `DERIVED` | an extracted field exists but no specific OCR result/region is linked |
| `AMBIGUOUS` | the field is `REVIEW_REQUIRED` or its OCR confidence is < 0.6 |
| `MISSING` | no extracted field backs the finding — **not** evidence of absence, never a violation |

## 5. Frontend

`apps/web/src/evidence/`:

- **WhyChain** — the six-step human-readable trace (source → document →
  version → requirement & rule → evidence → finding). A step whose nodes are
  absent renders an honest "not recorded" row; nothing is ever filled in.
- **EvidenceGraphView** — deterministic layered SVG (fixed columns by node
  category, fixed node sizes, stable order). The same payload always renders
  identically. Click a node to inspect it; hovering highlights its
  relationships.
- **NodeDetailPanel** — the whitelisted metadata of one node, per node type,
  plus its real relationships.
- **ImageEvidenceModal** — "show me the pixels": opens the real stored image
  with the perception overlays and the traced region highlighted.

Integration points: the Workspace evidence-graph card, the finding explanation
drawer (WHY chain section), the field evidence drawer (reverse trace section)
and the review queue (per-row "Trace" button). Every surface renders the
boundary note.

## 6. Security

Node metadata is whitelisted per node type in the builder. The graph never
exposes storage keys, filesystem paths, credentials, API keys, tokens or any
secret; image checksums are truncated for display. OCR/image contents are
never logged by the graph layer (it only reads rows that already exist).
A test scans serialized payloads for sensitive key patterns.

## 7. Demo data honesty

Regulatory demo rows carry `isDemo` flags exactly as Prompt 5 defined them;
the graph surfaces those flags on the corresponding nodes rather than
inventing citations. The system never fabricates a government citation: if the
underlying row is demo data, the node says so.
