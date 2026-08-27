"""Provenance helper: resolve (or create) the ModelVersion row for a service.

Every extraction and finding is stamped with the ``model_version_id`` of the
implementation that produced it, so results are attributable and reproducible.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelVersion
from app.services.interfaces import ServiceDescriptor


def resolve_model_version(db: Session, descriptor: ServiceDescriptor) -> ModelVersion:
    stmt = select(ModelVersion).where(
        ModelVersion.service_type == descriptor.service_type.value,
        ModelVersion.name == descriptor.name,
        ModelVersion.version == descriptor.version,
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing

    model_version = ModelVersion(
        service_type=descriptor.service_type.value,
        name=descriptor.name,
        version=descriptor.version,
        provider=descriptor.provider,
        is_active=True,
        meta={"note": "Auto-registered service descriptor."},
    )
    db.add(model_version)
    db.flush()
    return model_version
