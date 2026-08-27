"""Demo data seeding (DEMO ONLY).

Populates login accounts and a **fictional, clearly-labelled** regulatory
dataset so the system is demonstrable end-to-end. Per the project's hard
constraints:

* No real Legal Metrology rule numbers are used — codes are ``DEMO-*``.
* No real government sources are cited — ``official_source_url`` is left unset.
* Every regulatory row is flagged ``is_demo=True`` and its text carries the
  "DEMO DATA — NOT LEGAL ADVICE" marker.

The dataset includes an amendment chain (v1 superseded by v2) precisely so the
version-aware rule selection can be demonstrated: analysing with an older
context date resolves the older rule set.

Seeding is idempotent — it checks for existing rows before inserting.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import FieldType, RegulationVersionStatus, RuleStatus, UserRole
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import (
    Regulation,
    RegulationVersion,
    Rule,
    RuleApplicability,
    User,
)

logger = get_logger(__name__)

_DEMO_MARK = "DEMO DATA — NOT LEGAL ADVICE."
_REGULATION_CODE = "DEMO-LM-PC"


def seed_demo_data(db: Session, settings: Settings) -> dict[str, int]:
    users = _seed_users(db, settings)
    regulations = _seed_regulations(db)
    db.commit()
    summary = {"users": users, "regulations": regulations}
    logger.info("seed_complete", **summary)
    return summary


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def _seed_users(db: Session, settings: Settings) -> int:
    # Passwords come from settings/env only — never hard-coded literals here.
    accounts = [
        (settings.demo_admin_email, settings.demo_admin_password, "Demo Administrator", UserRole.ADMIN),
        (settings.demo_inspector_email, settings.demo_inspector_password, "Demo Inspector", UserRole.INSPECTOR),
        ("supervisor@legalmet.local", settings.demo_inspector_password, "Demo Supervisor", UserRole.SUPERVISOR),
        ("auditor@legalmet.local", settings.demo_inspector_password, "Demo Auditor", UserRole.AUDITOR),
    ]
    created = 0
    for email, password, full_name, role in accounts:
        exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(
            User(
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=role.value,
                is_active=True,
            )
        )
        created += 1
    if created:
        db.flush()
    return created


# ---------------------------------------------------------------------------
# Regulatory dataset (fictional, version-aware)
# ---------------------------------------------------------------------------


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _seed_regulations(db: Session) -> int:
    existing = db.execute(
        select(Regulation).where(Regulation.code == _REGULATION_CODE)
    ).scalar_one_or_none()
    if existing is not None:
        return 0

    regulation = Regulation(
        code=_REGULATION_CODE,
        title="DEMO — Packaged Commodities Declarations (illustrative placeholder)",
        jurisdiction="IN",
        authority="DEMO Authority (placeholder — not an official source)",
        description=(
            "Fictional, illustrative rule set used to demonstrate the compliance "
            f"pipeline. Not derived from any official text. {_DEMO_MARK}"
        ),
        official_source_url=None,
        is_demo=True,
    )
    db.add(regulation)
    db.flush()

    # v1: superseded, in force 2011-04-01 .. 2023-01-01 (fewer declarations).
    v1 = RegulationVersion(
        regulation_id=regulation.id,
        version_label="DEMO v1 (2011)",
        status=RegulationVersionStatus.SUPERSEDED.value,
        effective_from=_dt(2011, 4, 1),
        effective_until=_dt(2023, 1, 1),
        source_document_ref="DEMO placeholder — no real source",
        is_demo=True,
    )
    db.add(v1)
    db.flush()

    # v2: active, in force from 2023-01-01, amends v1 (adds two declarations).
    v2 = RegulationVersion(
        regulation_id=regulation.id,
        version_label="DEMO v2 (2023 amendment)",
        status=RegulationVersionStatus.ACTIVE.value,
        effective_from=_dt(2023, 1, 1),
        effective_until=None,
        amendment_of_id=v1.id,
        source_document_ref="DEMO placeholder — no real source",
        is_demo=True,
    )
    db.add(v2)
    db.flush()

    # (rule_code, title, requirement, validator, target_field, params, applies_to)
    v1_rules = [
        ("DEMO-MRP", "MRP declaration present",
         "A retail sale price declaration must be present on the label.",
         "field_present", FieldType.MRP, {}, ["general"]),
        ("DEMO-NETQTY", "Net quantity declaration present",
         "A net quantity declaration must be present on the label.",
         "field_present", FieldType.NET_QUANTITY, {}, ["general"]),
        ("DEMO-MFG", "Manufacturer/packer details present",
         "Manufacturer or packer details must be present and non-trivial.",
         "non_empty_text", FieldType.MANUFACTURER_DETAILS, {"min_length": 5}, ["general"]),
    ]
    # v2 keeps v1's rules and adds country-of-origin + consumer-care, plus a
    # food-only best-before rule (to demonstrate category-based applicability).
    v2_rules = v1_rules + [
        ("DEMO-COO", "Country of origin present",
         "A country of origin declaration must be present on the label.",
         "field_present", FieldType.COUNTRY_OF_ORIGIN, {}, ["general"]),
        ("DEMO-CARE", "Consumer care details present",
         "Consumer care contact details must be present on the label.",
         "field_present", FieldType.CONSUMER_CARE, {}, ["general"]),
        ("DEMO-BB", "Best-before declaration present (food)",
         "A best-before declaration must be present for food commodities.",
         "field_present", FieldType.BEST_BEFORE, {}, ["food"]),
    ]

    count = 0
    for version, ruleset in ((v1, v1_rules), (v2, v2_rules)):
        for rule_code, title, requirement, validator, target, params, applies_to in ruleset:
            rule = Rule(
                regulation_version_id=version.id,
                rule_code=rule_code,
                title=f"{title} (DEMO)",
                requirement_summary=f"{requirement} {_DEMO_MARK}",
                validation_logic_ref=validator,
                evidence_requirement="At least one clear label image showing the declaration.",
                status=RuleStatus.ACTIVE.value,
                is_demo=True,
            )
            db.add(rule)
            db.flush()
            for category in applies_to:
                db.add(
                    RuleApplicability(
                        rule_id=rule.id,
                        product_category=category,
                        condition_expression={
                            "targetFieldType": target.value,
                            "params": params,
                            "appliesTo": applies_to,
                            "note": _DEMO_MARK,
                        },
                        is_demo=True,
                    )
                )
            count += 1

    db.flush()
    return count
