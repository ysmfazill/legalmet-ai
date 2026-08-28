"""Regulatory seed for REAL Legal Metrology research data (Prompt 5).

This is the controlled regulatory import mechanism. It inserts research-grade
records for the Legal Metrology (Packaged Commodities) Rules, 2011 into the
Source → Document → Version → Requirement → Applicability hierarchy.

PROVENANCE & HONESTY CONTRACT
-----------------------------
The material here was researched (2026-08-28) from a legal database
reproduction of the Rules (indiankanoon.org, document 100694501). That
database itself flags that its copy "could not be verified" against the
original publication, and the official government repositories
(indiacode.nic.in / consumeraffairs.gov.in / egazette.gov.in) were not
reachable from the development environment at research time.

Therefore EVERY record seeded here is marked:

* ``is_demo = False``        — it is not the fictional DEMO dataset;
* verification_status = UNVERIFIED — it is research-grade, NOT verified
  against an authoritative government publication;
* an explicit verification_note recording the discovery source and what
  remains to be verified.

Nothing here is presented as an authoritative legal citation. Flipping a
source to VERIFIED is an audited ADMIN action that must only happen after a
human has checked the content against the official Gazette / India Code text.
Until then the data is ineligible for production compliance evaluation.

Content recorded (discovered, pending verification):
* Parent rules: G.S.R. 202(E), New Delhi, 7 March 2011, Ministry of Consumer
  Affairs (Department of Consumer Affairs); in force 1 April 2011 (Rule 1(2)).
* Amendments incorporated: G.S.R. 385(E) of 14 May 2015 (Rule 6(2) consumer
  care, effective 1 January 2016); G.S.R. 858(E) of 7 September 2016;
  G.S.R. 629(E) of 23 June 2017 (country-of-origin clause 6(1)(aa), best-
  before clause 6(1)(da), e-commerce definitions).
* Rule 6(1) declarations and Rule 6(2) consumer-care requirement.

The seed is deterministic, repeatable and idempotent: every record is matched
on its natural key (source name / document code / version label / rule code)
and re-running creates nothing new.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    DocumentType,
    FieldType,
    RegulationVersionStatus,
    RequirementType,
    RuleStatus,
    SourceType,
    VerificationStatus,
)
from app.core.logging import get_logger
from app.models import (
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
    RuleApplicability,
)
from app.services.regulatory.quality import assert_regulatory_data_quality

logger = get_logger(__name__)

_DISCOVERY_NOTE = (
    "Research-grade content discovered 2026-08-28 via a legal-database "
    "reproduction of the Rules (indiankanoon.org doc 100694501), which itself "
    "flags the text as unverifiable against the original publication. Official "
    "repositories (indiacode.nic.in, consumeraffairs.gov.in, egazette.gov.in) "
    "were unreachable from the development environment. Before this source is "
    "marked VERIFIED, a human must check every notification number, date and "
    "clause against the Gazette of India / India Code text."
)

_SOURCE_NAME = (
    "Department of Consumer Affairs — Legal Metrology (Packaged Commodities) publications"
)
_DOCUMENT_CODE = "LM-PC-RULES-2011"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def seed_regulatory_data(db: Session) -> dict[str, int]:
    """Idempotently seed the researched regulatory dataset. Returns counts."""
    source = _upsert_source(db)
    document = _upsert_document(db, source)
    versions = _upsert_versions(db, document)
    requirements = _upsert_requirements(db, versions)
    db.commit()

    # Loud structural validation — bad regulatory data never lands silently.
    assert_regulatory_data_quality(db, context="seed_regulatory_data")

    summary = {
        "sources": 1,
        "documents": 1,
        "versions": len(versions),
        "requirements": requirements,
    }
    logger.info("regulatory_seed_complete", **summary)
    return summary


# ---------------------------------------------------------------------------
# Source → Document → Version
# ---------------------------------------------------------------------------


def _upsert_source(db: Session) -> RegulatorySource:
    source = db.execute(
        select(RegulatorySource).where(RegulatorySource.name == _SOURCE_NAME)
    ).scalar_one_or_none()
    if source is not None:
        return source
    source = RegulatorySource(
        name=_SOURCE_NAME,
        authority=(
            "Department of Consumer Affairs, Ministry of Consumer Affairs, "
            "Food and Public Distribution, Government of India"
        ),
        source_type=SourceType.GOVERNMENT_DEPARTMENT.value,
        canonical_url="https://consumeraffairs.gov.in/",
        jurisdiction="IN",
        verification_status=VerificationStatus.UNVERIFIED.value,
        verification_note=_DISCOVERY_NOTE,
    )
    db.add(source)
    db.flush()
    return source


def _upsert_document(db: Session, source: RegulatorySource) -> Regulation:
    document = db.execute(
        select(Regulation).where(Regulation.code == _DOCUMENT_CODE)
    ).scalar_one_or_none()
    if document is not None:
        return document
    document = Regulation(
        code=_DOCUMENT_CODE,
        title="Legal Metrology (Packaged Commodities) Rules, 2011 (as amended)",
        jurisdiction="IN",
        authority=(
            "Department of Consumer Affairs, Ministry of Consumer Affairs, "
            "Food and Public Distribution, Government of India"
        ),
        description=(
            "Declarations required on pre-packaged commodities under the Legal "
            "Metrology (Packaged Commodities) Rules, 2011, as amended. Recorded "
            "from research material pending verification against the official "
            "Gazette / India Code text — see the source's verification note."
        ),
        official_source_url="https://consumeraffairs.gov.in/",
        is_demo=False,
        source_id=source.id,
        document_identifier=(
            "G.S.R. 202(E) (parent rules; amendments: G.S.R. 385(E) 2015, "
            "G.S.R. 858(E) 2016, G.S.R. 629(E) 2017)"
        ),
        document_type=DocumentType.RULES.value,
        publication_date=_dt(2011, 3, 7),
        content_hash=None,  # pending: hash of the verified source text
    )
    db.add(document)
    db.flush()
    return document


# (label, status, effective_from, effective_until, publication_date, ref)
_VERSIONS = [
    (
        "2011 original",
        RegulationVersionStatus.SUPERSEDED,
        _dt(2011, 4, 1),
        _dt(2016, 1, 1),
        _dt(2011, 3, 7),
        "Legal Metrology (Packaged Commodities) Rules, 2011 — G.S.R. 202(E), "
        "7 March 2011, in force 1 April 2011 (Rule 1(2))",
    ),
    (
        "as amended by G.S.R. 385(E)/2015",
        RegulationVersionStatus.SUPERSEDED,
        _dt(2016, 1, 1),
        _dt(2017, 6, 23),
        _dt(2015, 5, 14),
        "G.S.R. 385(E), 14 May 2015 — Rule 6(2) consumer-care declaration "
        "substituted, effective 1 January 2016",
    ),
    (
        "as amended through G.S.R. 629(E)/2017 (consolidated)",
        RegulationVersionStatus.ACTIVE,
        _dt(2017, 6, 23),
        None,
        _dt(2017, 6, 23),
        "G.S.R. 629(E), 23 June 2017 — inserts Rule 6(1)(aa) country of origin "
        "and Rule 6(1)(da) best-before/use-by. Version boundaries are a "
        "conservative modelling choice (amendment commencement pending Gazette "
        "verification) and are recorded as such, not as verified legal dates.",
    ),
]


def _upsert_versions(db: Session, document: Regulation) -> dict[str, RegulationVersion]:
    versions: dict[str, RegulationVersion] = {}
    previous: RegulationVersion | None = None
    for label, status, eff_from, eff_until, pub_date, ref in _VERSIONS:
        version = db.execute(
            select(RegulationVersion).where(
                RegulationVersion.regulation_id == document.id,
                RegulationVersion.version_label == label,
            )
        ).scalar_one_or_none()
        if version is None:
            version = RegulationVersion(
                regulation_id=document.id,
                version_label=label,
                status=status.value,
                effective_from=eff_from,
                effective_until=eff_until,
                amendment_of_id=previous.id if previous else None,
                source_document_ref=ref,
                is_demo=False,
                publication_date=pub_date,
            )
            db.add(version)
            db.flush()
        versions[label] = version
        previous = version
    return versions


# ---------------------------------------------------------------------------
# Requirements (per version)
# ---------------------------------------------------------------------------
#
# (rule_code, source_reference, title, summary, field_key, expected_format,
#  category, condition_expression)

_BASE_PREFIX = "The Rules require, for pre-packaged commodities in retail sale: "

_V1_REQUIREMENTS = [
    (
        "LM-PC-2011-6.1(a)",
        "Rule 6(1)(a)",
        "Name and address of manufacturer / packer / importer",
        _BASE_PREFIX
        + "a definite, plain and conspicuous declaration of the name and address "
        "of the manufacturer, or of the packer where the packer is not the "
        "manufacturer; for imported packages, the name and address of the importer.",
        FieldType.MANUFACTURER_DETAILS.value,
        "Name and full postal address, labelled as manufacturer / packed by / "
        "imported by (Marketed-by branding has separate 'deemed manufacturer' "
        "consequences — see the Explanation to the clause).",
        "all",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
    ),
    (
        "LM-PC-2011-6.1(b)",
        "Rule 6(1)(b)",
        "Common or generic name of the commodity",
        _BASE_PREFIX
        + "the common or generic name of the commodity contained in the package; "
        "for packages containing multiple products, the name and number or "
        "quantity of each.",
        FieldType.GENERIC_NAME.value,
        "Plain-language commodity name (e.g. 'Instant Noodles'), not a brand name.",
        "all",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
    ),
    (
        "LM-PC-2011-6.1(c)",
        "Rule 6(1)(c)",
        "Net quantity declaration",
        _BASE_PREFIX
        + "the net quantity, in terms of the standard unit of weight or measure, "
        "or of number where the commodity is sold by count.",
        FieldType.NET_QUANTITY.value,
        "Standard unit (e.g. '500 g', '1 L', '10 pcs'); symbols per the Schedule.",
        "all",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
    ),
    (
        "LM-PC-2011-6.1(d)",
        "Rule 6(1)(d)",
        "Month and year of manufacture / pre-packing / import",
        _BASE_PREFIX
        + "the month and year of manufacture, pre-packing or import (with "
        "documented exemptions, e.g. certified seeds, and category-specific "
        "laws prevailing for food articles).",
        FieldType.DATE_OF_MANUFACTURE.value,
        "Month and year, rubber-stamped or printed (e.g. 'MFG: 03/2026').",
        "all",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
    ),
    (
        "LM-PC-2011-6.1(e)",
        "Rule 6(1)(e)",
        "Retail sale price (MRP) inclusive of all taxes",
        _BASE_PREFIX
        + "the retail sale price of the package, clearly showing that it is the "
        "maximum price inclusive of all taxes (with the prescribed paise "
        "rounding); the declaration must be in the 'MRP ... inclusive of all "
        "taxes' manner.",
        FieldType.MRP.value,
        "'MRP ₹__ (inclusive of all taxes)' — price in rupees, inclusive of all "
        "taxes; a sticker with a lower revised MRP may not conceal the original.",
        "all",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
    ),
    (
        "LM-PC-2011-6.1(f)",
        "Rule 6(1)(f)",
        "Dimensions of the commodity, where relevant",
        _BASE_PREFIX
        + "where sizes are relevant, the dimensions of the commodity (and of "
        "each piece when pieces differ).",
        FieldType.DIMENSIONS.value,
        "Size in the relevant standard unit (length / area), per piece where "
        "pieces differ.",
        "dimensional",
        {"commodity": ["textiles", "paper", "garments"], "packageType": "*",
         "saleContext": "RETAIL"},
    ),
]

_V2_ADDITIONS = [
    (
        "LM-PC-2011-6.2",
        "Rule 6(2) (as substituted by G.S.R. 385(E)/2015)",
        "Consumer care contact details",
        _BASE_PREFIX
        + "every package bears the name, address, telephone number and e-mail "
        "address of the person or office that can be contacted for consumer "
        "complaints.",
        FieldType.CONSUMER_CARE.value,
        "Name, address, telephone number and e-mail address of the consumer "
        "complaints contact.",
        "all",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL"},
    ),
]

_V3_ADDITIONS = [
    (
        "LM-PC-2011-6.1(aa)",
        "Rule 6(1)(aa) (inserted by G.S.R. 629(E)/2017)",
        "Country of origin for imported packages",
        _BASE_PREFIX
        + "for imported products, the name of the country of origin or "
        "manufacture or assembly.",
        FieldType.COUNTRY_OF_ORIGIN.value,
        "Country name (e.g. 'Country of Origin: ...') on imported pre-packaged "
        "commodities.",
        "imported",
        {"commodity": "*", "packageType": "*", "saleContext": "RETAIL",
         "importedOnly": True},
    ),
    (
        "LM-PC-2011-6.1(da)",
        "Rule 6(1)(da) (inserted by G.S.R. 629(E)/2017)",
        "Best-before / use-by date where applicable",
        _BASE_PREFIX
        + "for commodities that may become unfit for consumption with time, the "
        "'best before' or 'use by' date (date, month and year), except where "
        "another law provides for this.",
        FieldType.BEST_BEFORE.value,
        "'Best Before' / 'Use By' plus date, month and year.",
        "perishable",
        {"commodity": ["food", "consumables-with-shelf-life"], "packageType": "*",
         "saleContext": "RETAIL"},
    ),
]


def _upsert_requirements(db: Session, versions: dict[str, RegulationVersion]) -> int:
    by_label = [
        ("2011 original", _V1_REQUIREMENTS),
        ("as amended by G.S.R. 385(E)/2015", _V1_REQUIREMENTS + _V2_ADDITIONS),
        (
            "as amended through G.S.R. 629(E)/2017 (consolidated)",
            _V1_REQUIREMENTS + _V2_ADDITIONS + _V3_ADDITIONS,
        ),
    ]
    created = 0
    for label, requirements in by_label:
        version = versions[label]
        for code, ref, title, summary, field_key, fmt, category, condition in requirements:
            rule = db.execute(
                select(Rule).where(
                    Rule.regulation_version_id == version.id,
                    Rule.rule_code == code,
                )
            ).scalar_one_or_none()
            if rule is not None:
                continue
            rule = Rule(
                regulation_version_id=version.id,
                rule_code=code,
                title=title,
                requirement_summary=summary,
                validation_logic_ref="field_present",  # deterministic validator key
                evidence_requirement=(
                    "A clear image region showing the declaration, linked via the "
                    "perception evidence chain (field → region → OCR)."
                ),
                status=RuleStatus.ACTIVE.value,
                is_demo=False,
                requirement_type=RequirementType.DECLARATION.value,
                field_key=field_key,
                expected_format=fmt,
                mandatory=True,
                applicability_definition=condition,
                source_reference=ref,
            )
            db.add(rule)
            db.flush()
            db.add(
                RuleApplicability(
                    rule_id=rule.id,
                    product_category=category,
                    condition_expression=dict(condition),
                    is_demo=False,
                )
            )
            created += 1
    db.flush()
    return created
