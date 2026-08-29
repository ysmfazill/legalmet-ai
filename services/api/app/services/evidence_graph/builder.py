"""Evidence Graph builder (Prompt 7) — full traceability over real data.

The Evidence Graph is NOT a stored structure and NOT a visualization aid: it
is a deterministic, read-only traversal over the relationships that already
exist in the database:

    Prompt 4 (perception)   IMAGE → REGION → OCR → EXTRACTED FIELD → RUN
    Prompt 5 (regulatory)   SOURCE → DOCUMENT → VERSION → REQUIREMENT
    Prompt 6 (compliance)   FINDING → RULE / REQUIREMENT / EVALUATION
    audit                   AUDIT_EVENT → entity

Every node is ONE persisted record (node id = ``"<type>:<uuid>"``) and every
edge is a typed relationship between two real entity ids. Nothing is invented:
a missing link is simply absent, and evidence quality is labelled explicitly
(DIRECT / DERIVED / AMBIGUOUS / MISSING) — MISSING evidence is never converted
into compliance.

BOUNDARY: the graph is a traceability representation of system inputs,
transformations, regulatory references and findings. It does not independently
determine legal compliance.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    EvidenceEdgeType,
    EvidenceNodeType,
    EvidenceStrength,
    ExtractionStatus,
)
from app.core.errors import NotFoundError
from app.models import (
    AuditEvent,
    ComplianceEvaluation,
    ComplianceRule,
    EvaluationFinding,
    ExtractedField,
    Image,
    ImageRegion,
    Inspection,
    OcrTextResult,
    Package,
    ProcessingRun,
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
)

EVIDENCE_GRAPH_BOUNDARY_NOTE = (
    "The Evidence Graph is a traceability representation of system inputs, "
    "transformations, regulatory references, and findings. It does not "
    "independently determine legal compliance."
)

# Confidence below which evidence is labelled AMBIGUOUS (mirrors the Prompt 6
# engine's evidence-quality floor — traceability, never a compliance verdict).
_AMBIGUOUS_CONFIDENCE_FLOOR = 0.6

# Bounded traversal: hard caps so one request can never load the database.
MAX_NODES = 400
MAX_OCR_PER_IMAGE = 60
MAX_REGIONS_PER_IMAGE = 40
MAX_FINDINGS = 60
MAX_FIELD_FINDINGS = 20
MAX_AUDIT_EVENTS = 50

# Label truncation for readable node chips.
_LABEL_MAX = 48


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _short(text: str | None, limit: int = _LABEL_MAX) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


def evidence_strength(finding: EvaluationFinding, field: ExtractedField | None) -> str:
    """Deterministic evidence-quality label for one finding (Phase 5).

    DIRECT — the finding has direct evidence (an OCR line / image region).
    DERIVED — a field exists but without direct region/OCR linkage.
    AMBIGUOUS — evidence exists but is insufficient (review / low confidence).
    MISSING — no valid evidence exists (never converted into compliance).
    """
    if field is None:
        return EvidenceStrength.MISSING.value
    if field.status == ExtractionStatus.REVIEW_REQUIRED.value or (
        float(field.confidence or 0.0) < _AMBIGUOUS_CONFIDENCE_FLOOR
    ):
        return EvidenceStrength.AMBIGUOUS.value
    if field.source_ocr_result_id is not None or field.image_region_id is not None:
        return EvidenceStrength.DIRECT.value
    return EvidenceStrength.DERIVED.value


class _Graph:
    """Mutable accumulator with node/edge dedup (cycles are impossible by
    construction: every edge is added once, keyed deterministically)."""

    def __init__(self, max_nodes: int | None = None) -> None:
        # Resolved at construction time so tests can patch builder.MAX_NODES.
        self._nodes: dict[str, dict] = {}
        self._edges: dict[str, dict] = {}
        self.max_nodes = MAX_NODES if max_nodes is None else max_nodes
        self.truncated = False

    def node(
        self,
        ntype: EvidenceNodeType,
        entity_id,
        label: str,
        metadata: dict | None = None,
    ) -> str | None:
        nid = f"{ntype.value}:{entity_id}"
        if nid in self._nodes:
            return nid
        if len(self._nodes) >= self.max_nodes:
            self.truncated = True
            return None
        self._nodes[nid] = {
            "id": nid,
            "type": ntype.value,
            "label": label,
            "metadata": metadata,
        }
        return nid

    def edge(
        self,
        source: str | None,
        target: str | None,
        etype: EvidenceEdgeType,
        metadata: dict | None = None,
    ) -> None:
        if source is None or target is None:
            return
        eid = f"{etype.value}:{source}->{target}"
        if eid in self._edges:
            return
        if len(self._edges) >= self.max_nodes * 3:
            self.truncated = True
            return
        self._edges[eid] = {
            "id": eid,
            "source": source,
            "target": target,
            "type": etype.value,
            "metadata": metadata,
        }

    def has_node(self, ntype: EvidenceNodeType, entity_id) -> bool:
        return f"{ntype.value}:{entity_id}" in self._nodes

    def out(self, **root) -> dict:
        return {
            "nodes": list(self._nodes.values()),
            "edges": list(self._edges.values()),
            "nodeCount": len(self._nodes),
            "edgeCount": len(self._edges),
            "truncated": self.truncated,
            "boundaryNote": EVIDENCE_GRAPH_BOUNDARY_NOTE,
            **root,
        }


class EvidenceGraphService:
    """Builds bounded, cycle-free evidence graphs over real persisted data."""

    # ------------------------------------------------------------------ API

    def graph_for_inspection(
        self,
        db: Session,
        inspection_id: uuid.UUID,
        *,
        evaluation_id: uuid.UUID | None = None,
    ) -> dict:
        """Full graph for one inspection (perception + regulatory + findings).

        ``evaluation_id`` selects a HISTORICAL evaluation; by default the latest
        is used. Historical regulatory relationships are never re-resolved: the
        finding rows themselves carry the requirement/version used at the time.
        """
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")

        g = _Graph()
        insp = self._add_inspection(g, inspection)

        evaluation = self._resolve_evaluation(db, inspection_id, evaluation_id)
        ev_node = self._add_evaluation(g, evaluation) if evaluation else None
        if evaluation is not None:
            g.edge(insp, ev_node, EvidenceEdgeType.INSPECTION_HAS_EVALUATION)

        # Perception side: images → runs → regions/OCR → fields.
        self._add_perception_for_inspection(db, g, inspection_id)

        # Compliance side: findings of the chosen evaluation + their chains.
        if evaluation is not None:
            findings = list(
                db.execute(
                    select(EvaluationFinding)
                    .where(EvaluationFinding.evaluation_id == evaluation.id)
                    .order_by(EvaluationFinding.created_at.asc())
                    .limit(MAX_FINDINGS)
                )
                .scalars()
                .all()
            )
            for finding in findings:
                self._add_finding_chain(db, g, finding, ev_node, insp)
            if len(findings) == MAX_FINDINGS:
                g.truncated = True

            self._add_audit_events(db, g, inspection_id, evaluation=evaluation)

        return g.out(
            rootType=EvidenceNodeType.INSPECTION.value,
            rootId=str(inspection_id),
            inspectionId=str(inspection_id),
            evaluationId=str(evaluation.id) if evaluation else None,
        )

    def graph_for_finding(self, db: Session, finding_id: uuid.UUID) -> dict:
        """Focused graph for ONE finding: both halves of the chain.

        Finding → Rule → Requirement → Version → Document → Source, AND
        Finding → Field → OCR → Region → Image → Inspection (+ run, audit).
        """
        finding = db.get(EvaluationFinding, finding_id)
        if finding is None:
            raise NotFoundError(f"Finding not found: {finding_id}")
        evaluation = db.get(ComplianceEvaluation, finding.evaluation_id)
        inspection = db.get(Inspection, evaluation.inspection_id)

        g = _Graph()
        insp = self._add_inspection(g, inspection)
        ev_node = self._add_evaluation(g, evaluation)
        g.edge(insp, ev_node, EvidenceEdgeType.INSPECTION_HAS_EVALUATION)
        self._add_finding_chain(db, g, finding, ev_node, insp)

        # Audit trail specific to THIS finding (lifecycle events attach to the
        # evaluation node instead).
        events = list(
            db.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.entity_type == "compliance_evaluation",
                    AuditEvent.entity_id == evaluation.id,
                )
                .order_by(AuditEvent.created_at.asc())
                .limit(MAX_AUDIT_EVENTS)
            )
            .scalars()
            .all()
        )
        for event in events:
            payload = event.payload or {}
            target_fid = payload.get("findingId")
            if target_fid == str(finding.id):
                audit_node = self._add_audit_event(g, event)
                g.edge(audit_node, g.node(
                    EvidenceNodeType.FINDING, finding.id, ""
                ), EvidenceEdgeType.AUDIT_RECORDS_ACTION)

        return g.out(
            rootType=EvidenceNodeType.FINDING.value,
            rootId=str(finding_id),
            inspectionId=str(inspection.id),
            evaluationId=str(evaluation.id),
        )

    def graph_for_field(self, db: Session, field_id: uuid.UUID) -> dict:
        """Reverse-direction graph for ONE extracted field.

        Field → OCR → Region → Image → Inspection (+ run), AND every finding
        that used this field as evidence → requirement → version → source.
        """
        field = db.get(ExtractedField, field_id)
        if field is None:
            raise NotFoundError(f"Field not found: {field_id}")
        image = db.get(Image, field.image_id)
        inspection = (
            db.execute(
                select(Inspection)
                .join(Package, Package.inspection_id == Inspection.id)
                .where(Package.id == image.package_id)
            )
            .scalars()
            .first()
        )
        if inspection is None:  # pragma: no cover — defensive, FK integrity
            raise NotFoundError(f"Inspection for field not found: {field_id}")

        g = _Graph()
        insp = self._add_inspection(g, inspection)
        self._add_field_chain(db, g, field, insp)

        # Reverse: every finding whose evidence was this field.
        findings = list(
            db.execute(
                select(EvaluationFinding)
                .where(EvaluationFinding.extracted_field_id == field.id)
                .order_by(EvaluationFinding.created_at.asc())
                .limit(MAX_FIELD_FINDINGS)
            )
            .scalars()
            .all()
        )
        for finding in findings:
            evaluation = db.get(ComplianceEvaluation, finding.evaluation_id)
            ev_node = self._add_evaluation(g, evaluation)
            g.edge(insp, ev_node, EvidenceEdgeType.INSPECTION_HAS_EVALUATION)
            self._add_finding_chain(db, g, finding, ev_node, insp)
            # The explicit field → requirement relation (reverse traceability).
            requirement = db.get(Rule, finding.requirement_id)
            if requirement is not None:
                req_node = g.node(
                    EvidenceNodeType.REQUIREMENT, requirement.id, requirement.rule_code
                )
                field_node = g.node(
                    EvidenceNodeType.EXTRACTED_FIELD, field.id, ""
                )
                g.edge(
                    field_node,
                    req_node,
                    EvidenceEdgeType.FIELD_EVALUATED_AGAINST_REQUIREMENT,
                )
        if len(findings) == MAX_FIELD_FINDINGS:
            g.truncated = True

        return g.out(
            rootType=EvidenceNodeType.EXTRACTED_FIELD.value,
            rootId=str(field_id),
            inspectionId=str(inspection.id),
            evaluationId=str(findings[-1].evaluation_id) if findings else None,
        )

    @staticmethod
    def strength_vocabulary() -> list[dict[str, str]]:
        return [
            {
                "strength": s.value,
                "description": _STRENGTH_DESCRIPTIONS[s],
            }
            for s in EvidenceStrength
        ]

    # ------------------------------------------------------------ internals

    def _resolve_evaluation(
        self, db: Session, inspection_id: uuid.UUID, evaluation_id: uuid.UUID | None
    ) -> ComplianceEvaluation | None:
        if evaluation_id is not None:
            evaluation = (
                db.execute(
                    select(ComplianceEvaluation)
                    .where(
                        ComplianceEvaluation.id == evaluation_id,
                        ComplianceEvaluation.inspection_id == inspection_id,
                    )
                    .options(selectinload(ComplianceEvaluation.findings))
                )
                .scalars()
                .first()
            )
            if evaluation is None:
                raise NotFoundError(
                    f"Evaluation not found for inspection {inspection_id}: {evaluation_id}"
                )
            return evaluation
        return (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id == inspection_id)
                .options(selectinload(ComplianceEvaluation.findings))
                .order_by(ComplianceEvaluation.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def _add_perception_for_inspection(
        self, db: Session, g: _Graph, inspection_id: uuid.UUID
    ) -> None:
        images = list(
            db.execute(
                select(Image)
                .join(Package, Package.id == Image.package_id)
                .where(Package.inspection_id == inspection_id)
                .order_by(Image.created_at.asc())
            )
            .scalars()
            .all()
        )
        insp_node = g.node(EvidenceNodeType.INSPECTION, inspection_id, "")

        # Latest run per image (deterministic: newest created_at wins).
        latest_run_per_image: dict = {}
        for run_id, image_id in db.execute(
            select(ProcessingRun.id, ProcessingRun.image_id)
            .where(ProcessingRun.inspection_id == inspection_id)
            .order_by(ProcessingRun.created_at.desc())
        ):
            latest_run_per_image.setdefault(image_id, run_id)
        run_ids = list(latest_run_per_image.values())

        for image in images:
            img_node = self._add_image(g, image)
            g.edge(insp_node, img_node, EvidenceEdgeType.INSPECTION_CONTAINS_IMAGE)
            run_id = latest_run_per_image.get(image.id)
            if run_id is not None:
                run = db.get(ProcessingRun, run_id)
                run_node = self._add_run(g, run)
                g.edge(run_node, img_node, EvidenceEdgeType.PROCESSING_RUN_PROCESSED_IMAGE)

        if not run_ids:
            return

        regions = list(
            db.execute(
                select(ImageRegion)
                .where(ImageRegion.processing_run_id.in_(run_ids))
                .order_by(ImageRegion.created_at.asc())
            )
            .scalars()
            .all()
        )
        per_image: dict = {}
        for region in regions:
            per_image.setdefault(region.image_id, []).append(region)
        for image_id, image_regions in per_image.items():
            img_node = g.node(EvidenceNodeType.IMAGE, image_id, "")
            for region in image_regions[:MAX_REGIONS_PER_IMAGE]:
                reg_node = self._add_region(g, region)
                g.edge(img_node, reg_node, EvidenceEdgeType.IMAGE_HAS_REGION)
                run_id = region.processing_run_id
                if run_id is not None and g.has_node(
                    EvidenceNodeType.PROCESSING_RUN, run_id
                ):
                    g.edge(
                        g.node(EvidenceNodeType.PROCESSING_RUN, run_id, ""),
                        reg_node,
                        EvidenceEdgeType.PROCESSING_RUN_PRODUCED_REGION,
                    )
            if len(image_regions) > MAX_REGIONS_PER_IMAGE:
                g.truncated = True

        ocr_per_image: dict = {}
        for ocr in db.execute(
            select(OcrTextResult)
            .where(OcrTextResult.processing_run_id.in_(run_ids))
            .order_by(OcrTextResult.created_at.asc())
        ).scalars():
            ocr_per_image.setdefault(ocr.image_id, []).append(ocr)
        for image_id, lines in ocr_per_image.items():
            img_node = g.node(EvidenceNodeType.IMAGE, image_id, "")
            for ocr in lines[:MAX_OCR_PER_IMAGE]:
                ocr_node = self._add_ocr(g, ocr)
                g.edge(img_node, ocr_node, EvidenceEdgeType.IMAGE_HAS_OCR_RESULT)
                if ocr.region_id is not None and g.has_node(
                    EvidenceNodeType.IMAGE_REGION, ocr.region_id
                ):
                    g.edge(
                        g.node(EvidenceNodeType.IMAGE_REGION, ocr.region_id, ""),
                        ocr_node,
                        EvidenceEdgeType.REGION_HAS_OCR_RESULT,
                    )
                if g.has_node(EvidenceNodeType.PROCESSING_RUN, ocr.processing_run_id):
                    g.edge(
                        g.node(EvidenceNodeType.PROCESSING_RUN, ocr.processing_run_id, ""),
                        ocr_node,
                        EvidenceEdgeType.PROCESSING_RUN_PRODUCED_OCR,
                    )
            if len(lines) > MAX_OCR_PER_IMAGE:
                g.truncated = True

        fields = list(
            db.execute(
                select(ExtractedField)
                .where(ExtractedField.processing_run_id.in_(run_ids))
                .order_by(ExtractedField.created_at.asc())
            )
            .scalars()
            .all()
        )
        for field in fields:
            field_node = self._add_field(g, field)
            ocr = (
                db.get(OcrTextResult, field.source_ocr_result_id)
                if field.source_ocr_result_id
                else None
            )
            if ocr is not None:
                ocr_node = self._add_ocr(g, ocr)
                g.edge(ocr_node, field_node, EvidenceEdgeType.OCR_SUPPORTS_FIELD)
            elif field.image_region_id is not None and g.has_node(
                EvidenceNodeType.IMAGE_REGION, field.image_region_id
            ):
                g.edge(
                    g.node(EvidenceNodeType.IMAGE_REGION, field.image_region_id, ""),
                    field_node,
                    EvidenceEdgeType.REGION_SUPPORTS_FIELD,
                )

    def _add_finding_chain(
        self,
        db: Session,
        g: _Graph,
        finding: EvaluationFinding,
        ev_node: str | None,
        insp_node: str | None,
    ) -> None:
        """One finding with BOTH halves of its chain (regulatory + evidence)."""
        field = (
            db.get(ExtractedField, finding.extracted_field_id)
            if finding.extracted_field_id
            else None
        )
        strength = evidence_strength(finding, field)
        finding_node = self._add_finding(g, finding, strength)
        g.edge(finding_node, ev_node, EvidenceEdgeType.FINDING_BELONGS_TO_EVALUATION)

        # --- regulatory half: requirement → version → document → source ------
        requirement = db.get(Rule, finding.requirement_id)
        if requirement is not None:
            req_node = self._add_requirement(g, requirement)
            version = db.get(RegulationVersion, requirement.regulation_version_id)
            if version is not None:
                ver_node = self._add_version(g, version)
                g.edge(req_node, ver_node, EvidenceEdgeType.REQUIREMENT_BELONGS_TO_VERSION)
                document = db.get(Regulation, version.regulation_id)
                if document is not None:
                    doc_node = self._add_document(g, document)
                    g.edge(
                        ver_node, doc_node, EvidenceEdgeType.VERSION_ORIGINATES_FROM_DOCUMENT
                    )
                    if document.source_id is not None:
                        source = db.get(RegulatorySource, document.source_id)
                        if source is not None:
                            src_node = self._add_source(g, source)
                            g.edge(doc_node, src_node, EvidenceEdgeType.DOCUMENT_HAS_SOURCE)
            # The evaluation's regulatory version is the frozen/historical one
            # recorded on the evaluation row itself.
            if ev_node is not None and finding.evaluation.regulatory_version_id:
                ver_node = g.node(
                    EvidenceNodeType.REGULATORY_VERSION,
                    finding.evaluation.regulatory_version_id,
                    "",
                )
                g.edge(
                    ev_node, ver_node, EvidenceEdgeType.EVALUATION_USES_REGULATORY_VERSION
                )

        # --- deterministic rules ------------------------------------------------
        # The engine records a single rule_id only when exactly one rule was
        # bound; multi-rule findings carry the executed rule codes in
        # detail["rules"]. Both paths resolve to REAL ComplianceRule rows.
        compliance_rules: list[ComplianceRule] = []
        if finding.rule_id is not None:
            row = db.get(ComplianceRule, finding.rule_id)
            if row is not None:
                compliance_rules.append(row)
        else:
            codes = [
                outcome.get("ruleCode")
                for outcome in (finding.detail or {}).get("rules", [])
                if outcome.get("ruleCode")
            ]
            if codes:
                compliance_rules = list(
                    db.execute(
                        select(ComplianceRule)
                        .where(
                            ComplianceRule.requirement_id == finding.requirement_id,
                            ComplianceRule.rule_code.in_(codes),
                        )
                        .order_by(ComplianceRule.rule_code.asc())
                    )
                    .scalars()
                    .all()
                )
        for compliance_rule in compliance_rules:
            rule_node = self._add_rule(g, compliance_rule)
            g.edge(rule_node, finding_node, EvidenceEdgeType.RULE_PRODUCED_FINDING)
            if requirement is not None:
                req_node = g.node(
                    EvidenceNodeType.REQUIREMENT, requirement.id, requirement.rule_code
                )
                g.edge(
                    req_node, rule_node, EvidenceEdgeType.REQUIREMENT_EVALUATED_BY_RULE
                )

        # --- evidence half: field → OCR → region → image → inspection ---------
        if field is not None:
            field_node = self._add_field(g, field)
            g.edge(
                finding_node,
                field_node,
                EvidenceEdgeType.FINDING_SUPPORTED_BY_EVIDENCE,
                {"strength": strength},
            )
            self._add_field_chain(db, g, field, insp_node)
        elif finding.evidence_region_id is not None:
            # A region exists without a usable field (e.g. value not read).
            region = db.get(ImageRegion, finding.evidence_region_id)
            if region is not None:
                reg_node = self._add_region(g, region)
                g.edge(
                    finding_node,
                    reg_node,
                    EvidenceEdgeType.FINDING_SUPPORTED_BY_EVIDENCE,
                    {"strength": EvidenceStrength.DIRECT.value},
                )
                image = db.get(Image, region.image_id)
                if image is not None:
                    img_node = self._add_image(g, image)
                    g.edge(img_node, reg_node, EvidenceEdgeType.IMAGE_HAS_REGION)
                    if insp_node is not None:
                        g.edge(
                            insp_node, img_node, EvidenceEdgeType.INSPECTION_CONTAINS_IMAGE
                        )

    def _add_field_chain(
        self, db: Session, g: _Graph, field: ExtractedField, insp_node: str | None
    ) -> None:
        """Field → OCR → region → image (+ processing run) evidence chain."""
        field_node = self._add_field(g, field)
        ocr = (
            db.get(OcrTextResult, field.source_ocr_result_id)
            if field.source_ocr_result_id
            else None
        )
        region = None
        if ocr is not None and ocr.region_id is not None:
            region = db.get(ImageRegion, ocr.region_id)
        elif field.image_region_id is not None:
            region = db.get(ImageRegion, field.image_region_id)

        if ocr is not None:
            ocr_node = self._add_ocr(g, ocr)
            g.edge(ocr_node, field_node, EvidenceEdgeType.OCR_SUPPORTS_FIELD)
            if region is not None:
                reg_node = self._add_region(g, region)
                g.edge(reg_node, ocr_node, EvidenceEdgeType.REGION_HAS_OCR_RESULT)

        if region is not None:
            reg_node = self._add_region(g, region)
            if ocr is None:
                g.edge(reg_node, field_node, EvidenceEdgeType.REGION_SUPPORTS_FIELD)
            image = db.get(Image, region.image_id)
        else:
            image = db.get(Image, field.image_id)

        if image is not None:
            img_node = self._add_image(g, image)
            if region is not None:
                reg_node = g.node(EvidenceNodeType.IMAGE_REGION, region.id, "")
                g.edge(img_node, reg_node, EvidenceEdgeType.IMAGE_HAS_REGION)
            if insp_node is not None:
                g.edge(insp_node, img_node, EvidenceEdgeType.INSPECTION_CONTAINS_IMAGE)

        run_id = None
        if ocr is not None:
            run_id = ocr.processing_run_id
        elif field.processing_run_id is not None:
            run_id = field.processing_run_id
        if run_id is not None:
            run = db.get(ProcessingRun, run_id)
            run_node = self._add_run(g, run)
            if ocr is not None:
                g.edge(
                    run_node,
                    g.node(EvidenceNodeType.OCR_RESULT, ocr.id, ""),
                    EvidenceEdgeType.PROCESSING_RUN_PRODUCED_OCR,
                )
            if region is not None:
                g.edge(
                    run_node,
                    g.node(EvidenceNodeType.IMAGE_REGION, region.id, ""),
                    EvidenceEdgeType.PROCESSING_RUN_PRODUCED_REGION,
                )
            if image is not None:
                g.edge(
                    run_node,
                    g.node(EvidenceNodeType.IMAGE, image.id, ""),
                    EvidenceEdgeType.PROCESSING_RUN_PROCESSED_IMAGE,
                )

    def _add_audit_events(
        self,
        db: Session,
        g: _Graph,
        inspection_id: uuid.UUID,
        *,
        evaluation: ComplianceEvaluation,
    ) -> None:
        """Inspection-level audit overlay: evaluation + finding events."""
        events = list(
            db.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.inspection_id == inspection_id,
                    AuditEvent.entity_type == "compliance_evaluation",
                )
                .order_by(AuditEvent.created_at.asc())
                .limit(MAX_AUDIT_EVENTS)
            )
            .scalars()
            .all()
        )
        if len(events) == MAX_AUDIT_EVENTS:
            g.truncated = True
        ev_node = g.node(EvidenceNodeType.EVALUATION, evaluation.id, "")
        for event in events:
            audit_node = self._add_audit_event(g, event)
            payload = event.payload or {}
            target_fid = payload.get("findingId")
            if target_fid and g.has_node(EvidenceNodeType.FINDING, target_fid):
                g.edge(
                    audit_node,
                    g.node(EvidenceNodeType.FINDING, target_fid, ""),
                    EvidenceEdgeType.AUDIT_RECORDS_ACTION,
                )
            else:
                g.edge(audit_node, ev_node, EvidenceEdgeType.AUDIT_RECORDS_ACTION)

    # ------------------------------------------------------- node factories

    def _add_inspection(self, g: _Graph, inspection: Inspection) -> str | None:
        return g.node(
            EvidenceNodeType.INSPECTION,
            inspection.id,
            inspection.reference_no,
            {
                "referenceNo": inspection.reference_no,
                "status": inspection.status,
                "contextDate": _iso(inspection.context_date),
                "createdAt": _iso(inspection.created_at),
                "isDemo": inspection.is_demo,
            },
        )

    def _add_image(self, g: _Graph, image: Image) -> str | None:
        return g.node(
            EvidenceNodeType.IMAGE,
            image.id,
            image.original_filename or image.image_type,
            {
                "imageId": str(image.id),
                "filename": image.original_filename,
                "imageType": image.image_type,
                "captureSource": image.capture_source,
                "processingStatus": image.processing_status,
                "qualityGrade": image.quality_grade,
                "width": image.width,
                "height": image.height,
                "checksum": (image.checksum[:16] + "…") if image.checksum else None,
                "createdAt": _iso(image.created_at),
            },
        )

    def _add_region(self, g: _Graph, region: ImageRegion) -> str | None:
        return g.node(
            EvidenceNodeType.IMAGE_REGION,
            region.id,
            f"{region.region_type} region",
            {
                "regionId": str(region.id),
                "regionType": region.region_type,
                "bbox": region.bbox,
                "confidence": region.confidence,
                "payload": region.payload,
                "imageId": str(region.image_id),
            },
        )

    def _add_ocr(self, g: _Graph, ocr: OcrTextResult) -> str | None:
        return g.node(
            EvidenceNodeType.OCR_RESULT,
            ocr.id,
            _short(ocr.raw_text) or "OCR line",
            {
                "ocrId": str(ocr.id),
                "rawText": ocr.raw_text,
                "normalizedText": ocr.normalized_text,
                "bbox": ocr.bbox,
                "confidence": ocr.confidence,
                "language": ocr.language,
                "provider": ocr.provider,
                "modelName": ocr.model_name,
                "modelVersion": ocr.model_version,
                "processingRunId": str(ocr.processing_run_id),
                "imageId": str(ocr.image_id),
            },
        )

    def _add_field(self, g: _Graph, field: ExtractedField) -> str | None:
        value = field.normalized_value or field.raw_text
        return g.node(
            EvidenceNodeType.EXTRACTED_FIELD,
            field.id,
            f"{field.field_type}: {_short(value, 32)}",
            {
                "fieldId": str(field.id),
                "fieldType": field.field_type,
                "rawText": field.raw_text,
                "normalizedValue": field.normalized_value,
                "unit": field.unit,
                "confidence": field.confidence,
                "status": field.status,
                "extractionMethod": field.extraction_method,
                "imageRegionId": str(field.image_region_id) if field.image_region_id else None,
                "sourceOcrResultId": (
                    str(field.source_ocr_result_id) if field.source_ocr_result_id else None
                ),
                "processingRunId": (
                    str(field.processing_run_id) if field.processing_run_id else None
                ),
                "createdAt": _iso(field.created_at),
            },
        )

    def _add_requirement(self, g: _Graph, requirement: Rule) -> str | None:
        return g.node(
            EvidenceNodeType.REQUIREMENT,
            requirement.id,
            requirement.rule_code,
            {
                "requirementId": str(requirement.id),
                "ruleCode": requirement.rule_code,
                "title": requirement.title,
                "requirementSummary": requirement.requirement_summary,
                "requirementType": requirement.requirement_type,
                "fieldKey": requirement.field_key,
                "mandatory": requirement.mandatory,
                "sourceReference": requirement.source_reference,
                "versionId": str(requirement.regulation_version_id),
                "isDemo": requirement.is_demo,
            },
        )

    def _add_rule(self, g: _Graph, rule) -> str | None:
        return g.node(
            EvidenceNodeType.RULE,
            rule.id,
            _short(rule.rule_code),
            {
                "ruleId": str(rule.id),
                "ruleCode": rule.rule_code,
                "ruleType": rule.rule_type,
                "ruleVersion": rule.rule_version,
                "active": rule.active,
                "description": rule.description,
            },
        )

    def _add_version(self, g: _Graph, version: RegulationVersion) -> str | None:
        return g.node(
            EvidenceNodeType.REGULATORY_VERSION,
            version.id,
            version.version_label,
            {
                "versionId": str(version.id),
                "versionLabel": version.version_label,
                "status": version.status,
                "effectiveFrom": _iso(version.effective_from),
                "effectiveUntil": _iso(version.effective_until),
                "publicationDate": _iso(version.publication_date),
                "documentId": str(version.regulation_id),
                "isDemo": version.is_demo,
            },
        )

    def _add_document(self, g: _Graph, document: Regulation) -> str | None:
        return g.node(
            EvidenceNodeType.REGULATORY_DOCUMENT,
            document.id,
            _short(document.title, 56) or document.code,
            {
                "documentId": str(document.id),
                "code": document.code,
                "title": document.title,
                "documentIdentifier": document.document_identifier,
                "documentType": document.document_type,
                "publicationDate": _iso(document.publication_date),
                "officialSourceUrl": document.official_source_url,
                "sourceId": str(document.source_id) if document.source_id else None,
                "isDemo": document.is_demo,
            },
        )

    def _add_source(self, g: _Graph, source: RegulatorySource) -> str | None:
        return g.node(
            EvidenceNodeType.REGULATORY_SOURCE,
            source.id,
            source.name,
            {
                "sourceId": str(source.id),
                "name": source.name,
                "authority": source.authority,
                "sourceType": source.source_type,
                "jurisdiction": source.jurisdiction,
                "verificationStatus": source.verification_status,
                "canonicalUrl": source.canonical_url,
            },
        )

    def _add_evaluation(self, g: _Graph, evaluation: ComplianceEvaluation) -> str | None:
        return g.node(
            EvidenceNodeType.EVALUATION,
            evaluation.id,
            f"Evaluation · {evaluation.status}",
            {
                "evaluationId": str(evaluation.id),
                "status": evaluation.status,
                "engineVersion": evaluation.engine_version,
                "contextDate": _iso(evaluation.context_date),
                "startedAt": _iso(evaluation.started_at),
                "completedAt": _iso(evaluation.completed_at),
                "regulatoryVersionId": (
                    str(evaluation.regulatory_version_id)
                    if evaluation.regulatory_version_id
                    else None
                ),
                "summary": evaluation.summary,
            },
        )

    def _add_finding(
        self, g: _Graph, finding: EvaluationFinding, strength: str | None = None
    ) -> str | None:
        code = (finding.provenance or {}).get("requirementCode") or "Requirement"
        return g.node(
            EvidenceNodeType.FINDING,
            finding.id,
            f"{code}: {finding.status}",
            {
                "findingId": str(finding.id),
                "status": finding.status,
                "severity": finding.severity,
                "applicability": finding.applicability,
                "detectedValue": finding.detected_value,
                "expectedValue": finding.expected_value,
                "explanation": finding.explanation,
                "evidenceStrength": strength,
                "absence": (finding.detail or {}).get("absence"),
                "evaluationId": str(finding.evaluation_id),
                "requirementId": str(finding.requirement_id),
                "ruleId": str(finding.rule_id) if finding.rule_id else None,
                "extractedFieldId": (
                    str(finding.extracted_field_id) if finding.extracted_field_id else None
                ),
                "evidenceRegionId": (
                    str(finding.evidence_region_id) if finding.evidence_region_id else None
                ),
                "createdAt": _iso(finding.created_at),
            },
        )

    def _add_run(self, g: _Graph, run: ProcessingRun) -> str | None:
        return g.node(
            EvidenceNodeType.PROCESSING_RUN,
            run.id,
            run.reference,
            {
                "runId": str(run.id),
                "reference": run.reference,
                "status": run.status,
                "pipelineVersion": run.pipeline_version,
                "ocrProvider": run.ocr_provider,
                "ocrModel": run.ocr_model,
                "ocrVersion": run.ocr_version,
                "visionProvider": run.vision_provider,
                "visionModel": run.vision_model,
                "visionVersion": run.vision_version,
                "durationMs": run.duration_ms,
                "startedAt": _iso(run.started_at),
                "completedAt": _iso(run.completed_at),
            },
        )

    def _add_audit_event(self, g: _Graph, event: AuditEvent) -> str | None:
        return g.node(
            EvidenceNodeType.AUDIT_EVENT,
            event.id,
            event.event_type,
            {
                "eventId": str(event.id),
                "eventType": event.event_type,
                "entityType": event.entity_type,
                "entityId": str(event.entity_id) if event.entity_id else None,
                "actorId": str(event.actor_id) if event.actor_id else None,
                "payload": event.payload,
                "createdAt": _iso(event.created_at),
            },
        )


_STRENGTH_DESCRIPTIONS = {
    EvidenceStrength.DIRECT: (
        "The finding has direct evidence from an image region / OCR line."
    ),
    EvidenceStrength.DERIVED: (
        "The value was deterministically normalized/derived from source data."
    ),
    EvidenceStrength.AMBIGUOUS: (
        "Evidence exists but is insufficient to confidently establish the "
        "required relationship — never treated as compliance."
    ),
    EvidenceStrength.MISSING: (
        "No valid evidence exists. Missing evidence is never converted into "
        "legal non-compliance."
    ),
}
