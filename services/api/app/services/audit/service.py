"""Audit service — append-only provenance trail.

Writes immutable :class:`AuditEvent` rows. Nothing here updates or deletes; the
trail is the tamper-evident record of what happened, to what, by whom, and when.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditEventType
from app.models import AuditEvent


class AuditService:
    def record(
        self,
        db: Session,
        *,
        event_type: AuditEventType,
        entity_type: str,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        inspection_id: UUID | None = None,
        payload: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type.value,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            inspection_id=inspection_id,
            payload=payload,
        )
        db.add(event)
        db.flush()
        return event

    def list_for_inspection(self, db: Session, inspection_id: UUID) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.inspection_id == inspection_id)
            .order_by(AuditEvent.created_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    def list_recent(self, db: Session, *, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(db.execute(stmt).scalars().all())
