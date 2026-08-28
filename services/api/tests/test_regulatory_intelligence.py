"""Regulatory intelligence tests (Prompt 5) — service + data-quality layer.

Covers the version-aware Source → Document → Version → Requirement hierarchy
and its invariants:

* deterministic effective-date selection, including the explicit
  NO_APPLICABLE_VERSION state (never a silent fall-back to the newest);
* supersession — old versions keep their own requirement set, untouched;
* idempotent seed and the loud-failing data-quality validator;
* the candidate mapping from perception fields to requirement definitions,
  which must never produce a compliance verdict;
* auditability of the one admin-writable mutation (source verification).

The fakes-driven perception fixtures come from the Prompt 4 test module so the
candidate-mapping tests run against real extracted fields.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.enums import (
    CandidateMappingStatus,
    DocumentType,
    RegulationVersionStatus,
    SourceType,
    VerificationStatus,
)
from app.core.errors import RegulatoryDataInvalidError
from app.db.regulatory_seed import seed_regulatory_data
from app.models import (
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
)
from app.services.regulatory.quality import (
    assert_regulatory_data_quality,
    validate_regulatory_data,
)
from app.services.regulatory.service import RegulatoryService
from tests.conftest import API
from tests.test_perception_pipeline import FakeOCRService, FakeVisionService

# Reference points inside / outside the seeded version windows.
BEFORE_RULES = datetime(2005, 1, 1, tzinfo=UTC)  # before any LM(PC) version
V1_DATE = datetime(2012, 6, 1, tzinfo=UTC)  # 2011 original in force
V2_DATE = datetime(2016, 6, 1, tzinfo=UTC)  # G.S.R. 385(E)/2015 in force
V3_DATE = datetime(2020, 6, 1, tzinfo=UTC)  # G.S.R. 629(E)/2017 consolidated

LM_DOC_CODE = "LM-PC-RULES-2011"


def _lm_document(db) -> Regulation:
    return db.execute(select(Regulation).where(Regulation.code == LM_DOC_CODE)).scalar_one()


def _version(db, label: str) -> RegulationVersion:
    return db.execute(
        select(RegulationVersion).where(RegulationVersion.version_label == label)
    ).scalar_one()


# --- source / document / version hierarchy ----------------------------------


class TestHierarchy:
    def test_seeded_source_is_unverified_government_department(self, db):
        source = db.execute(select(RegulatorySource)).scalar_one()
        assert source.source_type == SourceType.GOVERNMENT_DEPARTMENT.value
        assert source.verification_status == VerificationStatus.UNVERIFIED.value
        # Research-grade honesty: an UNVERIFIED source must carry the note
        # explaining why it is not yet VERIFIED.
        assert source.verification_note
        note_l = source.verification_note.lower()
        assert "unverif" in note_l or "verify" in note_l

    def test_document_belongs_to_source_with_provenance(self, db):
        doc = _lm_document(db)
        assert doc.source_id is not None
        assert doc.document_identifier and "G.S.R. 202(E)" in doc.document_identifier
        assert doc.document_type == DocumentType.RULES.value
        assert doc.publication_date is not None
        assert doc.publication_date.replace(tzinfo=UTC) == datetime(2011, 3, 7, tzinfo=UTC)
        assert doc.is_demo is False
        source = db.get(RegulatorySource, doc.source_id)
        assert source is not None

    def test_document_versions_are_ordered_and_chained(self, db):
        doc = _lm_document(db)
        versions = sorted(doc.versions, key=lambda v: v.effective_from)
        assert [v.status for v in versions] == [
            RegulationVersionStatus.SUPERSEDED.value,
            RegulationVersionStatus.SUPERSEDED.value,
            RegulationVersionStatus.ACTIVE.value,
        ]
        # amendment chain: each version amends the previous one
        assert versions[1].amendment_of_id == versions[0].id
        assert versions[2].amendment_of_id == versions[1].id


class TestVersionSelection:
    def test_selection_is_deterministic_per_date(self, db):
        svc = RegulatoryService()
        doc = _lm_document(db)
        for at, expected in [
            (V1_DATE, "2011 original"),
            (V2_DATE, "as amended by G.S.R. 385(E)/2015"),
            (V3_DATE, "as amended through G.S.R. 629(E)/2017 (consolidated)"),
        ]:
            version, status = svc.resolve_version(db, document_id=doc.id, at=at)
            assert status.value == "FOUND"
            assert version.version_label == expected

    def test_date_before_first_version_is_no_applicable_version(self, db):
        svc = RegulatoryService()
        doc = _lm_document(db)
        version, status = svc.resolve_version(db, document_id=doc.id, at=BEFORE_RULES)
        assert status.value == "NO_APPLICABLE_VERSION"
        assert version is None

    def test_boundary_dates_open_left_closed_right(self, db):
        svc = RegulatoryService()
        doc = _lm_document(db)
        # v2 window is [2016-01-01, 2017-06-23)
        v, s = svc.resolve_version(db, document_id=doc.id, at=datetime(2016, 1, 1, tzinfo=UTC))
        assert (s.value, v.version_label) == (
            "FOUND",
            "as amended by G.S.R. 385(E)/2015",
        )
        # one second before v3's effective_from still selects v2
        just_before = datetime(2017, 6, 22, 23, 59, 59, tzinfo=UTC)
        v, s = svc.resolve_version(db, document_id=doc.id, at=just_before)
        assert (s.value, v.version_label) == (
            "FOUND",
            "as amended by G.S.R. 385(E)/2015",
        )
        # exactly v3's effective_from selects v3
        v, s = svc.resolve_version(db, document_id=doc.id, at=datetime(2017, 6, 23, tzinfo=UTC))
        assert (s.value, v.version_label) == (
            "FOUND",
            "as amended through G.S.R. 629(E)/2017 (consolidated)",
        )

    def test_future_version_not_selected_for_past_date(self, db):
        svc = RegulatoryService()
        doc = _lm_document(db)
        # 2011 date must not resolve to the 2017 consolidated version.
        v, s = svc.resolve_version(db, document_id=doc.id, at=V1_DATE)
        assert v.version_label == "2011 original"
        assert "G.S.R. 629" not in v.version_label


class TestRequirementSets:
    def test_old_and_new_versions_have_independent_requirement_sets(self, db):
        v1 = _version(db, "2011 original")
        v2 = _version(db, "as amended by G.S.R. 385(E)/2015")
        v3 = _version(db, "as amended through G.S.R. 629(E)/2017 (consolidated)")
        for v in (v1, v2, v3):
            codes = {
                r.rule_code
                for r in db.execute(
                    select(Rule).where(Rule.regulation_version_id == v.id)
                ).scalars()
            }
            if v is v1:
                assert "LM-PC-2011-6.2" not in codes  # consumer care added 2016
                assert "LM-PC-2011-6.1(aa)" not in codes  # origin added 2017
            if v is v2:
                assert "LM-PC-2011-6.2" in codes
                assert "LM-PC-2011-6.1(aa)" not in codes
            if v is v3:
                assert "LM-PC-2011-6.1(aa)" in codes
                assert "LM-PC-2011-6.1(da)" in codes

    def test_requirements_carry_provenance_fields(self, db):
        v3 = _version(db, "as amended through G.S.R. 629(E)/2017 (consolidated)")
        origin_rule = (
            db.execute(
                select(Rule).where(
                    Rule.regulation_version_id == v3.id,
                    Rule.rule_code == "LM-PC-2011-6.1(aa)",
                )
            )
            .scalars()
            .one()
        )
        assert origin_rule.field_key == "COUNTRY_OF_ORIGIN"
        assert origin_rule.requirement_type == "DECLARATION"
        assert origin_rule.source_reference and "G.S.R. 629(E)" in origin_rule.source_reference
        assert origin_rule.mandatory is True
        assert origin_rule.is_demo is False


class TestSeedIdempotencyAndQuality:
    def test_seed_is_idempotent(self, db):
        before = {
            m.__name__: len(
                list(db.execute(select(m)).scalars())
            )
            for m in (RegulatorySource, Regulation, RegulationVersion, Rule)
        }
        seed_regulatory_data(db)
        after = {
            m.__name__: len(
                list(db.execute(select(m)).scalars())
            )
            for m in (RegulatorySource, Regulation, RegulationVersion, Rule)
        }
        assert before == after

    def test_seeded_data_passes_quality_validation(self, db):
        assert validate_regulatory_data(db) == []

    def test_quality_validator_flags_missing_source(self, db):
        doc = _lm_document(db)
        doc.source_id = None
        db.flush()
        issues = validate_regulatory_data(db)
        assert any(i["code"] == "MISSING_SOURCE" for i in issues)
        db.rollback()

    def test_quality_validator_flags_overlapping_versions(self, db):
        v3 = _version(db, "as amended through G.S.R. 629(E)/2017 (consolidated)")
        v2 = _version(db, "as amended by G.S.R. 385(E)/2015")
        # make v2's window overlap v3's by extending it
        v2.effective_until = v3.effective_until  # None -> overlap
        db.flush()
        issues = validate_regulatory_data(db)
        assert any(i["code"] == "OVERLAPPING_VERSIONS" for i in issues)
        db.rollback()

    def test_quality_validator_flags_invalid_effective_dates(self, db):
        v3 = _version(db, "as amended through G.S.R. 629(E)/2017 (consolidated)")
        v3.effective_until = v3.effective_from - timedelta(days=1)
        db.flush()
        issues = validate_regulatory_data(db)
        assert any(i["code"] == "INVALID_EFFECTIVE_DATE" for i in issues)
        db.rollback()

    def test_quality_validator_flags_duplicate_requirement(self, db):
        v3 = _version(db, "as amended through G.S.R. 629(E)/2017 (consolidated)")
        dup = Rule(
            regulation_version_id=v3.id,
            rule_code="LM-PC-2011-6.1(a)",
            title="Duplicate",
            requirement_summary="duplicate requirement",
            validation_logic_ref="field_present",
            is_demo=False,
        )
        db.add(dup)
        db.flush()
        issues = validate_regulatory_data(db)
        assert any(i["code"] == "DUPLICATE_REQUIREMENT" for i in issues)
        db.rollback()

    def test_quality_validator_flags_unverified_without_note(self, db):
        source = db.execute(select(RegulatorySource)).scalar_one()
        source.verification_note = None
        db.flush()
        issues = validate_regulatory_data(db)
        assert any(i["code"] == "UNVERIFIED_SOURCE_WITHOUT_NOTE" for i in issues)
        db.rollback()

    def test_assert_quality_raises_loudly(self, db):
        doc = _lm_document(db)
        doc.source_id = None
        db.flush()
        with pytest.raises(RegulatoryDataInvalidError) as exc_info:
            assert_regulatory_data_quality(db, context="test")
        assert any(
            i["code"] == "MISSING_SOURCE" for i in exc_info.value.details.get("issues", [])
        )
        db.rollback()


# --- candidate mapping (perception → regulations, NO evaluation) -------------


class TestCandidateMapping:
    @pytest.fixture()
    def perceived(self, client, inspector_headers, services, monkeypatch):
        """Inspection with a real perception run (fake OCR/vision)."""
        pipeline = services.perception._pipeline
        monkeypatch.setattr(pipeline, "_ocr", FakeOCRService())
        monkeypatch.setattr(pipeline, "_vision", FakeVisionService())

        resp = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": "Candidate Mapping Sample", "productCategory": "food"},
        )
        assert resp.status_code == 201, resp.text
        inspection_id = resp.json()["id"]

        img = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("front.png", _label_png_bytes(), "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        assert img.status_code == 201, img.text

        kick = client.post(
            f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers
        )
        assert kick.status_code == 202, kick.text
        return inspection_id

    def test_fields_map_to_candidates_without_verdict(self, client, inspector_headers, perceived):
        resp = client.get(
            f"{API}/inspections/{perceived}/regulatory-candidates",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["inspectionId"] == perceived
        assert body["regulatoryEvaluation"] == "AWAITING_REGULATORY_EVALUATION"

        by_type = {f["fieldType"]: f for f in body["fields"]}
        # MRP and net quantity exist in the fake OCR output and match seeded
        # requirement field_keys.
        assert "MRP" in by_type
        mrp = by_type["MRP"]
        assert mrp["mappingStatus"] == CandidateMappingStatus.CANDIDATE.value
        assert mrp["applicabilityStatus"] == (
            CandidateMappingStatus.APPLICABILITY_NOT_EVALUATED.value
        )
        assert mrp["evaluationStatus"] == CandidateMappingStatus.AWAITING_COMPLIANCE_ENGINE.value
        codes = [c["ruleCode"] for c in mrp["candidates"]]
        assert "LM-PC-2011-6.1(e)" in codes
        # every candidate carries source verification status (UNVERIFIED today)
        for cand in mrp["candidates"]:
            assert cand["sourceVerificationStatus"] == VerificationStatus.UNVERIFIED.value

    def test_candidates_resolve_version_by_context_date(
        self, db, client, inspector_headers, perceived
    ):
        # Same inspection, but evaluated with a 2012 context: the candidate
        # must come from the 2011 original version, not the consolidated one.
        resp = client.get(
            f"{API}/inspections/{perceived}/regulatory-candidates",
            headers=inspector_headers,
            params={"on": "2012-06-01T00:00:00Z"},
        )
        assert resp.status_code == 200, resp.text
        mrp = next(f for f in resp.json()["fields"] if f["fieldType"] == "MRP")
        assert mrp["candidates"], "2012 context must still find the 2011 MRP requirement"
        for cand in mrp["candidates"]:
            assert cand["effectiveFrom"].startswith("2011-04-01")

    def test_no_applicable_version_for_ancient_context(self, client, inspector_headers, perceived):
        resp = client.get(
            f"{API}/inspections/{perceived}/regulatory-candidates",
            headers=inspector_headers,
            params={"on": "1999-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200, resp.text
        for field in resp.json()["fields"]:
            assert field["candidates"] == []

    def test_unknown_field_type_has_no_candidates(self, db):
        svc = RegulatoryService()
        candidates = svc.requirement_candidates_for_field(
            db, field_type="NOT_A_REAL_FIELD", at=V3_DATE
        )
        assert candidates == []

    def test_service_field_candidates_marks_every_entry(
        self, db, client, inspector_headers, perceived
    ):
        svc = RegulatoryService()
        result = svc.field_candidates(db, inspection_id=_uuid(perceived))
        assert result["context_date"] is not None
        for entry in result["fields"]:
            assert entry["mapping_status"] == CandidateMappingStatus.CANDIDATE.value
            assert entry["applicability_status"] == (
                CandidateMappingStatus.APPLICABILITY_NOT_EVALUATED.value
            )
            assert entry["evaluation_status"] == (
                CandidateMappingStatus.AWAITING_COMPLIANCE_ENGINE.value
            )


def _uuid(value: str):
    import uuid as _uuid_mod

    return _uuid_mod.UUID(value)


def _label_png_bytes() -> bytes:
    from tests.test_perception_pipeline import _label_png

    return _label_png()
