"""Regulatory data-quality validation (Prompt 5, Phase 13).

Structural validation of the regulatory data layer, run by the seed/import
process (and available on demand). The contract is simple and strict:

* structural problems RAISE :class:`RegulatoryDataInvalidError` — regulatory
  data is never silently repaired;
* every issue carries a machine-readable ``code`` + ``detail`` so the failure
  is diagnosable.

Checks:
- duplicate requirements (same rule_code within one version)
- orphan requirements (missing / dangling version)
- missing version (version without document, document without source for
  non-demo rows)
- invalid effective dates (effective_until <= effective_from)
- overlapping effective windows between versions of one document
- unverified source used as authoritative (non-demo data under a source whose
  verification_status is not VERIFIED must explicitly declare that it is
  research-grade — i.e. carry a verification note; a VERIFIED flag flip is an
  audited admin action, never a side effect of seeding)
- missing provenance (non-demo requirements without source_reference or whose
  version/document/source chain is incomplete)
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import VerificationStatus
from app.core.errors import RegulatoryDataInvalidError
from app.core.logging import get_logger
from app.models import (
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
)

logger = get_logger(__name__)


def validate_regulatory_data(db: Session) -> list[dict]:
    """Return the list of structural issues found (empty list = healthy).

    Raises nothing by itself — callers decide. The seed/import wrapper
    :func:`assert_regulatory_data_quality` turns non-demo issues into a loud
    failure.
    """
    issues: list[dict] = []

    sources = {s.id: s for s in db.execute(select(RegulatorySource)).scalars()}
    documents = {d.id: d for d in db.execute(select(Regulation)).scalars()}
    versions = {v.id: v for v in db.execute(select(RegulationVersion)).scalars()}
    rules = list(db.execute(select(Rule)).scalars())

    # --- duplicate requirement codes within one version -------------------------
    codes: dict[tuple, int] = defaultdict(int)
    for rule in rules:
        codes[(rule.regulation_version_id, rule.rule_code)] += 1
    for (version_id, code), count in codes.items():
        if count > 1:
            issues.append(
                {
                    "code": "DUPLICATE_REQUIREMENT",
                    "detail": f"{code} appears {count} times in version {version_id}",
                }
            )

    # --- orphan requirements (dangling version) ---------------------------------
    for rule in rules:
        if rule.regulation_version_id not in versions:
            issues.append(
                {
                    "code": "ORPHAN_REQUIREMENT",
                    "detail": f"{rule.rule_code} references missing version "
                    f"{rule.regulation_version_id}",
                }
            )
        version = versions.get(rule.regulation_version_id)
        if version is not None and version.regulation_id not in documents:
            issues.append(
                {
                    "code": "MISSING_DOCUMENT",
                    "detail": f"{rule.rule_code}'s version references missing document",
                }
            )

    # --- invalid / overlapping effective dates -----------------------------------
    for version in versions.values():
        if (
            version.effective_from is not None
            and version.effective_until is not None
            and version.effective_until <= version.effective_from
        ):
            issues.append(
                {
                    "code": "INVALID_EFFECTIVE_DATE",
                    "detail": f"{version.version_label}: effective_until <= effective_from",
                }
            )

    by_document: dict[uuid.UUID, list[RegulationVersion]] = defaultdict(list)
    for version in versions.values():
        by_document[version.regulation_id].append(version)
    for document_id, doc_versions in by_document.items():
        ordered = sorted(
            (v for v in doc_versions if v.effective_from is not None),
            key=lambda v: v.effective_from,
        )
        for current, following in zip(ordered, ordered[1:], strict=False):
            overlap = current.effective_until is None or (
                current.effective_until > following.effective_from
            )
            if overlap:
                issues.append(
                    {
                        "code": "OVERLAPPING_VERSIONS",
                        "detail": (
                            f"document {document_id}: {current.version_label} overlaps "
                            f"{following.version_label}"
                        ),
                    }
                )

    # --- provenance chain completeness + verification honesty --------------------
    for rule in rules:
        if rule.is_demo:
            continue  # demo rows are explicitly fictional; nothing to prove
        version = versions.get(rule.regulation_version_id)
        document = documents.get(version.regulation_id) if version else None
        if not rule.source_reference:
            issues.append(
                {
                    "code": "MISSING_PROVENANCE",
                    "detail": f"{rule.rule_code} has no source_reference citation",
                }
            )
        if document is None or document.source_id is None or document.source_id not in sources:
            issues.append(
                {
                    "code": "MISSING_SOURCE",
                    "detail": f"{rule.rule_code}: document has no resolved regulatory source",
                }
            )
            continue
        source = sources[document.source_id]
        if source.verification_status != VerificationStatus.VERIFIED.value and not (
            source.verification_note and source.verification_note.strip()
        ):
            issues.append(
                {
                    "code": "UNVERIFIED_SOURCE_WITHOUT_NOTE",
                    "detail": (
                        f"{rule.rule_code}: source {source.name} is "
                        f"{source.verification_status} but carries no verification note "
                        "explaining its provenance"
                    ),
                }
            )

    for document in documents.values():
        if not document.is_demo and (
            document.source_id is None or document.source_id not in sources
        ):
            issues.append(
                {
                    "code": "MISSING_SOURCE",
                    "detail": f"document {document.code} is non-demo but has no source",
                }
            )
        has_real_version = any(
            not v.is_demo for v in by_document.get(document.id, [])
        )
        if not document.is_demo and not has_real_version:
            issues.append(
                {
                    "code": "MISSING_VERSION",
                    "detail": f"document {document.code} is non-demo but has no versions",
                }
            )

    return issues


def assert_regulatory_data_quality(db: Session, *, context: str) -> None:
    """Fail loudly on structural issues (used by the seed/import process)."""
    issues = validate_regulatory_data(db)
    if issues:
        logger.error("regulatory_data_invalid", context=context, issues=issues)
        raise RegulatoryDataInvalidError(
            "Regulatory data failed structural validation — refusing to import.",
            details={"context": context, "issues": issues},
        )
