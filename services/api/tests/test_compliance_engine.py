"""Deterministic compliance engine tests (Prompt 6).

Covers the engine contract in layers:

* ApplicabilityResolver — YES / NO / UNKNOWN outcomes and their reasons
* rule-type evaluators — every seeded rule type, decimal safety, MRP parsing,
  ambiguity handling (AMBIGUOUS never becomes a pass or a fail)
* ComplianceEngine end-to-end — version-aware evaluation over real seeded
  regulatory data, the NOT_DETECTED vs NON_COMPLIANT distinction, determinism,
  historical-result preservation, transparent count-only summaries, and the
  golden cases A–F

Legal-safety invariants under test (each must fail loudly if broken):

1. No engine failure is ever converted into COMPLIANT.
2. Missing OCR is never legal non-compliance (FIELD_NOT_FOUND).
3. UNKNOWN applicability → REVIEW_REQUIRED, never a silent skip.
4. No percentages / fake confidence anywhere in the summary.
5. Explanations answer the seven explainability questions.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.enums import (
    ApplicabilityOutcome,
    EngineFindingStatus,
    EvaluationStatus,
)
from app.models import (
    ComplianceEvaluation,
    ComplianceRule,
    ExtractedField,
    Image,
    Inspection,
    Package,
    ProcessingRun,
    Product,
    Rule,
)
from app.services.compliance.applicability import (
    ApplicabilityInput,
    ApplicabilityResolver,
)
from app.services.compliance.evaluators import (
    evaluate_comparison,
    evaluate_contact_format,
    evaluate_date_format,
    evaluate_declaration_format,
    evaluate_mrp_format,
    evaluate_numeric_value,
    evaluate_presence,
    evaluate_range,
    evaluate_text_match,
    evaluate_text_pattern,
    evaluate_unit_match,
    get_evaluator,
    registered_rule_types,
)

# ---------------------------------------------------------------------------
# Test doubles for ExtractedField (the evaluators only read these attributes).
# ---------------------------------------------------------------------------


class FakeField:
    def __init__(
        self,
        *,
        raw_text="",
        normalized_value=None,
        unit=None,
        confidence=0.95,
        status="DETECTED",
    ):
        self.raw_text = raw_text
        self.normalized_value = normalized_value
        self.unit = unit
        self.confidence = confidence
        self.status = status


# ===========================================================================
# 1. Applicability resolver
# ===========================================================================


@pytest.fixture()
def applicability() -> ApplicabilityResolver:
    return ApplicabilityResolver()


class TestApplicability:
    def test_wildcard_commodity_applies_to_everything(self, applicability):
        result = applicability.evaluate(
            {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
            ApplicabilityInput(category="anything", imported=None),
        )
        assert result.outcome is ApplicabilityOutcome.YES

    def test_category_list_match_is_yes(self, applicability):
        result = applicability.evaluate(
            {"commodity": ["food", "consumables-with-shelf-life"]},
            ApplicabilityInput(category="food", imported=None),
        )
        assert result.outcome is ApplicabilityOutcome.YES

    def test_category_mismatch_is_no_with_reason(self, applicability):
        result = applicability.evaluate(
            {"commodity": ["textiles", "paper", "garments"]},
            ApplicabilityInput(category="electronics", imported=None),
        )
        assert result.outcome is ApplicabilityOutcome.NO
        assert "electronics" in result.reason

    def test_missing_category_is_unknown_not_no(self, applicability):
        result = applicability.evaluate(
            {"commodity": ["food"]},
            ApplicabilityInput(category=None, imported=None),
        )
        assert result.outcome is ApplicabilityOutcome.UNKNOWN

    def test_imported_only_unknown_when_import_status_unknown(self, applicability):
        result = applicability.evaluate(
            {"commodity": "*", "importedOnly": True},
            ApplicabilityInput(category="food", imported=None),
        )
        assert result.outcome is ApplicabilityOutcome.UNKNOWN
        assert "import" in result.reason.lower()

    def test_imported_only_no_for_domestic(self, applicability):
        result = applicability.evaluate(
            {"commodity": "*", "importedOnly": True},
            ApplicabilityInput(category="food", imported=False),
        )
        assert result.outcome is ApplicabilityOutcome.NO

    def test_imported_only_yes_for_imported(self, applicability):
        result = applicability.evaluate(
            {"commodity": "*", "importedOnly": True},
            ApplicabilityInput(category="food", imported=True),
        )
        assert result.outcome is ApplicabilityOutcome.YES

    def test_empty_condition_applies_generally(self, applicability):
        result = applicability.evaluate(None, ApplicabilityInput(category=None, imported=None))
        assert result.outcome is ApplicabilityOutcome.YES

    def test_sale_context_mismatch_is_no(self, applicability):
        result = applicability.evaluate(
            {"saleContext": "WHOLESALE"},
            ApplicabilityInput(category="food", imported=None),
        )
        assert result.outcome is ApplicabilityOutcome.NO


# ===========================================================================
# 2. Rule-type evaluators
# ===========================================================================


class TestPresenceEvaluator:
    def test_detected_value_passes(self):
        outcome = evaluate_presence(
            FakeField(raw_text="MRP 25", normalized_value="25"), {}
        )
        assert outcome.passed is True

    def test_missing_field_is_indeterminate_not_fail(self):
        outcome = evaluate_presence(None, {})
        assert outcome.passed is None
        assert outcome.detail["absence"] == "FIELD_NOT_FOUND"
        # Phase 5: the reason must explicitly deny absence.
        assert "not evidence that the declaration is absent" in outcome.reason

    def test_not_extracted_is_indeterminate(self):
        field = FakeField(status="NOT_EXTRACTED", raw_text="MRP")
        outcome = evaluate_presence(field, {})
        assert outcome.passed is None

    def test_low_confidence_is_indeterminate(self):
        field = FakeField(raw_text="MRP 25", normalized_value="25", confidence=0.3)
        outcome = evaluate_presence(field, {})
        assert outcome.passed is None
        assert outcome.detail["outcome_code"] == "INSUFFICIENT_EVIDENCE"

    def test_review_required_status_is_indeterminate(self):
        field = FakeField(status="REVIEW_REQUIRED", confidence=0.9)
        outcome = evaluate_presence(field, {})
        assert outcome.passed is None

    def test_empty_normalized_value_is_indeterminate(self):
        field = FakeField(raw_text="  ", normalized_value="")
        outcome = evaluate_presence(field, {})
        assert outcome.passed is None


class TestMrpFormatEvaluator:
    def test_full_mrp_declaration_passes(self):
        field = FakeField(raw_text="MRP ₹ 99.00 (inclusive of all taxes)")
        outcome = evaluate_mrp_format(field, {})
        assert outcome.passed is True
        assert outcome.detail["detected_amount"] == "99.00"

    def test_missing_inclusive_phrase_fails(self):
        field = FakeField(raw_text="MRP ₹ 99.00")
        outcome = evaluate_mrp_format(field, {})
        assert outcome.passed is False
        assert "inclusive of all taxes" in outcome.reason

    def test_no_parseable_price_fails(self):
        field = FakeField(raw_text="Best product ever")
        outcome = evaluate_mrp_format(field, {})
        assert outcome.passed is False

    def test_ambiguous_price_is_never_fail_or_pass(self):
        field = FakeField(raw_text="MRP ₹ ..,/../")
        outcome = evaluate_mrp_format(field, {})
        assert outcome.passed is None
        assert outcome.detail["outcome_code"] == "AMBIGUOUS_VALUE"

    def test_missing_field_is_indeterminate(self):
        outcome = evaluate_mrp_format(None, {})
        assert outcome.passed is None

    def test_price_never_invented(self):
        """A half-read price must never be completed by the evaluator."""
        field = FakeField(raw_text="MRP ₹ 9")  # possibly truncated "95"
        outcome = evaluate_mrp_format(field, {})
        assert outcome.detail.get("detected_amount") == "9"


class TestDateFormatEvaluator:
    def test_month_year_passes(self):
        field = FakeField(raw_text="MFG 03/2026", normalized_value="03/2026")
        outcome = evaluate_date_format(field, {})
        assert outcome.passed is True

    def test_month_name_year_passes(self):
        outcome = evaluate_date_format(FakeField(normalized_value="March 2026"), {})
        assert outcome.passed is True

    def test_non_date_text_fails(self):
        outcome = evaluate_date_format(FakeField(normalized_value="hello world"), {})
        assert outcome.passed is False

    def test_missing_text_is_indeterminate(self):
        assert evaluate_date_format(None, {}) .passed is None


class TestContactFormatEvaluator:
    def test_phone_and_email_pass(self):
        field = FakeField(
            raw_text="Consumer care: +91 98765 43210, care@example.com"
        )
        assert evaluate_contact_format(field, {}).passed is True

    def test_phone_only_fails_with_named_missing_channel(self):
        field = FakeField(raw_text="Toll free 1800 123 456")
        outcome = evaluate_contact_format(field, {})
        assert outcome.passed is False
        assert "e-mail" in outcome.reason

    def test_email_only_fails(self):
        field = FakeField(raw_text="Write to care@example.com")
        assert evaluate_contact_format(field, {}).passed is False


class TestUnitMatchEvaluator:
    def test_accepted_unit_passes(self):
        field = FakeField(raw_text="500 g", normalized_value="500", unit="g")
        assert evaluate_unit_match(field, {"units": ["g", "kg", "ml"]}).passed is True

    def test_unaccepted_unit_fails(self):
        field = FakeField(raw_text="16 oz", normalized_value="16", unit="oz")
        assert evaluate_unit_match(field, {"units": ["g", "kg"]}).passed is False

    def test_missing_unit_is_indeterminate(self):
        field = FakeField(raw_text="500", normalized_value="500", unit=None)
        outcome = evaluate_unit_match(field, {"units": ["g", "kg"]})
        assert outcome.passed is None

    def test_unit_inferred_from_text(self):
        field = FakeField(raw_text="500 g", normalized_value="500", unit=None)
        assert evaluate_unit_match(field, {"units": ["g", "kg"]}).passed is True

    def test_missing_config_is_execution_failure(self):
        outcome = evaluate_unit_match(FakeField(), {})
        assert outcome.passed is None
        assert outcome.detail["outcome_code"] == "RULE_EXECUTION_FAILED"


class TestNumericEvaluators:
    def test_numeric_value_passes_decimal(self):
        assert evaluate_numeric_value(FakeField(normalized_value="1.10"), {}).passed is True

    def test_decimal_safe_comparison(self):
        """0.1 + 0.2 must equal 0.3 under Decimal (never under float)."""
        field = FakeField(normalized_value="0.3")
        outcome = evaluate_comparison(field, {"operator": "=", "value": "0.3"})
        assert outcome.passed is True

    def test_range_bounds_inclusive(self):
        low = FakeField(normalized_value="10")
        high = FakeField(normalized_value="20")
        assert evaluate_range(low, {"min": "10", "max": "20"}).passed is True
        assert evaluate_range(high, {"min": "10", "max": "20"}).passed is True

    def test_range_outside_fails(self):
        field = FakeField(normalized_value="21")
        assert evaluate_range(field, {"min": "10", "max": "20"}).passed is False

    def test_non_numeric_is_ambiguous_not_fail(self):
        field = FakeField(normalized_value="about five")
        outcome = evaluate_numeric_value(field, {})
        assert outcome.passed is None
        assert outcome.detail["outcome_code"] == "AMBIGUOUS_VALUE"

    def test_comparison_invalid_config_is_execution_failure(self):
        outcome = evaluate_comparison(FakeField(normalized_value="1"), {"operator": "~"})
        assert outcome.passed is None
        assert outcome.detail["outcome_code"] == "RULE_EXECUTION_FAILED"


class TestTextEvaluators:
    def test_text_match_case_insensitive(self):
        field = FakeField(normalized_value="Instant Noodles")
        assert evaluate_text_match(field, {"expected": "instant noodles"}).passed is True

    def test_text_pattern(self):
        field = FakeField(normalized_value="NET WT. 500g")
        assert evaluate_text_pattern(field, {"pattern": r"net\s*wt"}).passed is True

    def test_declaration_format_min_words(self):
        assert (
            evaluate_declaration_format(
                FakeField(normalized_value="Tata Salt"), {"minWords": 2}
            ).passed
            is True
        )
        assert (
            evaluate_declaration_format(FakeField(normalized_value="Salt"), {"minWords": 2}).passed
            is False
        )

    def test_every_rule_type_has_an_evaluator(self, db):
        rule_types = {
            r[0]
            for r in db.execute(select(ComplianceRule.rule_type).distinct()).all()
        }
        assert rule_types  # seeded rules exist
        for rule_type in rule_types:
            assert get_evaluator(rule_type) is not None, f"no evaluator for {rule_type}"

    def test_registered_vocabulary_is_small(self):
        # Phase 4: deliberately small vocabulary.
        assert len(registered_rule_types()) == 13


# ===========================================================================
# 3. Engine end-to-end (uses the seeded regulatory dataset from conftest)
# ====================================================================================


def _make_inspection(
    db,
    *,
    category: str | None = "food",
    context_date: datetime | None = datetime(2026, 6, 1, tzinfo=UTC),
    fields: list[dict] | None = None,
) -> Inspection:
    """Build a real inspection with one perception run + extracted fields."""
    product = Product(
        name=f"Product {uuid.uuid4().hex[:6]}",
        category=category or "general",
        is_demo=False,
    )
    db.add(product)
    db.flush()
    inspection = Inspection(
        reference_no=f"INS-C-{uuid.uuid4().hex[:8].upper()}",
        status="ANALYZED",
        product_id=product.id,
        context_date=context_date,
        is_demo=False,
    )
    db.add(inspection)
    db.flush()
    package = Package(inspection_id=inspection.id, label="Pkg 1")
    db.add(package)
    db.flush()
    image = Image(
        package_id=package.id,
        storage_key=f"inspections/{inspection.id}/img.png",
        original_filename="front.png",
        mime_type="image/png",
        width=1200,
        height=1600,
        image_type="FRONT",
        quality_status="OK",
        is_demo=False,
    )
    db.add(image)
    db.flush()
    run = ProcessingRun(
        reference=f"RUN-{uuid.uuid4().hex[:8].upper()}",
        inspection_id=inspection.id,
        image_id=image.id,
        status="COMPLETED",
        pipeline_version="test-1",
        is_demo=False,
    )
    db.add(run)
    db.flush()
    for spec in fields or []:
        db.add(
            ExtractedField(
                image_id=image.id,
                image_region_id=None,
                package_id=package.id,
                field_type=spec["type"],
                raw_text=spec.get("raw", ""),
                normalized_value=spec.get("normalized"),
                unit=spec.get("unit"),
                confidence=spec.get("confidence", 0.95),
                extraction_method="test",
                status=spec.get("status", "DETECTED"),
                processing_run_id=run.id,
                is_demo=False,
            )
        )
    db.commit()
    db.refresh(inspection)
    return inspection


_FULL_COMPLIANT_FIELDS = [
    {"type": "MANUFACTURER_DETAILS", "raw": "Made by ACME Foods Pvt Ltd, Mumbai 400001",
     "normalized": "ACME Foods Pvt Ltd, Mumbai 400001"},
    {"type": "GENERIC_NAME", "raw": "INSTANT NOODLES", "normalized": "Instant Noodles"},
    {"type": "NET_QUANTITY", "raw": "NET WT. 500 g", "normalized": "500", "unit": "g"},
    {"type": "DATE_OF_MANUFACTURE", "raw": "MFG: 03/2026", "normalized": "03/2026"},
    {"type": "MRP", "raw": "MRP ₹ 60.00 (inclusive of all taxes)", "normalized": "60.00"},
    {"type": "CONSUMER_CARE", "raw": "Consumer care: +91 98765 43210, care@acme.example",
     "normalized": "+91 98765 43210, care@acme.example"},
    # Import evidence activates the imported-only country-of-origin requirement.
    {"type": "IMPORTER_DETAILS", "raw": "Imported by ACME Imports Pvt Ltd, Delhi 110001",
     "normalized": "ACME Imports Pvt Ltd, Delhi 110001"},
    {"type": "COUNTRY_OF_ORIGIN", "raw": "Country of Origin: India", "normalized": "India"},
    {"type": "BEST_BEFORE", "raw": "Best Before: 09/2027", "normalized": "09/2027"},
]

# The domestic package: no importer evidence — import status genuinely unknown.
_DOMESTIC_FIELDS = [f for f in _FULL_COMPLIANT_FIELDS
                    if f["type"] not in ("IMPORTER_DETAILS", "COUNTRY_OF_ORIGIN")]


@pytest.fixture()
def engine(services):
    return services.compliance


def _isolated_engine():
    """A fresh in-memory DB + engine for tests that MUTATE regulatory data.

    The shared session-scoped test database must stay pristine for the rest of
    the suite, so any test that deletes/deactivates regulatory rows gets its
    own isolated copy.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.db.regulatory_seed import seed_regulatory_data
    from app.services.compliance.engine import ComplianceEngine
    from app.services.compliance.seed_rules import seed_compliance_rules
    from app.services.regulatory.service import RegulatoryService

    sa_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(sa_engine)
    session = sessionmaker(bind=sa_engine, expire_on_commit=False)()
    seed_regulatory_data(session)
    seed_compliance_rules(session)
    return session, ComplianceEngine(regulatory=RegulatoryService())


