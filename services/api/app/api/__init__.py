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
    citizen,
    compliance,
    department,
    evidence_graph,
    findings,
    health,
    history,
    hitl,
    images,
    inspections,
    lots,
    perception,
    products,
    regulations,
    reports,
    review,
    search,
    storage,
    verification,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(citizen.router)
api_router.include_router(department.router)
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
api_router.include_router(evidence_graph.router)
api_router.include_router(hitl.router)
api_router.include_router(verification.router)
api_router.include_router(lots.router)
api_router.include_router(reports.router)
# UI-09 — search, history & operational intelligence (read-only, staff-only)
api_router.include_router(search.router)
api_router.include_router(history.router)
api_router.include_router(products.router)

__all__ = ["api_router"]
