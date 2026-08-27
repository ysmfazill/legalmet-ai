"""Evidence service — makes every finding answer "Why?".

Two responsibilities:

1. :meth:`create_for_finding` — persist the evidence rows that back a finding.
   The system-wide invariant is that **no finding exists without at least one
   evidence row**; this method guarantees that by always writing a
   VALIDATION_RESULT row plus rows for each matched field and the rule
   reference.
2. :meth:`build_graph` — assemble the Evidence Graph
   (inspection → package → image → region → field → evidence → finding →
   rule/version, plus review actions) that powers the Evidence Viewer.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EvidenceType
from app.core.errors import NotFoundError
from app.models import ComplianceFinding, Evidence, ExtractedField
from app.schemas.evidence_graph import EvidenceGraph, EvidenceGraphEdge, EvidenceGraphNode


class EvidenceService:
    def create_for_finding(
        self,
        db: Session,
        *,
        finding: ComplianceFinding,
        matched_field_ids: list[UUID],
        fallback_image_id: UUID | None,
        rule_code: str | None,
        validator_output: dict,
    ) -> list[Evidence]:
        evidence: list[Evidence] = []

        fields: list[ExtractedField] = []
        if matched_field_ids:
            stmt = select(ExtractedField).where(ExtractedField.id.in_(matched_field_ids))
            fields = list(db.execute(stmt).scalars().all())

        for fld in fields:
            evidence.append(
                Evidence(
                    finding_id=finding.id,
                    evidence_type=EvidenceType.EXTRACTED_FIELD.value,
                    image_id=fld.image_id,
                    image_region_id=fld.image_region_id,
                    extracted_field_id=fld.id,
                    data={
                        "fieldType": fld.field_type,
                        "value": fld.normalized_value or fld.raw_text,
                        "confidence": fld.confidence,
                    },
                )
            )

        if finding.rule_id is not None:
            evidence.append(
                Evidence(
                    finding_id=finding.id,
                    evidence_type=EvidenceType.RULE_REFERENCE.value,
                    rule_id=finding.rule_id,
                    data={"ruleCode": rule_code, "ruleVersionId": str(finding.rule_version_id)
                          if finding.rule_version_id else None},
                )
            )

        # Always present -> guarantees the "at least one evidence" invariant even
        # when nothing was matched (e.g. a missing-declaration finding). Anchored
        # to an image so the graph still reaches the visual source.
        image_for_result = fields[0].image_id if fields else fallback_image_id
        evidence.append(
            Evidence(
                finding_id=finding.id,
                evidence_type=EvidenceType.VALIDATION_RESULT.value,
                image_id=image_for_result,
                data=validator_output or {},
            )
        )

        db.add_all(evidence)
        db.flush()
        return evidence

    def build_graph(self, db: Session, finding_id: UUID) -> EvidenceGraph:
        finding = db.get(ComplianceFinding, finding_id)
        if finding is None:
            raise NotFoundError(f"Finding not found: {finding_id}")

        nodes: dict[str, EvidenceGraphNode] = {}
        edges: list[EvidenceGraphEdge] = []

        def node(nid: str, ntype: str, label: str, data: dict | None = None) -> str:
            if nid not in nodes:
                nodes[nid] = EvidenceGraphNode(id=nid, type=ntype, label=label, data=data)
            return nid

        def edge(src: str, dst: str, relation: str) -> None:
            edges.append(EvidenceGraphEdge.model_validate({"from": src, "to": dst, "relation": relation}))

        # Core spine: inspection -> package -> finding.
        insp_id = node(f"inspection:{finding.inspection_id}", "INSPECTION", "Inspection")
        pkg_id = node(f"package:{finding.package_id}", "PACKAGE", "Package")
        finding_node = node(
            f"finding:{finding.id}",
            "FINDING",
            f"{finding.status}",
            {"status": finding.status, "confidence": finding.confidence,
             "fieldType": finding.field_type, "isReviewed": finding.is_reviewed,
             "reviewStatus": finding.review_status},
        )
        edge(pkg_id, insp_id, "IN_INSPECTION")
        edge(finding_node, pkg_id, "OF_PACKAGE")

        # Rule / version provenance.
        if finding.rule is not None:
            rule_id = node(
                f"rule:{finding.rule.id}", "RULE",
                finding.rule.rule_code,
                {"requirement": finding.rule.requirement_summary,
                 "validator": finding.rule.validation_logic_ref},
            )
            edge(finding_node, rule_id, "BASED_ON_RULE")
            if finding.rule_version is not None:
                ver = finding.rule_version
                ver_id = node(
                    f"rule_version:{ver.id}", "RULE_VERSION",
                    ver.version_label,
                    {"status": ver.status, "effectiveFrom": ver.effective_from.isoformat()
                     if ver.effective_from else None},
                )
                edge(rule_id, ver_id, "VERSION")

        # Evidence rows and the artifacts they point at.
        for ev in finding.evidence:
            ev_node = node(
                f"evidence:{ev.id}", "EVIDENCE",
                ev.evidence_type,
                {"data": ev.data},
            )
            edge(finding_node, ev_node, "SUPPORTED_BY")

            if ev.extracted_field_id is not None and ev.extracted_field is not None:
                fld = ev.extracted_field
                fld_node = node(
                    f"field:{fld.id}", "EXTRACTED_FIELD",
                    f"{fld.field_type}: {fld.normalized_value or fld.raw_text}",
                    {"confidence": fld.confidence, "rawText": fld.raw_text},
                )
                edge(ev_node, fld_node, "REFERENCES")
                if fld.image_region_id is not None:
                    reg_node = node(f"region:{fld.image_region_id}", "IMAGE_REGION", "Region")
                    edge(fld_node, reg_node, "EXTRACTED_FROM")
                    if fld.image_id is not None:
                        img_node = node(f"image:{fld.image_id}", "IMAGE", "Image")
                        edge(reg_node, img_node, "IN_IMAGE")
                        edge(img_node, pkg_id, "OF_PACKAGE")

            if ev.image_id is not None:
                img_node = node(f"image:{ev.image_id}", "IMAGE", "Image")
                edge(ev_node, img_node, "FROM_IMAGE")
                edge(img_node, pkg_id, "OF_PACKAGE")
            if ev.image_region_id is not None:
                reg_node = node(f"region:{ev.image_region_id}", "IMAGE_REGION", "Region")
                edge(ev_node, reg_node, "LOCATED_AT")

        # Human-in-the-loop overlay.
        for action in finding.review_actions:
            act_node = node(
                f"review:{action.id}", "REVIEW_ACTION",
                action.action,
                {"correctedStatus": action.corrected_status, "reason": action.reason},
            )
            edge(act_node, finding_node, "REVIEWS")

        return EvidenceGraph(
            finding_id=finding.id,
            nodes=list(nodes.values()),
            edges=edges,
        )
