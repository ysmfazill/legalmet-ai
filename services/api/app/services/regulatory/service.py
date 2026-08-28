"""Regulatory service — version-aware rule resolution + regulatory intelligence.

Two responsibilities:

1. (Prompt 1) ``get_applicable_rules`` answers *"which DEMO rule version applies
   to this inspection context?"* for the clearly-labelled demo compliance flow.
   It deliberately resolves only ``is_demo`` regulations so the demo flow's
   findings never mix in real (research-grade, unverified) requirements.

2. (Prompt 5) The regulatory-intelligence read/resolve layer over the
   Source → Document → Version → Requirement hierarchy: effective-date version
   selection with an explicit NO_APPLICABLE_VERSION state, provenance-bearing
   requirement queries, audited source verification updates, and the
   extracted-field → candidate-requirement mapping used by the workspace.

Nothing here evaluates compliance. The strongest statement this service makes
about a field/requirement pair is "candidate — applicability not evaluated,
awaiting the compliance engine".
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    AuditEventType,
    CandidateMappingStatus,
    FieldType,
    RegulationVersionStatus,
    RuleStatus,
    VerificationStatus,
    VersionSelectionStatus,
)
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models import (
    ExtractedField,
    Inspection,
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
    RuleApplicability,
)
from app.services.audit.service import AuditService
from app.services.interfaces import RuleSpec

logger = get_logger(__name__)

_WILDCARD_CATEGORIES = {"*", "any", "all", "general"}


class RegulatoryService:
    def __init__(self, audit: AuditService | None = None) -> None:
        # Audit is optional so the Prompt 1 composition (no audit arg) keeps
        # working; Prompt 5's registry wires the shared audit service in.
        self._audit = audit

    # ------------------------------------------------------------------
    # Prompt 1 — DEMO rule resolution (unchanged behaviour, demo-only data)
    # ------------------------------------------------------------------

    def get_applicable_rules(
        self, db: Session, *, category: str, context_date: datetime
    ) -> list[RuleSpec]:
        category_l = (category or "").strip().lower()
        stmt = (
            select(Rule, RuleApplicability, RegulationVersion)
            .join(RuleApplicability, RuleApplicability.rule_id == Rule.id)
            .join(RegulationVersion, RegulationVersion.id == Rule.regulation_version_id)
            .join(Regulation, Regulation.id == RegulationVersion.regulation_id)
            .where(
                Regulation.is_demo.is_(True),  # demo flow stays on demo data
                Rule.status == RuleStatus.ACTIVE.value,
                RegulationVersion.status.in_(
                    [
                        RegulationVersionStatus.ACTIVE.value,
                        RegulationVersionStatus.SUPERSEDED.value,
                    ]
                ),
                RegulationVersion.effective_from <= context_date,
                or_(
                    RegulationVersion.effective_until.is_(None),
                    RegulationVersion.effective_until > context_date,
                ),
            )
        )
        rows = db.execute(stmt).all()

        # Pick, per (regulation, rule_code), the in-force version with the
        # latest effective_from — the version-aware selection step.
        chosen: dict[tuple, tuple[Rule, RuleApplicability, RegulationVersion]] = {}
        for rule, applicability, version in rows:
            if not self._category_matches(category_l, applicability.product_category):
                continue
            key = (version.regulation_id, rule.rule_code)
            current = chosen.get(key)
            if current is None or self._newer(version, current[2]):
                chosen[key] = (rule, applicability, version)

        return [self._to_spec(rule, appl, version) for rule, appl, version in chosen.values()]

    # ------------------------------------------------------------------
    # Prompt 5 — sources
    # ------------------------------------------------------------------

    def list_sources(
        self,
        db: Session,
        *,
        verification_status: str | None = None,
        source_type: str | None = None,
    ) -> list[RegulatorySource]:
        stmt = select(RegulatorySource).order_by(RegulatorySource.name)
        if verification_status:
            stmt = stmt.where(RegulatorySource.verification_status == verification_status)
        if source_type:
            stmt = stmt.where(RegulatorySource.source_type == source_type)
        return list(db.execute(stmt).scalars().all())

    def get_source(self, db: Session, source_id: uuid.UUID) -> RegulatorySource:
        source = db.get(RegulatorySource, source_id)
        if source is None:
            raise NotFoundError(f"Regulatory source not found: {source_id}")
        return source

    def update_source_verification(
        self,
        db: Session,
        *,
        source_id: uuid.UUID,
        verification_status: str,
        verification_note: str | None,
        actor_id: uuid.UUID | None,
    ) -> RegulatorySource:
        """Audited verification-state change. ADMIN-only at the router.

        Raising to VERIFIED is the explicit human act that makes a source's
        data eligible for production compliance evaluation. The before/after
        states are preserved in the audit event.
        """
        try:
            VerificationStatus(verification_status)
        except ValueError as exc:
            raise ValidationError(
                f"Unknown verification status: {verification_status}",
                details={"allowed": [s.value for s in VerificationStatus]},
            ) from exc

        source = self.get_source(db, source_id)
        before = {
            "verificationStatus": source.verification_status,
            "verificationNote": source.verification_note,
        }
        if verification_status == VerificationStatus.VERIFIED.value and not (
            verification_note and verification_note.strip()
        ):
            raise ValidationError(
                "Marking a source VERIFIED requires a verification note recording "
                "how and against which official publication it was checked."
            )

        source.verification_status = verification_status
        if verification_note is not None:
            source.verification_note = verification_note
        db.flush()

        if self._audit is not None:
            self._audit.record(
                db,
                event_type=AuditEventType.REGULATORY_SOURCE_UPDATED,
                entity_type="regulatory_source",
                entity_id=source.id,
                actor_id=actor_id,
                payload={
                    "before": before,
                    "after": {
                        "verificationStatus": source.verification_status,
                        "verificationNote": source.verification_note,
                    },
                },
            )
        db.commit()
        db.refresh(source)
        return source

    # ------------------------------------------------------------------
    # Prompt 5 — documents + versions
    # ------------------------------------------------------------------

    def list_documents(
        self,
        db: Session,
        *,
        source_id: uuid.UUID | None = None,
        document_type: str | None = None,
        is_demo: bool | None = None,
    ) -> list[Regulation]:
        stmt = (
            select(Regulation)
            .options(selectinload(Regulation.versions))
            .order_by(Regulation.code)
        )
        if source_id is not None:
            stmt = stmt.where(Regulation.source_id == source_id)
        if document_type:
            stmt = stmt.where(Regulation.document_type == document_type)
        if is_demo is not None:
            stmt = stmt.where(Regulation.is_demo.is_(is_demo))
        return list(db.execute(stmt).scalars().all())

    def get_document(self, db: Session, document_id: uuid.UUID) -> Regulation:
        document = db.get(
            Regulation, document_id, options=(selectinload(Regulation.versions),)
        )
        if document is None:
            raise NotFoundError(f"Regulatory document not found: {document_id}")
        return document

    def list_versions(
        self,
        db: Session,
        *,
        document_id: uuid.UUID | None = None,
        status: str | None = None,
        effective_on: datetime | None = None,
    ) -> list[RegulationVersion]:
        stmt = select(RegulationVersion).order_by(
            RegulationVersion.effective_from.asc(), RegulationVersion.created_at.asc()
        )
        if document_id is not None:
            stmt = stmt.where(RegulationVersion.regulation_id == document_id)
        if status:
            stmt = stmt.where(RegulationVersion.status == status)
        if effective_on is not None:
            stmt = stmt.where(
                RegulationVersion.effective_from <= effective_on,
                or_(
                    RegulationVersion.effective_until.is_(None),
                    RegulationVersion.effective_until > effective_on,
                ),
            )
        return list(db.execute(stmt).scalars().all())

    def resolve_version(
        self, db: Session, *, document_id: uuid.UUID, at: datetime
    ) -> tuple[RegulationVersion | None, VersionSelectionStatus]:
        """Deterministic effective-date selection.

        Returns the version whose [effective_from, effective_until) window
        contains ``at``; ties resolved by latest effective_from. If no version
        is in force at ``at``, returns (None, NO_APPLICABLE_VERSION) — the
        resolver never silently falls back to the newest version.
        """
        matches = self.list_versions(db, document_id=document_id, effective_on=at)
        if not matches:
            return None, VersionSelectionStatus.NO_APPLICABLE_VERSION
        in_force = [v for v in matches if v.effective_from is not None]
        if not in_force:
            return None, VersionSelectionStatus.NO_APPLICABLE_VERSION
        chosen = max(in_force, key=lambda v: (v.effective_from, v.created_at))
        return chosen, VersionSelectionStatus.FOUND

    def current_version(
        self, db: Session, document_id: uuid.UUID
    ) -> tuple[RegulationVersion | None, VersionSelectionStatus]:
        return self.resolve_version(db, document_id=document_id, at=utcnow())

    # ------------------------------------------------------------------
    # Prompt 5 — requirements (with full provenance)
    # ------------------------------------------------------------------

    def list_requirements(
        self,
        db: Session,
        *,
        version_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        source_id: uuid.UUID | None = None,
        field_key: str | None = None,
        requirement_type: str | None = None,
        category: str | None = None,
        status: str | None = None,
        effective_on: datetime | None = None,
        current: bool | None = None,
        is_demo: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Rule], int]:
        stmt = (
            select(Rule)
            .join(RegulationVersion, RegulationVersion.id == Rule.regulation_version_id)
            .join(Regulation, Regulation.id == RegulationVersion.regulation_id)
        )
        count_stmt = stmt  # same filters; count applied below

        if version_id is not None:
            stmt = stmt.where(Rule.regulation_version_id == version_id)
            count_stmt = count_stmt.where(Rule.regulation_version_id == version_id)
        if document_id is not None:
            stmt = stmt.where(RegulationVersion.regulation_id == document_id)
            count_stmt = count_stmt.where(RegulationVersion.regulation_id == document_id)
        if source_id is not None:
            stmt = stmt.where(Regulation.source_id == source_id)
            count_stmt = count_stmt.where(Regulation.source_id == source_id)
        if field_key:
            stmt = stmt.where(Rule.field_key == field_key)
            count_stmt = count_stmt.where(Rule.field_key == field_key)
        if requirement_type:
            stmt = stmt.where(Rule.requirement_type == requirement_type)
            count_stmt = count_stmt.where(Rule.requirement_type == requirement_type)
        if status:
            stmt = stmt.where(Rule.status == status)
            count_stmt = count_stmt.where(Rule.status == status)
        if is_demo is not None:
            stmt = stmt.where(Rule.is_demo.is_(is_demo))
            count_stmt = count_stmt.where(Rule.is_demo.is_(is_demo))

        when = effective_on if effective_on is not None else (utcnow() if current else None)
        if when is not None:
            window = (
                RegulationVersion.effective_from <= when,
                or_(
                    RegulationVersion.effective_until.is_(None),
                    RegulationVersion.effective_until > when,
                ),
            )
            stmt = stmt.where(*window)
            count_stmt = count_stmt.where(*window)

        if category:
            stmt = stmt.join(RuleApplicability, RuleApplicability.rule_id == Rule.id).where(
                RuleApplicability.product_category == category
            )
            count_stmt = count_stmt.join(
                RuleApplicability, RuleApplicability.rule_id == Rule.id
            ).where(RuleApplicability.product_category == category)

        rows = list(
            db.execute(stmt.order_by(Rule.rule_code).limit(limit).offset(offset)).scalars()
        )
        total = len(list(db.execute(count_stmt).scalars()))
        return rows, total

    def get_requirement(
        self, db: Session, requirement_id: uuid.UUID
    ) -> tuple[Rule, RegulationVersion, Regulation, RegulatorySource | None]:
        rule = db.get(Rule, requirement_id)
        if rule is None:
            raise NotFoundError(f"Regulatory requirement not found: {requirement_id}")
        version = db.get(RegulationVersion, rule.regulation_version_id)
        document = db.get(Regulation, version.regulation_id)
        source = db.get(RegulatorySource, document.source_id) if document.source_id else None
        return rule, version, document, source

    # ------------------------------------------------------------------
    # Prompt 5 — candidate mapping (perception → regulations, NO evaluation)
    # ------------------------------------------------------------------

    def requirement_candidates_for_field(
        self, db: Session, *, field_type: str, at: datetime
    ) -> list[tuple[Rule, RegulationVersion, Regulation, RegulatorySource | None]]:
        """Candidate requirements whose field_key matches a perception field.

        Deterministic read-time join over the requirement definitions in force
        at ``at``. This produces CANDIDATES ONLY — applicability is not
        evaluated and no compliance conclusion is drawn (Prompt 6's engine
        will consume these definitions and decide).
        """
        rows, _total = self.list_requirements(
            db,
            field_key=field_type,
            effective_on=at,
            status=RuleStatus.ACTIVE.value,
            is_demo=False,
            limit=1000,
        )
        result: list[tuple[Rule, RegulationVersion, Regulation, RegulatorySource | None]] = []
        for rule in rows:
            version = db.get(RegulationVersion, rule.regulation_version_id)
            document = db.get(Regulation, version.regulation_id)
            source = (
                db.get(RegulatorySource, document.source_id) if document.source_id else None
            )
            result.append((rule, version, document, source))
        return result

    def field_candidates(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        on: datetime | None = None,
    ) -> dict:
        """Map an inspection's extracted fields to candidate requirements.

        Uses the version in force at the inspection's creation date by default
        (an inspection must eventually reference the version used during
        evaluation — Prompt 6). Output carries explicit markers:
        APPLICABILITY_NOT_EVALUATED and AWAITING_COMPLIANCE_ENGINE. Never a
        compliance verdict.
        """
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        context_date = on or inspection.created_at or utcnow()

        mapped: list[dict] = []
        for field in self._latest_fields(db, inspection_id):
            candidates = self.requirement_candidates_for_field(
                db, field_type=field.field_type, at=context_date
            )
            mapped.append(
                {
                    "field": field,
                    "candidates": candidates,
                    "mapping_status": CandidateMappingStatus.CANDIDATE.value,
                    "applicability_status": (
                        CandidateMappingStatus.APPLICABILITY_NOT_EVALUATED.value
                    ),
                    "evaluation_status": (
                        CandidateMappingStatus.AWAITING_COMPLIANCE_ENGINE.value
                    ),
                }
            )

        return {
            "inspection": inspection,
            "context_date": context_date,
            "fields": mapped,
        }

    @staticmethod
    def _latest_fields(db: Session, inspection_id: uuid.UUID) -> list[ExtractedField]:
        """Extracted fields from the LATEST perception run per image."""
        from app.models import ProcessingRun

        latest_run_per_image: dict[uuid.UUID, uuid.UUID] = {}
        for run_id, image_id in db.execute(
            select(ProcessingRun.id, ProcessingRun.image_id)
            .where(ProcessingRun.inspection_id == inspection_id)
            .order_by(ProcessingRun.created_at.desc())
        ):
            latest_run_per_image.setdefault(image_id, run_id)
        if not latest_run_per_image:
            return []
        keep = set(latest_run_per_image.values())
        stmt = (
            select(ExtractedField)
            .where(ExtractedField.processing_run_id.in_(keep))
            .order_by(ExtractedField.created_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Prompt 1 internals (unchanged)
    # ------------------------------------------------------------------

    @staticmethod
    def _category_matches(category: str, applicability_category: str) -> bool:
        appl = (applicability_category or "").strip().lower()
        if appl in _WILDCARD_CATEGORIES:
            return True
        if not category:
            return False
        return appl in category or category in appl

    @staticmethod
    def _newer(candidate: RegulationVersion, current: RegulationVersion) -> bool:
        if candidate.effective_from is None:
            return False
        if current.effective_from is None:
            return True
        return candidate.effective_from > current.effective_from

    @staticmethod
    def _to_spec(
        rule: Rule, applicability: RuleApplicability, version: RegulationVersion
    ) -> RuleSpec:
        cond = applicability.condition_expression or {}
        target_raw = cond.get("targetFieldType") or cond.get("target_field_type")
        target: FieldType | None = None
        if target_raw:
            try:
                target = FieldType(target_raw)
            except ValueError:
                target = None
        return RuleSpec(
            rule_id=rule.id,
            rule_version_id=version.id,
            rule_code=rule.rule_code,
            requirement_summary=rule.requirement_summary,
            validation_logic_ref=rule.validation_logic_ref,
            target_field_type=target,
            params=cond.get("params", {}) or {},
        )

    # --- Read helpers for the API -----------------------------------------

    def list_regulations(self, db: Session) -> list[Regulation]:
        stmt = select(Regulation).order_by(Regulation.code)
        return list(db.execute(stmt).scalars().all())

    def list_rules(self, db: Session, *, limit: int, offset: int) -> tuple[list[Rule], int]:
        total = db.execute(select(Rule)).scalars().all()
        stmt = select(Rule).order_by(Rule.rule_code).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars().all()), len(total)
