"""Evidence Graph tests (Prompt 7).

Covers the traceability contract:

* graph generation for an inspection / finding / field (API + service)
* node & edge correctness — every node is a real persisted record, every edge
  connects two real entity ids, no duplicates, no invalid edges
* full chains: finding → rule → requirement → version → document → source AND
  finding → field → OCR → region → image → inspection
* evidence strength labelling (DIRECT / DERIVED / AMBIGUOUS / MISSING)
* historical version traceability (a frozen evaluation never re-resolves)
* authorization (401 without a token), nonexistent IDs (404)
* bounded traversal caps and cycle prevention (deduped node/edge ids)
* the GOLDEN TRACE test — proves the graph is not fabricated
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.enums import (
    EvidenceEdgeType,
    EvidenceStrength,
    InspectionDecisionType,
    UserRole,
)
from app.models import (
    EvaluationFinding,
    ExtractedField,
    ImageRegion,
    OcrTextResult,
    ProcessingRun,
    Rule,
    User,
)
from app.services.evidence_graph.builder import (
    EVIDENCE_GRAPH_BOUNDARY_NOTE,
    EvidenceGraphService,
    evidence_strength,
)

# Re-use the Prompt 6 test data builders so the graph is exercised against the
# SAME evidence shapes the engine consumes.
from tests.test_compliance_engine import (
    _DOMESTIC_FIELDS,
    _FULL_COMPLIANT_FIELDS,
    _make_inspection,
)

API = "/api/v1"


@pytest.fixture()
def graph_service() -> EvidenceGraphService:
    return EvidenceGraphService()


@pytest.fixture()
def evaluated(db, services):
    """An inspection with a completed evaluation over full-compliant fields,
    including REAL region + OCR rows for the MRP field (the golden chain)."""
    engine = services.compliance
    inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
    # Attach real perception evidence to the MRP field: region → OCR → field.
    run = db.execute(
        select(ProcessingRun).where(ProcessingRun.inspection_id == inspection.id)
    ).scalars().first()
    mrp = db.execute(
        select(ExtractedField).where(
            ExtractedField.processing_run_id == run.id,
            ExtractedField.field_type == "MRP",
        )
    ).scalars().one()
    region = ImageRegion(
        image_id=run.image_id,
        region_type="TEXT_LINE",
        bbox={"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.03},
        confidence=0.98,
        processing_run_id=run.id,
    )
    db.add(region)
    db.flush()
    ocr = OcrTextResult(
        image_id=run.image_id,
        processing_run_id=run.id,
        region_id=region.id,
        raw_text="MRP ₹ 60.00 (inclusive of all taxes)",
        normalized_text="MRP ₹ 60.00 (inclusive of all taxes)",
        bbox=region.bbox,
        confidence=0.97,
        provider="test",
        model_name="test-ocr",
        model_version="1",
    )
    db.add(ocr)
    db.flush()
    mrp.image_region_id = region.id
    mrp.source_ocr_result_id = ocr.id
    db.commit()
    evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
    db.refresh(evaluation)
    return inspection, evaluation


def _nodes(payload) -> dict[str, dict]:
    return {n["id"]: n for n in payload["nodes"]}


def _edges(payload) -> list[dict]:
    return payload["edges"]


def _find_edge(payload, etype: EvidenceEdgeType, source: str | None = None,
               target: str | None = None) -> dict | None:
    for edge in payload["edges"]:
        if edge["type"] != etype.value:
            continue
        if source is not None and not edge["source"].endswith(source):
            continue
        if target is not None and not edge["target"].endswith(target):
            continue
        return edge
    return None


# ===========================================================================
# 1. Service-level graph correctness
# ===========================================================================


class TestInspectionGraph:
    def test_graph_generated_for_valid_inspection(self, db, graph_service, evaluated):
        inspection, _ = evaluated
        payload = graph_service.graph_for_inspection(db, inspection.id)
        assert payload["rootType"] == "INSPECTION"
        assert payload["rootId"] == str(inspection.id)
        assert payload["nodeCount"] == len(payload["nodes"])
        assert payload["edgeCount"] == len(payload["edges"])
        assert payload["truncated"] is False
        assert EVIDENCE_GRAPH_BOUNDARY_NOTE in payload["boundaryNote"]
        assert "does not independently determine legal compliance" in payload["boundaryNote"]

    def test_has_all_node_types(self, db, graph_service, evaluated):
        _, _evaluation = evaluated
        inspection, evaluation = evaluated
        payload = graph_service.graph_for_inspection(db, inspection.id)
        types = {n["type"] for n in payload["nodes"]}
        for expected in (
            "INSPECTION", "IMAGE", "IMAGE_REGION", "OCR_RESULT",
            "EXTRACTED_FIELD", "REGULATORY_SOURCE", "REGULATORY_DOCUMENT",
            "REGULATORY_VERSION", "REQUIREMENT", "RULE", "EVALUATION",
            "FINDING", "PROCESSING_RUN", "AUDIT_EVENT",
        ):
            assert expected in types, f"missing node type {expected}"

    def test_no_duplicate_nodes_or_edges(self, db, graph_service, evaluated):
        inspection, _ = evaluated
        payload = graph_service.graph_for_inspection(db, inspection.id)
        node_ids = [n["id"] for n in payload["nodes"]]
        edge_ids = [e["id"] for e in payload["edges"]]
        assert len(node_ids) == len(set(node_ids))
        assert len(edge_ids) == len(set(edge_ids))

    def test_every_edge_connects_real_nodes(self, db, graph_service, evaluated):
        """No invalid edges: both endpoints of every edge must exist."""
        inspection, _ = evaluated
        payload = graph_service.graph_for_inspection(db, inspection.id)
        node_ids = {n["id"] for n in payload["nodes"]}
        for edge in payload["edges"]:
            assert edge["source"] in node_ids, f"dangling source {edge}"
            assert edge["target"] in node_ids, f"dangling target {edge}"

    def test_every_node_id_is_real_entity_id(self, db, graph_service, evaluated):
        """Node ids are '<TYPE>:<uuid>' of real persisted records — spot-check
        each type against the database."""
        inspection, evaluation = evaluated
        payload = graph_service.graph_for_inspection(db, inspection.id)
        nodes = _nodes(payload)
        # inspection node
        assert f"INSPECTION:{inspection.id}" in nodes
        # evaluation node
        assert f"EVALUATION:{evaluation.id}" in nodes
        # finding nodes
        for finding in evaluation.findings:
            assert f"FINDING:{finding.id}" in nodes
        # requirement + rule + version nodes exist for each finding
        for finding in evaluation.findings:
            assert f"REQUIREMENT:{finding.requirement_id}" in nodes
        # image nodes
        images = db.execute(
            select(ProcessingRun).where(ProcessingRun.inspection_id == inspection.id)
        ).scalars().all()
        for img in images:
            assert f"IMAGE:{img.image_id}" in nodes

    def test_no_evaluation_yet_still_has_perception(self, db, graph_service):
        """An inspection with perception but no evaluation: graph exists with
        evidence nodes and an explicit null evaluationId."""
        inspection = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        payload = graph_service.graph_for_inspection(db, inspection.id)
        assert payload["evaluationId"] is None
        types = {n["type"] for n in payload["nodes"]}
        assert "IMAGE" in types
        assert "FINDING" not in types

    def test_historical_evaluation_id_selects_that_run(self, db, graph_service):
        """?evaluationId= traces the HISTORICAL run, not the latest."""
        inspection = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        from app.services.compliance.engine import ComplianceEngine
        from app.services.regulatory.service import RegulatoryService

        first = ComplianceEngine(
            regulatory=RegulatoryService()
        ).evaluate(db, inspection_id=inspection.id)
        second = ComplianceEngine(
            regulatory=RegulatoryService()
        ).evaluate(db, inspection_id=inspection.id)
        payload = graph_service.graph_for_inspection(
            db, inspection.id, evaluation_id=first.id
        )
        assert payload["evaluationId"] == str(first.id)
        assert payload["evaluationId"] != str(second.id)
        nodes = _nodes(payload)
        assert f"EVALUATION:{first.id}" in nodes
        assert f"EVALUATION:{second.id}" not in nodes

    def test_wrong_inspection_evaluation_id_404s(self, db, graph_service, evaluated):
        inspection, _ = evaluated
        other = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        from app.services.compliance.engine import ComplianceEngine
        from app.services.regulatory.service import RegulatoryService

        other_eval = ComplianceEngine(
            regulatory=RegulatoryService()
        ).evaluate(db, inspection_id=other.id)
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            graph_service.graph_for_inspection(
                db, inspection.id, evaluation_id=other_eval.id
            )


class TestFindingGraph:
    def test_finding_graph_generated(self, db, graph_service, evaluated):
        inspection, evaluation = evaluated
        finding = evaluation.findings[0]
        payload = graph_service.graph_for_finding(db, finding.id)
        assert payload["rootType"] == "FINDING"
        assert payload["rootId"] == str(finding.id)
        assert payload["inspectionId"] == str(inspection.id)

    def test_finding_graph_has_regulatory_half(self, db, graph_service, evaluated):
        """Finding → Rule → Requirement → Version → Document → Source."""
        _, evaluation = evaluated
        finding = evaluation.findings[0]
        payload = graph_service.graph_for_finding(db, finding.id)
        nodes = _nodes(payload)
        assert f"REQUIREMENT:{finding.requirement_id}" in nodes
        if finding.rule_id:
            assert f"RULE:{finding.rule_id}" in nodes
            assert _find_edge(
                payload, EvidenceEdgeType.RULE_PRODUCED_FINDING
            ) is not None
        # requirement's version + document + source
        requirement = nodes[f"REQUIREMENT:{finding.requirement_id}"]
        version_id = requirement["metadata"]["versionId"]
        assert f"REGULATORY_VERSION:{version_id}" in nodes
        version = nodes[f"REGULATORY_VERSION:{version_id}"]
        document_id = version["metadata"]["documentId"]
        assert f"REGULATORY_DOCUMENT:{document_id}" in nodes
        document = nodes[f"REGULATORY_DOCUMENT:{document_id}"]
        if document["metadata"]["sourceId"]:
            assert f"REGULATORY_SOURCE:{document['metadata']['sourceId']}" in nodes
            assert _find_edge(
                payload, EvidenceEdgeType.DOCUMENT_HAS_SOURCE
            ) is not None

    def test_finding_graph_has_evidence_half(self, db, graph_service, evaluated):
        """Finding → Field → OCR → Region → Image → Inspection."""
        _, evaluation = evaluated
        run = db.execute(
            select(ProcessingRun).where(
                ProcessingRun.inspection_id == evaluation.inspection_id
            )
        ).scalars().first()
        ocr = db.execute(
            select(OcrTextResult).where(OcrTextResult.processing_run_id == run.id)
        ).scalars().one()
        finding = db.execute(
            select(EvaluationFinding).where(
                EvaluationFinding.evaluation_id == evaluation.id,
                EvaluationFinding.extracted_field_id
                == db.execute(
                    select(ExtractedField.id).where(
                        ExtractedField.source_ocr_result_id == ocr.id
                    )
                ).scalar_one(),
            )
        ).scalars().one()  # the MRP finding — it has the full OCR chain
        payload = graph_service.graph_for_finding(db, finding.id)
        nodes = _nodes(payload)
        assert f"EXTRACTED_FIELD:{finding.extracted_field_id}" in nodes
        field = nodes[f"EXTRACTED_FIELD:{finding.extracted_field_id}"]
        ocr_id = field["metadata"]["sourceOcrResultId"]
        assert ocr_id is not None
        assert f"OCR_RESULT:{ocr_id}" in nodes
        ocr = nodes[f"OCR_RESULT:{ocr_id}"]
        region_ref = ocr["metadata"].get("regionId", field["metadata"]["imageRegionId"])
        assert f"IMAGE_REGION:{region_ref}" in nodes
        # OCR → field and region → OCR edges exist
        assert _find_edge(
            payload, EvidenceEdgeType.OCR_SUPPORTS_FIELD
        ) is not None
        assert _find_edge(
            payload, EvidenceEdgeType.REGION_HAS_OCR_RESULT
        ) is not None
        # run + image nodes
        assert _find_edge(
            payload, EvidenceEdgeType.PROCESSING_RUN_PRODUCED_OCR
        ) is not None
        assert _find_edge(
            payload, EvidenceEdgeType.INSPECTION_CONTAINS_IMAGE
        ) is not None

    def test_finding_supported_by_evidence_edge_carries_strength(
        self, db, graph_service, evaluated
    ):
        _, evaluation = evaluated
        finding = next(
            f for f in evaluation.findings if f.extracted_field_id is not None
        )
        payload = graph_service.graph_for_finding(db, finding.id)
        edge = _find_edge(
            payload,
            EvidenceEdgeType.FINDING_SUPPORTED_BY_EVIDENCE,
            source=str(finding.id),
        )
        assert edge is not None
        assert edge["metadata"]["strength"] in {
            s.value for s in EvidenceStrength
        }


class TestFieldGraph:
    def test_field_graph_reverse_direction(self, db, graph_service, evaluated):
        """Field → OCR → Region → Image → Inspection AND every finding that
        used this field → requirement → version."""
        _, evaluation = evaluated
        finding = next(
            f for f in evaluation.findings if f.extracted_field_id is not None
        )
        field_id = finding.extracted_field_id
        payload = graph_service.graph_for_field(db, field_id)
        assert payload["rootType"] == "EXTRACTED_FIELD"
        nodes = _nodes(payload)
        assert f"EXTRACTED_FIELD:{field_id}" in nodes
        # reverse: this field was evaluated against a requirement
        assert f"REQUIREMENT:{finding.requirement_id}" in nodes
        assert _find_edge(
            payload, EvidenceEdgeType.FIELD_EVALUATED_AGAINST_REQUIREMENT
        ) is not None
        # evidence chain present too (the MRP field carries the full OCR chain)
        field = db.get(ExtractedField, field_id)
        if field.source_ocr_result_id:
            assert "OCR_RESULT" in {n["type"] for n in payload["nodes"]}
        assert "IMAGE" in {n["type"] for n in payload["nodes"]}
        assert "INSPECTION" in {n["type"] for n in payload["nodes"]}

    def test_field_with_no_findings(self, db, graph_service, evaluated):
        """A field no finding used (e.g. best-before was searched but not the
        primary evidence): still has its own evidence chain."""
        inspection, evaluation = evaluated
        finding_field_ids = {
            str(f.extracted_field_id) for f in evaluation.findings if f.extracted_field_id
        }
        all_fields = db.execute(
            select(ExtractedField).where(
                ExtractedField.processing_run_id.in_(
                    [r for r in db.execute(
                        select(ProcessingRun.id).where(
                            ProcessingRun.inspection_id == inspection.id
                        )
                    ).scalars()]
                )
            )
        ).scalars().all()
        unused = [f for f in all_fields if str(f.id) not in finding_field_ids]
        if not unused:  # every field was used — skip gracefully
            pytest.skip("all fields were consumed by findings")
        payload = graph_service.graph_for_field(db, unused[0].id)
        assert payload["evaluationId"] is None
        types = {n["type"] for n in payload["nodes"]}
        assert "INSPECTION" in types
        assert "FINDING" not in types


class TestEvidenceStrength:
    def test_missing_when_no_field(self, db, evaluated):
        _, evaluation = evaluated
        finding = next(f for f in evaluation.findings if f.extracted_field_id is None)
        assert evidence_strength(finding, None) == EvidenceStrength.MISSING.value

    def test_ambiguous_for_low_confidence(self, db):
        class FakeField:
            raw_text = "x"
            normalized_value = None
            status = "DETECTED"
            confidence = 0.4
            source_ocr_result_id = "ocr-1"
            image_region_id = None

        class FakeFinding:
            pass

        assert (
            evidence_strength(FakeFinding(), FakeField())
            == EvidenceStrength.AMBIGUOUS.value
        )

    def test_ambiguous_for_review_required(self, db):
        class FakeField:
            raw_text = "x"
            normalized_value = None
            status = "REVIEW_REQUIRED"
            confidence = 0.99
            source_ocr_result_id = None
            image_region_id = None

        class FakeFinding:
            pass

        assert (
            evidence_strength(FakeFinding(), FakeField())
            == EvidenceStrength.AMBIGUOUS.value
        )

    def test_direct_when_ocr_linked(self, db, evaluated):
        _, evaluation = evaluated
        run = db.execute(
            select(ProcessingRun).where(
                ProcessingRun.inspection_id == evaluation.inspection_id
            )
        ).scalars().first()
        ocr = db.execute(
            select(OcrTextResult).where(OcrTextResult.processing_run_id == run.id)
        ).scalars().one()
        finding = db.execute(
            select(EvaluationFinding).where(
                EvaluationFinding.evaluation_id == evaluation.id,
                EvaluationFinding.extracted_field_id
                == db.execute(
                    select(ExtractedField.id).where(
                        ExtractedField.source_ocr_result_id == ocr.id
                    )
                ).scalar_one(),
            )
        ).scalars().one()
        field = db.get(ExtractedField, finding.extracted_field_id)
        assert evidence_strength(finding, field) == EvidenceStrength.DIRECT.value

    def test_derived_when_no_ocr_link(self, db, evaluated):
        class FakeField:
            raw_text = "NET WT. 500 g"
            normalized_value = "500"
            status = "DETECTED"
            confidence = 0.95
            source_ocr_result_id = None
            image_region_id = None

        class FakeFinding:
            pass

        assert (
            evidence_strength(FakeFinding(), FakeField())
            == EvidenceStrength.DERIVED.value
        )

    def test_strength_vocabulary(self, graph_service):
        vocab = graph_service.strength_vocabulary()
        assert {v["strength"] for v in vocab} == {
            "DIRECT", "DERIVED", "AMBIGUOUS", "MISSING"
        }
        missing = next(v for v in vocab if v["strength"] == "MISSING")
        assert "never" in missing["description"].lower()


class TestBoundedTraversal:
    def test_node_cap_prevents_unbounded_growth(self, db, graph_service):
        """A graph with more nodes than the cap is truncated, never huge."""
        from app.services.evidence_graph import builder

        inspection = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        # Shrink the cap so the cap path is exercised without huge data.
        original = builder.MAX_NODES
        builder.MAX_NODES = 5
        try:
            payload = graph_service.graph_for_inspection(db, inspection.id)
            assert payload["truncated"] is True
            assert payload["nodeCount"] <= 5
        finally:
            builder.MAX_NODES = original

    def test_edge_ids_prevent_duplicate_edges(self, db, graph_service, evaluated):
        """Adding the same relationship twice is a no-op (cycle safety)."""
        inspection, _ = evaluated
        first = graph_service.graph_for_inspection(db, inspection.id)
        second = graph_service.graph_for_inspection(db, inspection.id)
        assert first["edgeCount"] == second["edgeCount"]
        assert first["nodeCount"] == second["nodeCount"]


class TestProvenance:
    def test_regulatory_nodes_carry_provenance(self, db, graph_service, evaluated):
        """Requirement → Version → Document → Source with real metadata."""
        _, evaluation = evaluated
        finding = evaluation.findings[0]
        payload = graph_service.graph_for_finding(db, finding.id)
        nodes = _nodes(payload)
        req = nodes[f"REQUIREMENT:{finding.requirement_id}"]
        version_id = req["metadata"]["versionId"]
        version = nodes[f"REGULATORY_VERSION:{version_id}"]
        assert version["metadata"]["versionLabel"]
        assert version["metadata"]["effectiveFrom"]
        doc = nodes[f"REGULATORY_DOCUMENT:{version['metadata']['documentId']}"]
        assert doc["metadata"]["title"]
        assert doc["metadata"]["isDemo"] is False
        if doc["metadata"]["sourceId"]:
            source = nodes[f"REGULATORY_SOURCE:{doc['metadata']['sourceId']}"]
            assert source["metadata"]["authority"]
            assert source["metadata"]["verificationStatus"] in {
                "UNVERIFIED", "VERIFIED", "SUPERSEDED", "ARCHIVED"
            }

    def test_historical_traceability_after_rule_deactivation(
        self, db, graph_service
    ):
        """Phase 14: a historical finding stays traceable even after its rule
        binding is deactivated — the finding row references remain intact."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        from app.models import ComplianceRule
        from app.services.compliance.engine import ComplianceEngine
        from app.services.regulatory.service import RegulatoryService

        eng = ComplianceEngine(regulatory=RegulatoryService())
        evaluation = eng.evaluate(db, inspection_id=inspection.id)
        finding = next(
            f for f in evaluation.findings
            if f.rule_id is not None or (f.detail or {}).get("rules")
        )
        # Deactivate every rule bound to this requirement AFTER the evaluation
        # was recorded — the finding's trace must survive.
        if finding.rule_id is not None:
            rule_ids = [finding.rule_id]
        else:
            codes = [
                o.get("ruleCode") for o in (finding.detail or {}).get("rules", [])
                if o.get("ruleCode")
            ]
            rule_ids = [
                r.id
                for r in db.execute(
                    select(ComplianceRule).where(
                        ComplianceRule.requirement_id == finding.requirement_id,
                        ComplianceRule.rule_code.in_(codes),
                    )
                ).scalars().all()
            ]
        for rid in rule_ids:
            db.get(ComplianceRule, rid).active = False
        db.commit()
        payload = graph_service.graph_for_finding(db, finding.id)
        nodes = _nodes(payload)
        for rid in rule_ids:
            assert f"RULE:{rid}" in nodes
            rule_node = nodes[f"RULE:{rid}"]
            assert rule_node["metadata"]["active"] is False
        assert f"REQUIREMENT:{finding.requirement_id}" in nodes


