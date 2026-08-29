"""API v1 router aggregation.

Mounted under ``settings.api_prefix`` by the app factory. Each domain lives in
its own router module; this file only wires them together.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    analytics,
    audit,
    auth,
    batch,
    compliance,
    findings,
    health,
    images,
    inspections,
    perception,
    regulations,
    review,
    storage,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(inspections.router)
api_router.include_router(images.router)
api_router.include_router(findings.router)
api_router.include_router(review.router)
api_router.include_router(compliance.router)
api_router.include_router(regulations.router)
api_router.include_router(audit.router)
api_router.include_router(analytics.router)
api_router.include_router(batch.router)
api_router.include_router(storage.router)
api_router.include_router(perception.router)

__all__ = ["api_router"]
