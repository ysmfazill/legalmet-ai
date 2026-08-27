"""Deterministic MOCK product-understanding service (foundation phase).

DEMO ONLY. Maps a category hint to an expected *declaration profile* — the set
of field categories a label of that kind typically carries. This is a perception
hint used to focus extraction and to flag likely-missing declarations. It is NOT
a legal requirement list; legal requirements come only from the rule engine.
"""
from __future__ import annotations

from app.core.enums import FieldType, ModelServiceType
from app.services.interfaces import (
    ProductProfile,
    ProductUnderstandingService,
    ServiceDescriptor,
)

_DEFAULT_PROFILE = [
    FieldType.MRP,
    FieldType.NET_QUANTITY,
    FieldType.MANUFACTURER_DETAILS,
    FieldType.GENERIC_NAME,
    FieldType.DATE_OF_MANUFACTURE,
    FieldType.COUNTRY_OF_ORIGIN,
    FieldType.CONSUMER_CARE,
]

# Category keyword -> extra expected field categories (perception hints only).
_CATEGORY_HINTS: dict[str, list[FieldType]] = {
    "food": [FieldType.BEST_BEFORE, FieldType.BATCH_NUMBER],
    "beverage": [FieldType.BEST_BEFORE, FieldType.BATCH_NUMBER],
    "cosmetic": [FieldType.EXPIRY_DATE, FieldType.BATCH_NUMBER],
    "electronic": [FieldType.DIMENSIONS, FieldType.IMPORTER_DETAILS],
    "apparel": [FieldType.DIMENSIONS],
}


class MockProductUnderstandingService(ProductUnderstandingService):
    @property
    def descriptor(self) -> ServiceDescriptor:
        return ServiceDescriptor(
            service_type=ModelServiceType.PRODUCT_CLASSIFIER,
            name="mock-product-classifier",
            version="0.1.0-demo",
            provider="mock",
        )

    def classify(
        self, *, name: str, category_hint: str | None, gtin: str | None
    ) -> ProductProfile:
        category = (category_hint or "general").strip().lower()
        profile = list(_DEFAULT_PROFILE)
        for keyword, extra in _CATEGORY_HINTS.items():
            if keyword in category:
                for field_type in extra:
                    if field_type not in profile:
                        profile.append(field_type)
        return ProductProfile(
            category=category,
            declaration_profile=profile,
            confidence=0.9,
            descriptor=self.descriptor,
        )
