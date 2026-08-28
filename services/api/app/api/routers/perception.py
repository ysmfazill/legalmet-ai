"""Perception routes (Prompt 4).

Start / re-run REAL perception analysis over stored package images and read
back OCR text, visual regions, extracted fields and processing-run history.

Handlers are thin — all orchestration lives in ``services.perception``.

Scope guardrail: nothing here evaluates regulatory requirements. The strongest
possible outcome of these routes is perception evidence plus an explicit
"AWAITING_REGULATORY_EVALUATION" marker in the analysis payload — never a
compliance verdict.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep, require_role
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import User
from app.schemas.image import ExtractedFieldOut, ImageRegionOut
from app.schemas.perception import (
    OcrTextResultOut,
    PerceptionAnalysisOut,
    PerceptionKickoffOut,
    PerceptionKickoffRun,
    ProcessingRunDetailOut,
    ProcessingRunOut,
)
from app.services.registry import Services

router = APIRouter(tags=["perception"])

# Perception mutations are performed by field staff; auditors stay read-only.
_PERCEPTION_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


def _kickoff(
    services: Services, runs, inspection_id: UUID
) -> PerceptionKickoffOut:
    return PerceptionKickoffOut(
        inspection_id=inspection_id,
        runs=[
            PerceptionKickoffRun(run_id=run.id, reference=run.reference, image_id=run.image_id)
            for run in runs
        ],
    )


def _run_background(background_tasks: BackgroundTasks, services: Services, run_ids) -> None:
    # Executed after the 202 response is sent; each run uses its own DB
    # session. (TestClient runs these synchronously, keeping tests
    # deterministic.)
    ids = [run.id for run in run_ids]
    background_tasks.add_task(services.perception.execute_runs, ids)


# --- Start / re-run -----------------------------------------------------------


@router.post(
    "/inspections/{inspection_id}/perceive",
    response_model=PerceptionKickoffOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_perception(
    inspection_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(*_PERCEPTION_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> PerceptionKickoffOut:
    runs = services.perception.start_for_inspection(
        db, inspection_id=inspection_id, actor_id=user.id
    )
    _run_background(background_tasks, services, runs)
    return _kickoff(services, runs, inspection_id)


@router.post(
    "/images/{image_id}/reanalyze",
    response_model=PerceptionKickoffOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def reanalyze_image(
    image_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(*_PERCEPTION_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> PerceptionKickoffOut:
    run = services.perception.reanalyze_image(db, image_id=image_id, actor_id=user.id)
    _run_background(background_tasks, services, [run])
    return _kickoff(services, [run], run.inspection_id)


# --- Reads ---------------------------------------------------------------------


@router.get("/inspections/{inspection_id}/analysis", response_model=PerceptionAnalysisOut)
def get_analysis(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> PerceptionAnalysisOut:
    return services.perception.get_analysis(db, inspection_id)


@router.get("/inspections/{inspection_id}/ocr", response_model=list[OcrTextResultOut])
def list_ocr(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[OcrTextResultOut]:
    rows = services.perception.list_ocr(db, inspection_id)
    return [OcrTextResultOut.model_validate(row) for row in rows]


@router.get("/inspections/{inspection_id}/regions", response_model=list[ImageRegionOut])
def list_regions(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[ImageRegionOut]:
    rows = services.perception.list_regions(db, inspection_id)
    return [ImageRegionOut.model_validate(row) for row in rows]


@router.get("/inspections/{inspection_id}/fields", response_model=list[ExtractedFieldOut])
def list_fields(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[ExtractedFieldOut]:
    return [
        ExtractedFieldOut.model_validate(row)
        for row in services.perception.list_fields(db, inspection_id)
    ]


@router.get("/inspections/{inspection_id}/processing", response_model=list[ProcessingRunOut])
def list_processing_runs(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[ProcessingRunOut]:
    return [
        ProcessingRunOut.model_validate(run)
        for run in services.perception.list_runs(db, inspection_id)
    ]


@router.get("/processing-runs/{run_id}", response_model=ProcessingRunDetailOut)
def get_processing_run(
    run_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ProcessingRunDetailOut:
    return services.perception.get_run(db, run_id)