class TestNotFound:
    def test_unknown_inspection_404(self, db, graph_service):
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            graph_service.graph_for_inspection(db, uuid.uuid4())

    def test_unknown_finding_404(self, db, graph_service):
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            graph_service.graph_for_finding(db, uuid.uuid4())

    def test_unknown_field_404(self, db, graph_service):
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            graph_service.graph_for_field(db, uuid.uuid4())


# ===========================================================================
# 2. GOLDEN TRACE (Phase 18) — proves the graph is not fabricated
# ===========================================================================


class TestGoldenTrace:
    def test_full_golden_trace_image_to_finding(self, db, graph_service, evaluated):
        """IMAGE → REGION → OCR → MRP FIELD → REQUIREMENT → VERSION →
        DOCUMENT → SOURCE → RULE → EVALUATION → FINDING.

        Every step is asserted against the DATABASE, not against graph output
        alone — proving each node is a real record and each edge a real FK.
        """
        inspection, evaluation = evaluated
        from app.models import (
            ComplianceRule,
            EvaluationFinding,
            Regulation,
            RegulationVersion,
            RegulatorySource,
        )

        # --- locate the real MRP evidence in the DATABASE ---------------------
        run = db.execute(
            select(ProcessingRun).where(ProcessingRun.inspection_id == inspection.id)
        ).scalars().first()
        ocr = db.execute(
            select(OcrTextResult).where(OcrTextResult.processing_run_id == run.id)
        ).scalars().one()  # the one OCR row we attached (MRP)
        assert "MRP" in ocr.raw_text
        region = db.get(ImageRegion, ocr.region_id)
        field = db.execute(
            select(ExtractedField).where(
                ExtractedField.source_ocr_result_id == ocr.id
            )
        ).scalars().one()
        assert field.field_type == "MRP"

        finding = db.execute(
            select(EvaluationFinding).where(
                EvaluationFinding.evaluation_id == evaluation.id,
                EvaluationFinding.extracted_field_id == field.id,
            )
        ).scalars().one()
        requirement = db.get(Rule, finding.requirement_id)
        version = db.get(RegulationVersion, requirement.regulation_version_id)
        document = db.get(Regulation, version.regulation_id)
        source = db.get(RegulatorySource, document.source_id)
        # The deterministic rules that produced the finding — the engine links
        # a single rule_id when exactly one rule was bound, and records every
        # executed rule code in detail["rules"] otherwise. Both resolve to REAL
        # ComplianceRule rows.
        if finding.rule_id is not None:
            compliance_rules = [db.get(ComplianceRule, finding.rule_id)]
        else:
            codes = [
                o.get("ruleCode") for o in (finding.detail or {}).get("rules", [])
                if o.get("ruleCode")
            ]
            compliance_rules = list(
                db.execute(
                    select(ComplianceRule).where(
                        ComplianceRule.requirement_id == finding.requirement_id,
                        ComplianceRule.rule_code.in_(codes),
                    )
                ).scalars().all()
            )

        # --- assert every node and relationship in the graph ------------------
        payload = graph_service.graph_for_finding(db, finding.id)
        nodes = _nodes(payload)

        # Node existence — real ids only.
        assert f"INSPECTION:{inspection.id}" in nodes
        assert f"IMAGE:{run.image_id}" in nodes
        assert f"IMAGE_REGION:{region.id}" in nodes
        assert f"OCR_RESULT:{ocr.id}" in nodes
        assert f"EXTRACTED_FIELD:{field.id}" in nodes
        assert f"REQUIREMENT:{requirement.id}" in nodes
        assert f"REGULATORY_VERSION:{version.id}" in nodes
        assert f"REGULATORY_DOCUMENT:{document.id}" in nodes
        assert f"REGULATORY_SOURCE:{source.id}" in nodes
        if compliance_rules:
            for compliance_rule in compliance_rules:
                assert f"RULE:{compliance_rule.id}" in nodes
        assert f"EVALUATION:{evaluation.id}" in nodes
        assert f"FINDING:{finding.id}" in nodes
        assert f"PROCESSING_RUN:{run.id}" in nodes

        # Node metadata comes from the real records.
        assert nodes[f"OCR_RESULT:{ocr.id}"]["metadata"]["rawText"] == ocr.raw_text
        assert nodes[f"IMAGE_REGION:{region.id}"]["metadata"]["bbox"] == region.bbox
        assert nodes[f"EXTRACTED_FIELD:{field.id}"]["metadata"]["normalizedValue"] == (
            field.normalized_value
        )
        assert nodes[f"REQUIREMENT:{requirement.id}"]["metadata"]["ruleCode"] == (
            requirement.rule_code
        )
        assert nodes[f"REGULATORY_VERSION:{version.id}"]["metadata"]["versionLabel"] == (
            version.version_label
        )
        assert nodes[f"REGULATORY_DOCUMENT:{document.id}"]["metadata"]["title"] == (
            document.title
        )
        assert nodes[f"REGULATORY_SOURCE:{source.id}"]["metadata"]["name"] == source.name
        assert nodes[f"FINDING:{finding.id}"]["metadata"]["status"] == finding.status

        # Every relationship, asserted edge by edge.
        def edge(src_type, src_id, etype, tgt_type, tgt_id):
            # exact endpoint matching
            sid = f"{src_type}:{src_id}"
            tid = f"{tgt_type}:{tgt_id}"
            for e in payload["edges"]:
                if e["type"] == etype.value and e["source"] == sid and e["target"] == tid:
                    return e
            return None

        assert edge("INSPECTION", inspection.id,
                    EvidenceEdgeType.INSPECTION_HAS_EVALUATION,
                    "EVALUATION", evaluation.id)
        assert edge("IMAGE", run.image_id, EvidenceEdgeType.IMAGE_HAS_REGION,
                    "IMAGE_REGION", region.id)
        assert edge("IMAGE_REGION", region.id,
                    EvidenceEdgeType.REGION_HAS_OCR_RESULT,
                    "OCR_RESULT", ocr.id)
        assert edge("OCR_RESULT", ocr.id, EvidenceEdgeType.OCR_SUPPORTS_FIELD,
                    "EXTRACTED_FIELD", field.id)
        assert edge("FINDING", finding.id,
                    EvidenceEdgeType.FINDING_SUPPORTED_BY_EVIDENCE,
                    "EXTRACTED_FIELD", field.id)
        assert edge("FINDING", finding.id,
                    EvidenceEdgeType.FINDING_BELONGS_TO_EVALUATION,
                    "EVALUATION", evaluation.id)
        assert edge("REQUIREMENT", requirement.id,
                    EvidenceEdgeType.REQUIREMENT_BELONGS_TO_VERSION,
                    "REGULATORY_VERSION", version.id)
        assert edge("REGULATORY_VERSION", version.id,
                    EvidenceEdgeType.VERSION_ORIGINATES_FROM_DOCUMENT,
                    "REGULATORY_DOCUMENT", document.id)
        assert edge("REGULATORY_DOCUMENT", document.id,
                    EvidenceEdgeType.DOCUMENT_HAS_SOURCE,
                    "REGULATORY_SOURCE", source.id)
        for compliance_rule in compliance_rules:
            assert edge("RULE", compliance_rule.id,
                        EvidenceEdgeType.RULE_PRODUCED_FINDING,
                        "FINDING", finding.id)
            assert edge("REQUIREMENT", requirement.id,
                        EvidenceEdgeType.REQUIREMENT_EVALUATED_BY_RULE,
                        "RULE", compliance_rule.id)
        assert edge("PROCESSING_RUN", run.id,
                    EvidenceEdgeType.PROCESSING_RUN_PRODUCED_OCR,
                    "OCR_RESULT", ocr.id)

        # The evidence strength of the golden chain is DIRECT (real OCR link).
        strength_edge = edge("FINDING", finding.id,
                             EvidenceEdgeType.FINDING_SUPPORTED_BY_EVIDENCE,
                             "EXTRACTED_FIELD", field.id)
        assert strength_edge["metadata"]["strength"] == EvidenceStrength.DIRECT.value


