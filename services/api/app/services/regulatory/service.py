"""Regulatory service — version-aware rule resolution.

Answers the core question: *"which rule version applies to this inspection
context?"* by selecting, for a product category and a context date, the rule
rows whose regulation version is in force on that date (effective_from window).

Operates only on stored regulatory data (seeded from clearly-labelled DEMO
placeholders during the foundation phase). It never invents rules.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.enums import FieldType, RegulationVersionStatus, RuleStatus
from app.models import Regulation, RegulationVersion, Rule, RuleApplicability
from app.services.interfaces import RuleSpec

_WILDCARD_CATEGORIES = {"*", "any", "all", "general"}


class RegulatoryService:
    def get_applicable_rules(
        self, db: Session, *, category: str, context_date: datetime
    ) -> list[RuleSpec]:
        category_l = (category or "").strip().lower()

        stmt = (
            select(Rule, RuleApplicability, RegulationVersion)
            .join(RuleApplicability, RuleApplicability.rule_id == Rule.id)
            .join(RegulationVersion, RegulationVersion.id == Rule.regulation_version_id)
            .where(
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
    def _to_spec(rule: Rule, applicability: RuleApplicability, version: RegulationVersion) -> RuleSpec:
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