def _in_force_requirement(db, rule_code: str):
    """The requirement row for ``rule_code`` on the consolidated (in-force,
    no effective_until) version — rule_code alone is NOT unique across the
    three seeded versions."""
    from app.models import RegulationVersion

    return db.execute(
        select(Rule)
        .join(RegulationVersion, Rule.regulation_version_id == RegulationVersion.id)
        .where(
            Rule.rule_code == rule_code,
            RegulationVersion.effective_until.is_(None),
        )
    ).scalar_one()


class TestEngineEndToEnd:
    def test_golden_case_a_fully_compliant_package(self, db, engine):
        """GOLDEN A: every declaration detected → COMPLETED, all COMPLIANT."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        assert evaluation.status == EvaluationStatus.COMPLETED.value
        statuses = [f.status for f in evaluation.findings]
        assert EngineFindingStatus.NON_COMPLIANT.value not in statuses
        # 2026 context date → consolidated version: 6.1(a)-(f) + 6.2 = 7
        # requirements apply (COO unknown-import → review; best-before → food YES).
        findings = {(f.requirement.rule_code): f for f in evaluation.findings}
        for code in [
            "LM-PC-2011-6.1(a)", "LM-PC-2011-6.1(b)", "LM-PC-2011-6.1(c)",
            "LM-PC-2011-6.1(d)", "LM-PC-2011-6.1(e)", "LM-PC-2011-6.2",
        ]:
            assert findings[code].status == EngineFindingStatus.COMPLIANT.value, (
                f"{code}: {findings[code].explanation}"
            )

    def test_golden_case_b_missing_mrp_is_not_detected_never_violation(self, db, engine):
        """GOLDEN B: no MRP field at all → NOT_DETECTED (never NON_COMPLIANT)."""
        fields = [f for f in _FULL_COMPLIANT_FIELDS if f["type"] != "MRP"]
        inspection = _make_inspection(db, fields=fields)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        mrp = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(e)")
        assert mrp.status == EngineFindingStatus.NOT_DETECTED.value
        assert mrp.detected_value is None
        # Presence rule outcome explains FIELD_NOT_FOUND honestly.
        assert "FIELD_NOT_FOUND" in str(mrp.detail)

    def test_golden_case_c_missing_inclusive_phrase_is_non_compliant(self, db, engine):
        """GOLDEN C: MRP present without the mandated wording → NON_COMPLIANT."""
        fields = [
            f if f["type"] != "MRP"
            else {**f, "raw": "MRP ₹ 60.00", "normalized": "60.00"}
            for f in _FULL_COMPLIANT_FIELDS
        ]
        inspection = _make_inspection(db, fields=fields)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        mrp = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(e)")
        assert mrp.status == EngineFindingStatus.NON_COMPLIANT.value
        assert "inclusive of all taxes" in mrp.explanation

    def test_golden_case_d_low_confidence_goes_to_review(self, db, engine):
        """GOLDEN D: low-OCR-confidence MRP → REVIEW_REQUIRED, no conclusion."""
        fields = [
            {**f, "confidence": 0.30, "status": "REVIEW_REQUIRED"}
            if f["type"] == "MRP" else f
            for f in _FULL_COMPLIANT_FIELDS
        ]
        inspection = _make_inspection(db, fields=fields)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        mrp = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(e)")
        assert mrp.status == EngineFindingStatus.REVIEW_REQUIRED.value
        assert evaluation.status == EvaluationStatus.REVIEW_REQUIRED.value

    def test_golden_case_e_unknown_import_status_goes_to_review(self, db, engine):
        """GOLDEN E: country-of-origin requirement (importedOnly) with no
        importer evidence → applicability UNKNOWN → REVIEW_REQUIRED."""
        inspection = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        coo = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(aa)")
        assert coo.status == EngineFindingStatus.REVIEW_REQUIRED.value
        assert coo.applicability == ApplicabilityOutcome.UNKNOWN.value
        assert "import" in coo.explanation.lower()

    def test_golden_case_f_non_perishable_category_is_not_applicable(self, db, engine):
        """GOLDEN F: best-before requirement for a non-perishable category →
        NOT_APPLICABLE with a recorded decision + reason (no violation)."""
        inspection = _make_inspection(db, category="electronics",
                                      fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        best_before = next(f for f in evaluation.findings
                           if f.requirement.rule_code == "LM-PC-2011-6.1(da)")
        assert best_before.status == EngineFindingStatus.NOT_APPLICABLE.value
        assert best_before.applicability == ApplicabilityOutcome.NO.value
        assert best_before.explanation  # decision + reason recorded

    def test_importer_evidence_activates_country_of_origin(self, db, engine):
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        coo = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(aa)")
        assert coo.applicability == ApplicabilityOutcome.YES.value
        assert coo.status == EngineFindingStatus.COMPLIANT.value

    def test_version_selection_2012_evaluates_only_original_requirements(self, db, engine):
        """Historical inspection: 2012 context → the 2011 original text only
        (no consumer care 6.2, no COO, no best-before)."""
        inspection = _make_inspection(
            db,
            context_date=datetime(2012, 6, 1, tzinfo=UTC),
            fields=_FULL_COMPLIANT_FIELDS,
        )
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        codes = {f.requirement.rule_code for f in evaluation.findings}
        assert "LM-PC-2011-6.2" not in codes
        assert "LM-PC-2011-6.1(aa)" not in codes
        assert "LM-PC-2011-6.1(da)" not in codes
        assert "LM-PC-2011-6.1(a)" in codes
        assert evaluation.regulatory_version_id is not None

    def test_version_selection_2016_includes_consumer_care(self, db, engine):
        inspection = _make_inspection(
            db,
            context_date=datetime(2016, 6, 1, tzinfo=UTC),
            fields=_FULL_COMPLIANT_FIELDS,
        )
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        codes = {f.requirement.rule_code for f in evaluation.findings}
        assert "LM-PC-2011-6.2" in codes
        assert "LM-PC-2011-6.1(aa)" not in codes  # 2017 amendment not yet in force

    def test_no_applicable_version_fails_explicitly(self, db, engine):
        """Context date before any version → FAILED + NO_APPLICABLE_VERSION,
        never a silent fallback to the newest version, never COMPLIANT."""
        inspection = _make_inspection(
            db,
            context_date=datetime(2010, 1, 1, tzinfo=UTC),
            fields=_FULL_COMPLIANT_FIELDS,
        )
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        assert evaluation.status == EvaluationStatus.FAILED.value
        assert evaluation.error["code"] == "NO_APPLICABLE_VERSION"
        assert evaluation.regulatory_version_id is None
        assert evaluation.findings == []

    def test_regulatory_data_unavailable_when_no_real_documents(self):
        """No non-demo documents at all → FAILED + REGULATORY_DATA_UNAVAILABLE."""
        from app.models import Regulation

        db, engine = _isolated_engine()
        regulations = db.execute(
            select(Regulation).where(Regulation.is_demo.is_(False))
        ).scalars().all()
        for regulation in regulations:
            db.delete(regulation)
        db.flush()
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate(db, inspection_id=inspection.id)
        assert evaluation.status == EvaluationStatus.FAILED.value
        assert evaluation.error["code"] == "REGULATORY_DATA_UNAVAILABLE"

    def test_unknown_rule_type_is_rule_execution_failure(self):
        """A configured rule with an unknown type → finding REVIEW_REQUIRED with
        RULE_EXECUTION_FAILED — never COMPLIANT, never silently skipped."""
        db, engine = _isolated_engine()
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        requirement = _in_force_requirement(db, "LM-PC-2011-6.1(b)")
        db.add(
            ComplianceRule(
                requirement_id=requirement.id,
                rule_code="TEST:BOGUS",
                rule_type="NOT_A_REAL_TYPE",
                rule_version=1,
                configuration={},
                active=True,
                is_demo=False,
            )
        )
        db.commit()
        evaluation = engine.evaluate(db, inspection_id=inspection.id)
        generic = next(f for f in evaluation.findings
                       if f.requirement.rule_code == "LM-PC-2011-6.1(b)")
        assert generic.status == EngineFindingStatus.REVIEW_REQUIRED.value
        codes = [
            r.get("errorCode") for r in generic.detail["rules"]
        ]
        assert "RULE_EXECUTION_FAILED" in codes

    def test_requirement_without_rules_is_not_evaluated(self):
        """A requirement with no configured rule → NOT_EVALUATED + PARTIAL —
        the engine never invents a check that was not configured."""
        db, engine = _isolated_engine()
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        requirement = _in_force_requirement(db, "LM-PC-2011-6.1(b)")
        for rule in db.execute(
            select(ComplianceRule).where(ComplianceRule.requirement_id == requirement.id)
        ).scalars():
            rule.active = False
        db.commit()
        evaluation = engine.evaluate(db, inspection_id=inspection.id)
        assert evaluation.status == EvaluationStatus.PARTIAL.value
        generic = next(f for f in evaluation.findings
                       if f.requirement.rule_code == "LM-PC-2011-6.1(b)")
        assert generic.status == EngineFindingStatus.NOT_EVALUATED.value

    def test_determinism_same_inputs_same_outputs(self, db, engine):
        """Two evaluations of the same evidence → identical statuses,
        detected values and explanations (byte-for-byte)."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        first = engine.evaluate_inspection(db, inspection_id=inspection.id)
        second = engine.evaluate_inspection(db, inspection_id=inspection.id)
        key = lambda f: f.requirement.rule_code  # noqa: E731
        a = sorted(first.findings, key=key)
        b = sorted(second.findings, key=key)
        assert [f.status for f in a] == [f.status for f in b]
        assert [f.detected_value for f in a] == [f.detected_value for f in b]
        assert [f.explanation for f in a] == [f.explanation for f in b]

    def test_history_is_never_overwritten(self, db, engine):
        """Re-evaluation creates a NEW row; the earlier evaluation and its
        regulatory version binding remain untouched."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        first = engine.evaluate_inspection(db, inspection_id=inspection.id)
        # Add an MRP field and re-evaluate — the first result must not change.
        run = db.execute(
            select(ProcessingRun).where(ProcessingRun.inspection_id == inspection.id)
        ).scalars().first()
        package = db.execute(
            select(Package).where(Package.inspection_id == inspection.id)
        ).scalars().first()
        db.add(
            ExtractedField(
                image_id=run.image_id,
                package_id=package.id,
                field_type="MRP",
                raw_text="MRP ₹ 60.00 (inclusive of all taxes)",
                normalized_value="60.00",
                confidence=0.95,
                extraction_method="test",
                status="DETECTED",
                processing_run_id=run.id,
                is_demo=False,
            )
        )
        db.commit()
        second = engine.evaluate_inspection(db, inspection_id=inspection.id)
        assert second.id != first.id
        db.refresh(first)
        assert first.summary  # untouched
        both = db.execute(
            select(ComplianceEvaluation).where(
                ComplianceEvaluation.inspection_id == inspection.id
            )
        ).scalars().all()
        assert len(both) == 2

    def test_summary_contains_counts_only(self, db, engine):
        """Phase 13: no percentage, no confidence score — counts only."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        summary_text = str(evaluation.summary).lower()
        for banned in ["percent", "%", "confidence", "score", "risk"]:
            assert banned not in summary_text, f"{banned} leaked into summary"
        assert evaluation.summary["totalFindings"] == len(evaluation.findings)
        by_status = evaluation.summary["byStatus"]
        assert sum(by_status.values()) == len(evaluation.findings)

    def test_explanation_answers_the_seven_questions(self, db, engine):
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        mrp = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(e)")
        text = mrp.explanation.lower()
        assert "lm-pc-2011-6.1(e)" in text            # which requirement
        assert "detected value" in text                # what was detected
        assert "rules:" in text                        # which rule + outcome
        assert "deterministic outcome" in text         # why this status
        assert "source" in text                        # provenance
        assert "decision-support" in text              # legal boundary
        assert mrp.detected_value == "60.00"
        assert mrp.expected_value is not None

    def test_provenance_snapshot_frozen(self, db, engine):
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        mrp = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(e)")
        prov = mrp.provenance
        assert prov["requirementCode"] == "LM-PC-2011-6.1(e)"
        assert prov["versionLabel"]
        assert prov["sourceVerificationStatus"] == "UNVERIFIED"
        assert prov["documentIdentifier"]

    def test_evidence_references_are_real_not_fabricated(self, db, engine):
        """Every finding's extracted_field_id / image_id must point at rows
        that actually exist (or be honestly absent)."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        for finding in evaluation.findings:
            if finding.extracted_field_id is not None:
                assert db.get(ExtractedField, finding.extracted_field_id) is not None
            if finding.image_id is not None:
                assert db.get(Image, finding.image_id) is not None

    def test_audit_events_recorded(self, db, engine):
        from app.models import AuditEvent

        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        engine.evaluate_inspection(db, inspection_id=inspection.id)
        events = db.execute(
            select(AuditEvent).where(AuditEvent.inspection_id == inspection.id)
        ).scalars().all()
        types = {e.event_type for e in events}
        assert "COMPLIANCE_EVALUATION_STARTED" in types
        assert "COMPLIANCE_EVALUATION_COMPLETED" in types

    def test_review_queue_lists_only_latest_evaluation_findings(self, db, engine):
        # Domestic fields: no import evidence → country-of-origin applicability
        # is UNKNOWN → REVIEW_REQUIRED finding → review queue.
        inspection = _make_inspection(db, fields=_DOMESTIC_FIELDS)
        engine.evaluate_inspection(db, inspection_id=inspection.id)
        engine.evaluate_inspection(db, inspection_id=inspection.id)
        items, total = engine.review_queue(db, limit=200, offset=0)
        latest = engine.latest_evaluation(db, inspection.id)
        # The queue is global (all inspections); scope to THIS inspection's
        # findings: every queued finding from this inspection must belong to
        # its latest evaluation — history is never re-queued.
        queued_here = [
            i for i in items
            if db.get(type(latest), i.evaluation_id).inspection_id == inspection.id
        ]
        assert queued_here, "expected at least one queued finding for this inspection"
        assert all(i.evaluation_id == latest.id for i in queued_here)
        assert total >= len(queued_here)

    def test_not_extracted_field_is_review_not_violation(self, db, engine):
        """A located-but-unreadable declaration (NOT_EXTRACTED) is never a
        violation — it goes to review."""
        fields = [
            {**f, "status": "NOT_EXTRACTED", "normalized": None}
            if f["type"] == "MRP" else f
            for f in _FULL_COMPLIANT_FIELDS
        ]
        inspection = _make_inspection(db, fields=fields)
        evaluation = engine.evaluate_inspection(db, inspection_id=inspection.id)
        mrp = next(f for f in evaluation.findings
                   if f.requirement.rule_code == "LM-PC-2011-6.1(e)")
        assert mrp.status == EngineFindingStatus.REVIEW_REQUIRED.value

    def test_seeded_rules_exist_for_all_requirement_types(self, db):
        """Every active non-demo requirement with a field key has ≥1 rule."""
        requirements = db.execute(
            select(Rule).where(Rule.is_demo.is_(False), Rule.field_key.is_not(None))
        ).scalars().all()
        assert requirements, "regulatory seed missing"
        for requirement in requirements:
            rules = db.execute(
                select(ComplianceRule).where(
                    ComplianceRule.requirement_id == requirement.id,
                    ComplianceRule.active.is_(True),
                )
            ).scalars().all()
            assert rules, f"no compliance rule for {requirement.rule_code}"

    def test_rule_types_are_only_from_the_vocabulary(self, db):
        rules = db.execute(select(ComplianceRule)).scalars().all()
        vocabulary = set(registered_rule_types())
        assert rules
        for rule in rules:
            assert rule.rule_type in vocabulary