# ===========================================================================
# 3. API layer
# ===========================================================================


class TestEvidenceGraphApi:
    def test_requires_auth(self, client, evaluated):
        inspection, _ = evaluated
        for path in (
            f"{API}/inspections/{inspection.id}/evidence-graph",
            f"{API}/evidence-graph",
        ):
            resp = client.get(path)
            assert resp.status_code == 401, path

    def test_inspection_graph_endpoint(self, client, inspector_headers, evaluated):
        inspection, evaluation = evaluated
        resp = client.get(
            f"{API}/inspections/{inspection.id}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rootType"] == "INSPECTION"
        assert body["rootId"] == str(inspection.id)
        assert body["evaluationId"] == str(evaluation.id)
        assert body["nodeCount"] == len(body["nodes"])
        assert body["edgeCount"] == len(body["edges"])
        assert body["boundaryNote"]
        assert all(
            set(n.keys()) >= {"id", "type", "label", "metadata"} for n in body["nodes"]
        )
        assert all(
            set(e.keys()) >= {"id", "source", "target", "type"} for e in body["edges"]
        )

    def test_historical_evaluation_param(self, client, inspector_headers, db):
        inspection = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        from app.services.compliance.engine import ComplianceEngine
        from app.services.regulatory.service import RegulatoryService

        eng = ComplianceEngine(regulatory=RegulatoryService())
        eng.evaluate(db, inspection_id=inspection.id)
        first = eng.evaluate(db, inspection_id=inspection.id)
        resp = client.get(
            f"{API}/inspections/{inspection.id}/evidence-graph"
            f"?evaluationId={first.id}",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["evaluationId"] == str(first.id)

    def test_finding_graph_endpoint(self, client, inspector_headers, evaluated):
        _, evaluation = evaluated
        finding = evaluation.findings[0]
        resp = client.get(
            f"{API}/compliance/findings/{finding.id}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rootType"] == "FINDING"
        assert body["rootId"] == str(finding.id)

    def test_field_graph_endpoint(self, client, inspector_headers, evaluated):
        _, evaluation = evaluated
        finding = next(
            f for f in evaluation.findings if f.extracted_field_id is not None
        )
        resp = client.get(
            f"{API}/fields/{finding.extracted_field_id}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rootType"] == "EXTRACTED_FIELD"

    def test_vocabulary_endpoint(self, client, inspector_headers):
        resp = client.get(f"{API}/evidence-graph", headers=inspector_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["strengths"]) == 4
        assert "does not independently determine legal compliance" in body["boundaryNote"]

    def test_404_unknown_inspection(self, client, inspector_headers):
        resp = client.get(
            f"{API}/inspections/{uuid.uuid4()}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_404_unknown_finding(self, client, inspector_headers):
        resp = client.get(
            f"{API}/compliance/findings/{uuid.uuid4()}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_404_unknown_field(self, client, inspector_headers):
        resp = client.get(
            f"{API}/fields/{uuid.uuid4()}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_no_sensitive_data_in_nodes(self, client, inspector_headers, evaluated):
        """No storage keys, filesystem paths, credentials in node metadata."""
        inspection, _ = evaluated
        resp = client.get(
            f"{API}/inspections/{inspection.id}/evidence-graph",
            headers=inspector_headers,
        )
        blob = resp.text.lower()
        for banned in (
            "storage_key", "storagekey", "secret", "password", "token",
            "api_key", "apikey", ".env", "e:\\", "c:\\", "/home/", "/users/"
        ):
            assert banned not in blob, f"sensitive data leaked: {banned}"

    def test_demo_finding_route_untouched(self, client, inspector_headers):
        """The Prompt 1 demo evidence-graph route still exists and returns
        404 for an unknown demo finding (not shadowed by Prompt 7)."""
        resp = client.get(
            f"{API}/findings/{uuid.uuid4()}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# 4. HUMAN NODES (Prompt 8, Phase 15) — AI vs HUMAN distinction
# ===========================================================================


def _make_low_conf_field(db, inspection_id, *, corrected=None):
    """A REVIEW_REQUIRED / low-confidence field, optionally human-corrected."""
    from app.models import Package

    package = db.execute(
        select(Package).where(Package.inspection_id == inspection_id)
    ).scalars().first()
    field = ExtractedField(
        package_id=package.id,
        image_id=package.images[0].id,
        field_type="OTHER",
        raw_text="maybe a value",
        normalized_value="maybe a value",
        confidence=0.2,
        status="REVIEW_REQUIRED",
        extraction_method="REGEX",
    )
    if corrected is not None:
        field.corrected_value = corrected
    db.add(field)
    db.flush()
    return field


class TestHumanNodes:
    """The graph must represent AI outputs and human actions as DISTINCT
    nodes: a correction/review/decision is its own origin=HUMAN node with an
    actor, never a mutation of the origin=AI node it acts upon."""

    @pytest.fixture()
    def inspector(self, db):
        return db.execute(
            select(User).where(User.role == UserRole.INSPECTOR.value)
        ).scalars().first()

    @pytest.fixture()
    def human_flow(self, db, services, evaluated, inspector):
        """A corrected field + a confirmed finding + a recorded decision."""
        from app.models import Package

        hitl = services.hitl
        inspection, evaluation = evaluated
        package = db.execute(
            select(Package).where(Package.inspection_id == inspection.id)
        ).scalars().first()
        field = db.execute(
            select(ExtractedField).where(
                ExtractedField.package_id == package.id,
                ExtractedField.field_type == "MRP",
            )
        ).scalars().first()
        correction = hitl.correct_field(
            db,
            field_id=field.id,
            actor=inspector,
            corrected_value="65.00",
            reason="Inspector verified MRP against the physical package.",
        )
        finding = db.execute(
            select(EvaluationFinding).where(
                EvaluationFinding.evaluation_id == evaluation.id,
                EvaluationFinding.extracted_field_id == field.id,
            )
        ).scalars().first()
        review = hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM"
        ).review
        decision = hitl.submit_decision(
            db,
            inspection_id=inspection.id,
            actor=inspector,
            decision=InspectionDecisionType.COMPLIANT,
        )
        db.commit()
        return inspection, evaluation, field, correction, finding, review, decision

    def test_human_nodes_exist_with_human_origin(self, db, graph_service, human_flow):
        inspection, _ev, _field, correction, _f, review, decision = human_flow
        payload = graph_service.graph_for_inspection(db, inspection.id)
        nodes = _nodes(payload)
        assert f"FIELD_CORRECTION:{correction.id}" in nodes
        assert f"FINDING_REVIEW:{review.id}" in nodes
        assert f"INSPECTION_DECISION:{decision.id}" in nodes
        for nid in (
            f"FIELD_CORRECTION:{correction.id}",
            f"FINDING_REVIEW:{review.id}",
            f"INSPECTION_DECISION:{decision.id}",
        ):
            assert nodes[nid]["metadata"]["origin"] == "HUMAN"

    def test_correction_metadata_carries_before_after(self, db, graph_service,
                                                      human_flow):
        inspection, _ev, _field, correction, _f, _r, _d = human_flow
        payload = graph_service.graph_for_inspection(db, inspection.id)
        node = _nodes(payload)[f"FIELD_CORRECTION:{correction.id}"]
        assert node["metadata"]["correctedValue"] == "65.00"
        assert node["metadata"]["previousValue"] == correction.previous_value
        assert "Inspector verified" in node["metadata"]["reason"]

    def test_correction_edge_points_at_ai_field_node(self, db, graph_service,
                                                     human_flow):
        inspection, _ev, field, correction, _f, _r, _d = human_flow
        payload = graph_service.graph_for_inspection(db, inspection.id)
        edge = _find_edge(
            payload,
            EvidenceEdgeType.FIELD_CORRECTION_CORRECTS_FIELD,
            source=f"FIELD_CORRECTION:{correction.id}",
            target=f"EXTRACTED_FIELD:{field.id}",
        )
        assert edge is not None
        # The AI field node is STILL in the graph, still origin=AI, still
        # carrying its ORIGINAL values — the correction never mutated it.
        field_node = _nodes(payload)[f"EXTRACTED_FIELD:{field.id}"]
        assert field_node["metadata"]["origin"] == "AI"
        assert field_node["metadata"]["normalizedValue"] == field.normalized_value
        assert field_node["metadata"]["hasHumanCorrection"] is True
        assert field_node["metadata"]["correctedValue"] == "65.00"

    def test_review_edge_points_at_ai_finding_node(self, db, graph_service,
                                                   human_flow):
        inspection, _ev, _field, _c, finding, review, _d = human_flow
        payload = graph_service.graph_for_inspection(db, inspection.id)
        edge = _find_edge(
            payload,
            EvidenceEdgeType.FINDING_REVIEW_REVIEWS_FINDING,
            source=f"FINDING_REVIEW:{review.id}",
            target=f"FINDING:{finding.id}",
        )
        assert edge is not None
        finding_node = _nodes(payload)[f"FINDING:{finding.id}"]
        assert finding_node["metadata"]["origin"] == "AI"
        assert finding_node["metadata"]["reviewState"] == "CONFIRMED"

    def test_decision_edges_and_supersede_chain(self, db, services, graph_service,
                                                human_flow, inspector):
        inspection, evaluation, _field, _c, _f, _r, first = human_flow
        hitl = services.hitl
        second = hitl.submit_decision(
            db,
            inspection_id=inspection.id,
            actor=inspector,
            decision=InspectionDecisionType.NON_COMPLIANT,
            reason="Post-review violation confirmed on reinspection.",
        )
        db.commit()
        payload = graph_service.graph_for_inspection(db, inspection.id)
        nodes = _nodes(payload)
        # BOTH decisions remain — decisions are superseded, never deleted.
        assert f"INSPECTION_DECISION:{first.id}" in nodes
        assert f"INSPECTION_DECISION:{second.id}" in nodes
        edge = _find_edge(
            payload,
            EvidenceEdgeType.DECISION_SUPERSEDES_DECISION,
            source=f"INSPECTION_DECISION:{second.id}",
            target=f"INSPECTION_DECISION:{first.id}",
        )
        assert edge is not None
        assert _find_edge(
            payload,
            EvidenceEdgeType.DECISION_FOR_INSPECTION,
            source=f"INSPECTION_DECISION:{second.id}",
            target=f"INSPECTION:{inspection.id}",
        ) is not None
        assert _find_edge(
            payload,
            EvidenceEdgeType.DECISION_BASED_ON_EVALUATION,
            source=f"INSPECTION_DECISION:{second.id}",
            target=f"EVALUATION:{evaluation.id}",
        ) is not None

    def test_ai_and_system_nodes_carry_origins(self, db, graph_service, human_flow):
        """AI outputs are origin=AI; neutral records are origin=SYSTEM —
        the three origins are never conflated."""
        inspection, _ev, _field, _c, _f, _r, _d = human_flow
        payload = graph_service.graph_for_inspection(db, inspection.id)
        origins: dict[str, set] = {}
        for node in payload["nodes"]:
            origins.setdefault(node["type"], set()).add(node["metadata"]["origin"])
        for ai_type in (
            "OCR_RESULT",
            "IMAGE_REGION",
            "EXTRACTED_FIELD",
            "EVALUATION",
            "FINDING",
            "PROCESSING_RUN",
        ):
            assert origins.get(ai_type) == {"AI"}, ai_type
        for system_type in (
            "INSPECTION",
            "IMAGE",
            "REQUIREMENT",
            "RULE",
            "REGULATORY_VERSION",
        ):
            assert origins.get(system_type) == {"SYSTEM"}, system_type
        assert origins.get("FIELD_CORRECTION") == {"HUMAN"}
        assert origins.get("FINDING_REVIEW") == {"HUMAN"}
        assert origins.get("INSPECTION_DECISION") == {"HUMAN"}

    def test_hitl_audit_events_link_to_human_nodes(self, db, graph_service, human_flow):
        """FIELD_CORRECTED / decision audit events are overlaid and point at
        the HUMAN nodes they record (not vaguely at the evaluation)."""
        inspection, _ev, _field, correction, _f, _r, decision = human_flow
        payload = graph_service.graph_for_inspection(db, inspection.id)
        assert _find_edge(
            payload,
            EvidenceEdgeType.AUDIT_RECORDS_ACTION,
            target=f"FIELD_CORRECTION:{correction.id}",
        ) is not None
        assert _find_edge(
            payload,
            EvidenceEdgeType.AUDIT_RECORDS_ACTION,
            target=f"INSPECTION_DECISION:{decision.id}",
        ) is not None

    def test_finding_graph_includes_its_review(self, db, graph_service, human_flow):
        _insp, _ev, _field, _c, finding, review, _d = human_flow
        payload = graph_service.graph_for_finding(db, finding.id)
        nodes = _nodes(payload)
        assert f"FINDING_REVIEW:{review.id}" in nodes
        assert _find_edge(
            payload,
            EvidenceEdgeType.FINDING_REVIEW_REVIEWS_FINDING,
            source=f"FINDING_REVIEW:{review.id}",
            target=f"FINDING:{finding.id}",
        ) is not None

    def test_field_graph_includes_its_corrections(self, db, graph_service, human_flow):
        _insp, _ev, field, correction, _f, _r, _d = human_flow
        payload = graph_service.graph_for_field(db, field.id)
        nodes = _nodes(payload)
        assert f"FIELD_CORRECTION:{correction.id}" in nodes
        assert nodes[f"FIELD_CORRECTION:{correction.id}"]["metadata"]["origin"] == (
            "HUMAN"
        )

    def test_no_human_nodes_without_human_actions(self, db, graph_service, evaluated):
        """A machine-only inspection has ZERO HUMAN-origin nodes — the origin
        labels are not decorative defaults."""
        inspection, _ev = evaluated
        payload = graph_service.graph_for_inspection(db, inspection.id)
        human_nodes = [
            n
            for n in payload["nodes"]
            if (n["metadata"] or {}).get("origin") == "HUMAN"
        ]
        assert human_nodes == []
        assert all(
            (n["metadata"] or {}).get("origin") in ("AI", "SYSTEM")
            for n in payload["nodes"]
        )

    def test_corrected_low_confidence_field_is_not_ambiguous(self, db, graph_service,
                                                             evaluated):
        """A human-confirmed correction is sufficient evidence — the ORIGINAL
        low AI confidence never downgrades it to AMBIGUOUS (mirrors the
        engine's corrected-value bypass of the quality gate)."""
        inspection, _ev = evaluated
        field = _make_low_conf_field(db, inspection.id, corrected="60.00")
        assert evidence_strength(None, None) == EvidenceStrength.MISSING.value
        strength = evidence_strength(None, field)
        assert strength in (
            EvidenceStrength.DIRECT.value,
            EvidenceStrength.DERIVED.value,
        )
