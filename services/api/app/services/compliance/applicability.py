"""Applicability resolution — does a requirement apply to THIS package?

Deterministic evaluation of the Prompt 5 ``applicability_definition`` /
``condition_expression`` structures:

    {"commodity": "*" | [categories...],
     "packageType": "*" | [types...],
     "saleContext": "RETAIL" | "*",
     "importedOnly": true}

Rules of the house:

* Everything resolves to YES / NO / UNKNOWN — never a boolean guess.
* Any input the resolver needs but does not have (e.g. product category when
  the condition is category-specific) yields UNKNOWN, which the engine turns
  into REVIEW_REQUIRED — never into silent skip, never into a violation.
* A NO outcome is recorded with its reason: the requirement does not apply,
  therefore no non-compliance finding is created, but the decision is kept.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ApplicabilityOutcome


@dataclass(frozen=True)
class ApplicabilityInput:
    """The package facts applicability is evaluated against.

    ``category`` comes from Product.category; ``imported`` is derived from the
    presence of importer details (or an explicit product flag when one exists).
    ``sale_context`` defaults to RETAIL — the only context the seeded Legal
    Metrology declarations speak about.
    """

    category: str | None
    imported: bool | None
    sale_context: str = "RETAIL"


@dataclass(frozen=True)
class ApplicabilityResult:
    outcome: ApplicabilityOutcome
    reason: str

    @property
    def applies(self) -> bool:
        return self.outcome is ApplicabilityOutcome.YES


def _matches_wildcard(value) -> bool:
    return value == "*" or value is None or value == ""


class ApplicabilityResolver:
    """Evaluates Prompt 5 applicability conditions deterministically."""

    def evaluate(
        self, condition: dict | None, package: ApplicabilityInput
    ) -> ApplicabilityResult:
        if not condition:
            # No conditions recorded → the requirement applies universally.
            return ApplicabilityResult(
                ApplicabilityOutcome.YES,
                "No applicability conditions recorded — requirement applies generally.",
            )

        # commodity / category condition
        commodity = condition.get("commodity", "*")
        if not _matches_wildcard(commodity):
            if package.category is None or not str(package.category).strip():
                return ApplicabilityResult(
                    ApplicabilityOutcome.UNKNOWN,
                    "Requirement is category-specific but the package has no recorded "
                    "category — applicability cannot be determined without a human.",
                )
            allowed = (
                commodity if isinstance(commodity, list) else [commodity]
            )
            norm = str(package.category).strip().lower()
            if norm not in [str(c).strip().lower() for c in allowed]:
                return ApplicabilityResult(
                    ApplicabilityOutcome.NO,
                    f"Requirement applies to commodity categories {allowed} but this "
                    f"package's category is '{package.category}'.",
                )

        # imported-only condition (e.g. country of origin for imports)
        if condition.get("importedOnly"):
            if package.imported is None:
                return ApplicabilityResult(
                    ApplicabilityOutcome.UNKNOWN,
                    "Requirement applies to imported packages only, but the import "
                    "status of this package is unknown — applicability cannot be "
                    "determined without a human.",
                )
            if not package.imported:
                return ApplicabilityResult(
                    ApplicabilityOutcome.NO,
                    "Requirement applies to imported packages only; this package is "
                    "not imported.",
                )

        # sale context condition
        sale = condition.get("saleContext", "*")
        if not _matches_wildcard(sale) and str(sale).upper() != str(
            package.sale_context
        ).upper():
            return ApplicabilityResult(
                ApplicabilityOutcome.NO,
                f"Requirement applies to sale context '{sale}' but this inspection's "
                f"context is '{package.sale_context}'.",
            )

        return ApplicabilityResult(
            ApplicabilityOutcome.YES,
            "All applicability conditions satisfied for this package.",
        )
