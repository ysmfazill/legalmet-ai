"""Compliance rule seeding — binds deterministic rules to real requirements.

Every seeded ComplianceRule row corresponds to a Prompt 5 requirement (FK to
``rules.id``) and encodes HOW to check it. Nothing here invents a requirement,
a rule number or a citation — the requirement data is the source of truth; the
rule simply attaches a deterministic check to it.

The binding is derived from what each requirement's ``field_key`` and
``expected_format`` genuinely allow, using only the rule types implemented in
``evaluators.py``:

    field_key            rule types
    -------------------  ------------------------------------------
    MRP                  MRP_FORMAT + COMPARISON(>0)
    NET_QUANTITY         PRESENCE + UNIT_MATCH
    DATE_OF_MANUFACTURE  PRESENCE + DATE_FORMAT
    BEST_BEFORE          PRESENCE + DATE_FORMAT
    CONSUMER_CARE        PRESENCE + CONTACT_FORMAT
    COUNTRY_OF_ORIGIN    PRESENCE + DECLARATION_FORMAT(min 1 word)
    MANUFACTURER_DETAILS PRESENCE + DECLARATION_FORMAT(min 2 words)
    GENERIC_NAME         PRESENCE + DECLARATION_FORMAT(min 1 word)
    DIMENSIONS           PRESENCE + NUMERIC_VALUE
    (others)             PRESENCE

Idempotent: natural key (requirement_id, rule_code) — safe to run repeatedly.
Only real (non-demo) requirements get rules.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RuleStatus
from app.models import ComplianceRule, Rule

# Accepted metric units for net-quantity declarations (Schedule units used by
# the seeded Legal Metrology requirements).
_QUANTITY_UNITS = ["g", "kg", "ml", "l", "pcs", "units", "m", "cm"]

# field_key → list of (rule_type_suffix, rule_type, configuration)
_RULE_BINDINGS: dict[str, list[tuple[str, str, dict]]] = {
    "MRP": [
        ("MRP_FORMAT", "MRP_FORMAT", {}),
        (
            "POSITIVE_PRICE",
            "COMPARISON",
            {"operator": ">", "value": "0"},
        ),
    ],
    "NET_QUANTITY": [
        ("PRESENCE", "PRESENCE", {}),
        ("UNIT_MATCH", "UNIT_MATCH", {"units": _QUANTITY_UNITS}),
    ],
    "DATE_OF_MANUFACTURE": [
        ("PRESENCE", "PRESENCE", {}),
        ("DATE_FORMAT", "DATE_FORMAT", {}),
    ],
    "BEST_BEFORE": [
        ("PRESENCE", "PRESENCE", {}),
        ("DATE_FORMAT", "DATE_FORMAT", {}),
    ],
    "CONSUMER_CARE": [
        ("PRESENCE", "PRESENCE", {}),
        ("CONTACT_FORMAT", "CONTACT_FORMAT", {}),
    ],
    "COUNTRY_OF_ORIGIN": [
        ("PRESENCE", "PRESENCE", {}),
        ("DECLARATION_FORMAT", "DECLARATION_FORMAT", {"minWords": 1}),
    ],
    "MANUFACTURER_DETAILS": [
        ("PRESENCE", "PRESENCE", {}),
        ("DECLARATION_FORMAT", "DECLARATION_FORMAT", {"minWords": 2}),
    ],
    "PACKER_DETAILS": [
        ("PRESENCE", "PRESENCE", {}),
        ("DECLARATION_FORMAT", "DECLARATION_FORMAT", {"minWords": 2}),
    ],
    "IMPORTER_DETAILS": [
        ("PRESENCE", "PRESENCE", {}),
        ("DECLARATION_FORMAT", "DECLARATION_FORMAT", {"minWords": 2}),
    ],
    "GENERIC_NAME": [
        ("PRESENCE", "PRESENCE", {}),
        ("DECLARATION_FORMAT", "DECLARATION_FORMAT", {"minWords": 1}),
    ],
    "DIMENSIONS": [
        ("PRESENCE", "PRESENCE", {}),
        ("NUMERIC_VALUE", "NUMERIC_VALUE", {}),
    ],
}
_DEFAULT_BINDING = [("PRESENCE", "PRESENCE", {})]


def seed_compliance_rules(db: Session) -> dict[str, int]:
    """Idempotently create ComplianceRule rows for all real requirements."""
    created = 0
    requirements = list(
        db.execute(
            select(Rule).where(
                Rule.is_demo.is_(False),
                Rule.status == RuleStatus.ACTIVE.value,
            )
        ).scalars()
    )
    for requirement in requirements:
        bindings = _RULE_BINDINGS.get(requirement.field_key or "", _DEFAULT_BINDING)
        for suffix, rule_type, configuration in bindings:
            code = f"{requirement.rule_code}:{suffix}"
            existing = db.execute(
                select(ComplianceRule).where(
                    ComplianceRule.requirement_id == requirement.id,
                    ComplianceRule.rule_code == code,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                ComplianceRule(
                    requirement_id=requirement.id,
                    rule_code=code,
                    rule_type=rule_type,
                    rule_version=1,
                    configuration=dict(configuration),
                    description=(
                        f"Deterministic {rule_type} check for {requirement.rule_code} "
                        f"({requirement.title})."
                    ),
                    active=True,
                    is_demo=False,
                )
            )
            created += 1
    db.flush()
    db.commit()
    return {"requirements": len(requirements), "rulesCreated": created}
