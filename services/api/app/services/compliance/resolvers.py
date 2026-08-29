"""Resolvers — each step of the compliance pipeline as a small, testable unit.

    RequirementResolver   which regulatory requirements are in force & checkable
    RuleResolver          which deterministic rule checks a requirement
    EvidenceResolver      which extracted field(s) evidence a requirement

All resolvers are read-only and deterministic: same DB state + same inputs →
same output. They never invent requirements, rules or evidence, and they never
silently fall back (a missing version/requirement is surfaced as an explicit
code the engine turns into FAILED / NO_APPLICABLE_REQUIREMENT).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RuleStatus
from app.models import (
    ComplianceRule,
    ExtractedField,
    ProcessingRun,
    Regulation,
    RegulationVersion,
    Rule,
)
from app.services.regulatory.service import RegulatoryService


@dataclass(frozen=True)
class VersionResolution:
    """Outcome of regulatory version selection for ONE evaluation."""

    version: RegulationVersion | None
    document: Regulation | None
    # "FOUND" | "NO_APPLICABLE_VERSION" (never a silent fallback to newest)
    status: str


class RequirementResolver:
    """Resolves the requirement set in force at the evaluation context date."""

    def __init__(self, regulatory: RegulatoryService) -> None:
        self._regulatory = regulatory

    def resolve_version(
        self, db: Session, *, at: datetime
    ) -> VersionResolution:
        """Deterministically select the non-demo regulation version in force.

        Uses the Prompt 5 resolver semantics ([effective_from, effective_until)
        window). If several non-demo documents exist, the FIRST document (by
        code) whose window matches is used and recorded; if none matches, the
        resolution is explicitly NO_APPLICABLE_VERSION.
        """
        documents = list(
            db.execute(
                select(Regulation)
                .where(Regulation.is_demo.is_(False))
                .order_by(Regulation.code.asc())
            ).scalars()
        )
        if not documents:
            return VersionResolution(None, None, "NO_REGULATORY_DATA")
        for document in documents:
            version, status = self._regulatory.resolve_version(
                db, document_id=document.id, at=at
            )
            if version is not None:
                return VersionResolution(version, document, "FOUND")
        return VersionResolution(None, documents[0], "NO_APPLICABLE_VERSION")

    def requirements_for_version(
        self, db: Session, version_id: uuid.UUID
    ) -> list[Rule]:
        """Active requirements of one version with a checkable field key.

        Requirements without a field_key cannot be checked against perception
        evidence and are returned separately by ``unchecked_requirements``.
        """
        return list(
            db.execute(
                select(Rule)
                .where(
                    Rule.regulation_version_id == version_id,
                    Rule.status == RuleStatus.ACTIVE.value,
                    Rule.is_demo.is_(False),
                    Rule.field_key.is_not(None),
                )
                .order_by(Rule.rule_code.asc())
            ).scalars()
        )

    def unchecked_requirements(
        self, db: Session, version_id: uuid.UUID
    ) -> list[Rule]:
        """Requirements with no field key — recordable but not checkable yet."""
        return list(
            db.execute(
                select(Rule)
                .where(
                    Rule.regulation_version_id == version_id,
                    Rule.status == RuleStatus.ACTIVE.value,
                    Rule.is_demo.is_(False),
                    Rule.field_key.is_(None),
                )
                .order_by(Rule.rule_code.asc())
            ).scalars()
        )


class RuleResolver:
    """Maps a regulatory requirement to its deterministic rule configuration."""

    def rules_for_requirement(
        self, db: Session, requirement_id: uuid.UUID
    ) -> list[ComplianceRule]:
        return list(
            db.execute(
                select(ComplianceRule)
                .where(
                    ComplianceRule.requirement_id == requirement_id,
                    ComplianceRule.active.is_(True),
                )
                .order_by(ComplianceRule.rule_code.asc())
            ).scalars()
        )


@dataclass(frozen=True)
class EvidenceBundle:
    """The perception evidence for one requirement over one inspection.

    ``fields`` are the extracted fields of the requirement's field key from the
    LATEST perception run per image — every candidate is kept (multiple images
    may show the same declaration); ``best`` is the deterministic primary
    field used for evaluation (highest confidence, then earliest created).
    ``searched_run_ids`` documents which runs were searched — the honest
    evidence behind a NOT_DETECTED finding.
    """

    field_key: str
    fields: list
    best: object | None
    searched_run_ids: list
    run_count: int


class EvidenceResolver:
    """Finds the extracted fields that evidence one requirement."""

    def latest_run_ids(self, db: Session, inspection_id: uuid.UUID) -> list:
        """Latest processing run per image for this inspection."""
        latest_run_per_image: dict = {}
        for run_id, image_id in db.execute(
            select(ProcessingRun.id, ProcessingRun.image_id)
            .where(ProcessingRun.inspection_id == inspection_id)
            .order_by(ProcessingRun.created_at.desc())
        ):
            latest_run_per_image.setdefault(image_id, run_id)
        return list(latest_run_per_image.values())

    def evidence_for(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        field_key: str,
    ) -> EvidenceBundle:
        run_ids = self.latest_run_ids(db, inspection_id)
        if not run_ids:
            return EvidenceBundle(field_key, [], None, [], 0)
        fields = list(
            db.execute(
                select(ExtractedField)
                .where(
                    ExtractedField.processing_run_id.in_(run_ids),
                    ExtractedField.field_type == field_key,
                )
                .order_by(ExtractedField.created_at.asc())
            ).scalars()
        )
        best = None
        if fields:
            # Deterministic primary evidence: highest confidence wins; ties are
            # broken by earliest creation (stable, reproducible).
            best = sorted(
                fields, key=lambda f: (-float(f.confidence or 0.0), f.created_at)
            )[0]
        return EvidenceBundle(field_key, fields, best, run_ids, len(run_ids))
