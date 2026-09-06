"""Evidence Planner + verification service (UI-06).

THE CORE QUESTION: "AI found a potential issue. What evidence is still
required before an inspector can make a defensible decision?"

    PERCEIVE   the perception layer already ran (image → OCR → fields)
    EVALUATE   the deterministic engine already ran (fields → findings)
    IDENTIFY   this service: what evidence exists, what is MISSING, and
               which concrete inspector action closes the gap
    VERIFY     a human creates + completes a VerificationTask
    REVIEW     the existing HITL layer (already built, not duplicated here)
    DECIDE     the existing InspectionDecision layer (never automated)

LEGAL SAFETY — the two boundaries this module refuses to cross:

1. DECLARED vs MEASURED. The system reads the DECLARED quantity from the
   package. A physical measurement is a human action recorded as a
   VerificationResult. Nothing here subtracts the two and declares a
   violation: permissible-error evaluation requires regulatory parameters the
   engine does not guess at. The measurement is EVIDENCE for the inspector.
2. GAP != VIOLATION. Evidence completeness is never a probability of
   violation. A row with a missing measurement is "requires verification",
   not "probably non-compliant".

Verification tasks are created ONLY by an authorised human through the
planner UI — the engine never auto-creates them, and completing one never
auto-creates or auto-changes a finding or a decision.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    ApplicabilityOutcome,
    AuditEventType,
    EvidenceItemStatus,
    EvidenceRequirementKind,
    ExtractionStatus,
    FieldType,
    FindingReviewState,
    LotPackageStatus,
    UserRole,
    VerificationLevel,
    VerificationTaskStatus,
    VerificationTaskType,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.base import utcnow
from app.models import (
    AuditEvent,
    CitizenReport,
    ComplianceEvaluation,
    EvaluationFinding,
    ExtractedField,
    Image,
    Inspection,
    LotPackage,
    Package,
    User,
    VerificationResult,
    VerificationTask,
)
from app.services.audit.service import AuditService
from app.services.regulatory.service import RegulatoryService
from app.services.verification.measurement_eval import (
    declared_text_for_task,
    evaluate_measurement,
    evaluation_out,
    evaluations_for_results,
)
from app.services.verification.units import observed_difference, normalize_unit

# Roles that may create/act on verification tasks (router enforces the same
# set; the service re-checks so no code path can bypass it).
_VERIFY_ROLES = frozenset(
    {UserRole.INSPECTOR.value, UserRole.SUPERVISOR.value, UserRole.ADMIN.value}
)

# Default requirement level per task type. MEASUREMENT is REQUIRED (the
# declaration cannot be trusted without it for net-content findings);
# INSPECTOR_OBSERVATION is RECOMMENDED by default (an AI-suggested double
# check). The creating human may override either.
_DEFAULT_LEVEL: dict[VerificationTaskType, VerificationLevel] = {
    VerificationTaskType.MEASUREMENT: VerificationLevel.REQUIRED,
    VerificationTaskType.INSPECTOR_OBSERVATION: VerificationLevel.RECOMMENDED,
}

# Valid task lifecycle transitions (anything else raises ConflictError).
_TASK_TRANSITIONS: dict[VerificationTaskStatus, frozenset[VerificationTaskStatus]] = {
    VerificationTaskStatus.PENDING: frozenset(
        {VerificationTaskStatus.IN_PROGRESS, VerificationTaskStatus.CANCELLED}
    ),
    VerificationTaskStatus.IN_PROGRESS: frozenset(
        {VerificationTaskStatus.COMPLETED, VerificationTaskStatus.CANCELLED}
    ),
    VerificationTaskStatus.COMPLETED: frozenset(),
    VerificationTaskStatus.CANCELLED: frozenset(),
}

# Gap kinds the planner can currently propose (only what the system supports).
_MEASUREMENT_FIELD_TYPES = frozenset({FieldType.NET_QUANTITY.value})

NET_QUANTITY_GAP_REASON = (
    "Physical net quantity is not verified — METRASIGHT can only read the "
    "value DECLARED on the package; it cannot weigh the contents."
)
LOW_CONFIDENCE_GAP_REASON = (
    "Low-confidence extraction — a human must verify the declared reading "
    "before relying on it (the original OCR evidence is preserved)."
)


@dataclass
class _Anchor:
    """Resolved anchor of a plan row / task: finding and/or extracted field."""

    finding: EvaluationFinding | None = None
    field: ExtractedField | None = None
    lot_package: LotPackage | None = None
    @property
    def title(self) -> str:
        if self.finding is not None:
            prov = self.finding.provenance or {}
            return (
                f"{prov.get('requirementCode') or 'Requirement'}"
                f"{': ' + prov['requirementTitle'] if prov.get('requirementTitle') else ''}"
            )
        if self.lot_package is not None:
            return f"Lot package {self.lot_package.label}"
        assert self.field is not None
        return str(self.field.field_type)


@dataclass
class _TaskIndex:
    """All verification tasks of one inspection, indexed by anchor."""

    tasks: list[VerificationTask] = field(default_factory=list)

    def for_anchor(
        self, anchor: _Anchor
    ) -> list[VerificationTask]:
        out = []
        for task in self.tasks:
            if anchor.lot_package is not None:
                if task.lot_package_id == anchor.lot_package.id:
                    out.append(task)
                continue
            if anchor.finding is not None and task.finding_id == anchor.finding.id:
                out.append(task)
            elif (
                anchor.field is not None
                and task.finding_id is None
                and task.lot_package_id is None
                and task.extracted_field_id == anchor.field.id
            ):
                # A task created via fieldId alone (finding_id NULL) belongs
                # to the DECLARATION it anchored on. It must be visible to
                # every plan row carrying that field — the finding row for
                # the same declaration shows the finding's extracted field,
                # so match on the field, not just the finding. Lot-anchored
                # tasks (lot_package_id set) never match field/finding rows.
                out.append(task)
        return out

    def completed_of_type(
        self, anchor: _Anchor, task_type: VerificationTaskType
    ) -> VerificationTask | None:
        for task in self.for_anchor(anchor):
            if (
                task.task_type == task_type.value
                and task.status == VerificationTaskStatus.COMPLETED.value
            ):
                return task
        return None

    def open_of_type(
        self, anchor: _Anchor, task_type: VerificationTaskType
    ) -> VerificationTask | None:
        for task in self.for_anchor(anchor):
            if (
                task.task_type == task_type.value
                and VerificationTaskStatus(task.status).is_open
            ):
                return task
        return None


class VerificationService:
    """Evidence plan computation + verification task lifecycle."""

    def __init__(
        self, audit: AuditService, regulatory: RegulatoryService | None = None
    ) -> None:
        self._audit = audit
        # UI-07: optional so existing tests keep constructing
        # VerificationService(audit). Without it, recorded measurements are
        # still validated + audited; only the regulatory evaluation is
        # skipped (and the plan labels it unavailable).
        self._regulatory = regulatory

    # ------------------------------------------------------------ evidence plan

    def evidence_plan(self, db: Session, inspection_id: uuid.UUID) -> dict:
        """GET /inspections/{id}/evidence-plan.

        One row per engine finding (latest evaluation), plus one row per
        extracted declaration that no finding referenced. Every ✓ and ⚠ shown
        is derived from data that actually exists — nothing is invented.
        """
        inspection = self._get_inspection(db, inspection_id)

        latest_eval = self._latest_evaluation(db, inspection_id)
        findings: list[EvaluationFinding] = (
            list(latest_eval.findings) if latest_eval else []
        )
        fields = self._inspection_fields(db, inspection_id)
        task_index = _TaskIndex(
            tasks=list(
                db.execute(
                    select(VerificationTask)
                    .where(VerificationTask.inspection_id == inspection_id)
                    .options(selectinload(VerificationTask.results))
                    .order_by(VerificationTask.created_at.asc())
                ).scalars()
            )
        )

        referenced_field_ids = {f.extracted_field_id for f in findings}
        has_image = (
            db.execute(
                select(func.count())
                .select_from(Image)
                .join(Package, Package.id == Image.package_id)
                .where(Package.inspection_id == inspection_id)
            ).scalar_one()
            > 0
        )
        items: list[dict] = []

        for finding in findings:
            items.append(
                self._finding_row(
                    finding,
                    field=(
                        finding.extracted_field
                        if finding.extracted_field_id
                        else None
                    ),
                    tasks=task_index,
                    has_image=has_image,
                    db=db,
                )
            )
        for fld in fields:
            if fld.id in referenced_field_ids:
                continue
            if fld.status == ExtractionStatus.NOT_EXTRACTED.value:
                # Nothing usable was read — the perception run history, not
                # the evidence planner, owns that signal.
                continue
            items.append(
                self._declaration_row(fld, tasks=task_index, has_image=has_image, db=db)
            )

        counts = {
            "total": len(items),
            "available": 0,
            "requiring_verification": 0,
            "verified": 0,
            "rejected": 0,
            "not_applicable": 0,
            "open_required_tasks": self.open_required_tasks(db, inspection_id),
        }
        # Row status → counts key. Explicit map (not status.lower()) because
        # the two vocabularies differ: REQUIRES_VERIFICATION counts as
        # "requiring_verification", and any future status is counted nowhere
        # rather than silently creating a phantom key.
        count_keys = {
            EvidenceItemStatus.AVAILABLE.value: "available",
            EvidenceItemStatus.REQUIRES_VERIFICATION.value: "requiring_verification",
            EvidenceItemStatus.VERIFIED.value: "verified",
            EvidenceItemStatus.REJECTED.value: "rejected",
            EvidenceItemStatus.NOT_APPLICABLE.value: "not_applicable",
        }
        for item in items:
            key = count_keys.get(item["status"])
            if key is not None:
                counts[key] += 1

        return {
            "inspection_id": inspection.id,
            "items": items,
            "counts": counts,
        }

    # ---------------------------------------------------------- task lifecycle

    def create_task(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        actor: User,
        finding_id: uuid.UUID | None,
        field_id: uuid.UUID | None,
        task_type: VerificationTaskType,
        reason: str,
        requirement_level: VerificationLevel | None = None,
        lot_package_id: uuid.UUID | None = None,
    ) -> VerificationTask:
        """POST /inspections/{id}/verifications — create ONE task.

        Explicit human action only. Duplicate guard: an OPEN task of the same
        type on the same anchor already exists → ConflictError.

        UI-07: a task may instead anchor on a lot package (the unit a lot
        measurement verifies). Lot-anchored tasks gate the LOT decision, not
        the inspection decision.
        """
        self._assert_actor_may_verify(db, inspection_id, actor)

        if not (reason and reason.strip()):
            raise ValidationError(
                "A reason is mandatory — every verification must be traceable."
            )

        anchor = self._resolve_anchor(
            db,
            inspection_id,
            finding_id=finding_id,
            field_id=field_id,
            lot_package_id=lot_package_id,
        )

        existing_open = _TaskIndex(
            tasks=list(
                db.execute(
                    select(VerificationTask).where(
                        VerificationTask.inspection_id == inspection_id,
                        VerificationTask.task_type == task_type.value,
                        VerificationTask.status.in_(
                            [
                                VerificationTaskStatus.PENDING.value,
                                VerificationTaskStatus.IN_PROGRESS.value,
                            ]
                        ),
                    )
                ).scalars()
            )
        ).open_of_type(anchor, task_type)
        if existing_open is not None:
            raise ConflictError(
                f"An open {task_type.value} verification task already exists "
                f"for this anchor (task {existing_open.id}, status "
                f"{existing_open.status}). Complete or cancel it first."
            )

        level = requirement_level or _DEFAULT_LEVEL[task_type]
        task = VerificationTask(
            inspection_id=inspection_id,
            finding_id=anchor.finding.id if anchor.finding else None,
            extracted_field_id=anchor.field.id if anchor.field else None,
            lot_package_id=anchor.lot_package.id if anchor.lot_package else None,
            task_type=task_type.value,
            requirement_level=level.value,
            reason=reason.strip(),
            status=VerificationTaskStatus.PENDING.value,
            created_by=actor.id,
        )
        db.add(task)
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.VERIFICATION_CREATED,
            entity_type="verification_task",
            entity_id=task.id,
            actor_id=actor.id,
            inspection_id=inspection_id,
            payload={
                "taskType": task.task_type,
                "requirementLevel": task.requirement_level,
                "reason": task.reason,
                "actorRole": actor.role,
                **(
                    {"findingId": str(anchor.finding.id)}
                    if anchor.finding
                    else {}
                ),
                **(
                    {"extractedFieldId": str(anchor.field.id)}
                    if anchor.field
                    else {}
                ),
                **(
                    {"lotPackageId": str(anchor.lot_package.id)}
                    if anchor.lot_package
                    else {}
                ),
            },
        )
        db.commit()
        return task

    def list_tasks(
        self, db: Session, inspection_id: uuid.UUID
    ) -> list[VerificationTask]:
        """GET /inspections/{id}/verifications (oldest first, full results)."""
        self._get_inspection(db, inspection_id)
        return list(
            db.execute(
                select(VerificationTask)
                .where(VerificationTask.inspection_id == inspection_id)
                .options(
                    selectinload(VerificationTask.results),
                    selectinload(VerificationTask.lot_package).selectinload(
                        LotPackage.lot
                    ),
                )
                .order_by(VerificationTask.created_at.asc())
            ).scalars()
        )

    def get_task(
        self, db: Session, task_id: uuid.UUID, actor: User | None = None
    ) -> VerificationTask:
        task = db.execute(
            select(VerificationTask)
            .where(VerificationTask.id == task_id)
            .options(
                selectinload(VerificationTask.results),
                selectinload(VerificationTask.lot_package).selectinload(
                    LotPackage.lot
                ),
            )
        ).scalar_one_or_none()
        if task is None:
            raise NotFoundError(f"Verification task not found: {task_id}")
        if actor is not None:
            self._assert_actor_may_verify(db, task.inspection_id, actor)
        return task

    def start_task(
        self, db: Session, *, task_id: uuid.UUID, actor: User
    ) -> VerificationTask:
        """POST /verifications/{id}/start — PENDING → IN_PROGRESS."""
        task = self.get_task(db, task_id)
        self._assert_actor_may_verify(db, task.inspection_id, actor)
        self._transition(task, VerificationTaskStatus.IN_PROGRESS)
        task.started_at = task.started_at or utcnow()
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.VERIFICATION_STARTED,
            entity_type="verification_task",
            entity_id=task.id,
            actor_id=actor.id,
            inspection_id=task.inspection_id,
            payload={
                "taskType": task.task_type,
                "status": task.status,
                "actorRole": actor.role,
            },
        )
        db.commit()
        return task

    def record_result(
        self,
        db: Session,
        *,
        task_id: uuid.UUID,
        actor: User,
        measured_value: float | None = None,
        unit: str | None = None,
        observation: str | None = None,
        instrument_id: str | None = None,
        instrument_verification_status: str | None = None,
        notes: str | None = None,
        complete: bool = True,
    ) -> VerificationTask:
        """POST /verifications/{id}/result — append one outcome row.

        MEASUREMENT: measured_value (> 0) and unit are mandatory. The measured
        value is stored SEPARATELY from the declared value and nothing here
        evaluates the difference against a rule — the inspector does that.

        Instrument verification status is stored only when supplied: absent
        means "not recorded", never "verified".

        ``complete=True`` closes the task (→ COMPLETED); ``complete=False``
        records an intermediate reading while the task stays IN_PROGRESS.
        """
        task = self.get_task(db, task_id)
        self._assert_actor_may_verify(db, task.inspection_id, actor)

        task_type = VerificationTaskType(task.task_type)
        if task_type == VerificationTaskType.MEASUREMENT:
            if measured_value is None:
                raise ValidationError(
                    "A measured value is mandatory for a MEASUREMENT task."
                )
            if measured_value <= 0:
                raise ValidationError(
                    "Measured value must be greater than zero."
                )
            if not (unit and unit.strip()):
                raise ValidationError(
                    "A unit is mandatory for a MEASUREMENT task "
                    "(e.g. g, kg, ml, L)."
                )
            # UI-07: the unit is VALIDATED, never assumed. mg/g/kg and ml/L
            # normalize deterministically; anything else is a 422 — the
            # system does not silently pick a unit for the inspector.
            normalize_unit(unit.strip())
        else:
            if not (observation and observation.strip()):
                raise ValidationError(
                    "An observation is mandatory for an "
                    "INSPECTOR_OBSERVATION task."
                )

        # Recording a result on a PENDING task implicitly starts it (the
        # inspector was already in the field); on a terminal task it is a 409.
        current = VerificationTaskStatus(task.status)
        if current is VerificationTaskStatus.PENDING:
            self._transition(task, VerificationTaskStatus.IN_PROGRESS)
            task.started_at = task.started_at or utcnow()
        elif current is VerificationTaskStatus.COMPLETED:
            raise ConflictError(
                "This verification task is already COMPLETED — results are "
                "append-only; create a new task for a re-verification."
            )
        elif current is VerificationTaskStatus.CANCELLED:
            raise ConflictError(
                "This verification task was CANCELLED — create a new task."
            )

        result = VerificationResult(
            task=task,
            recorded_by=actor.id,
            recorded_at=utcnow(),
            measured_value=measured_value,
            unit=unit.strip() if unit else None,
            observation=observation.strip() if observation else None,
            instrument_id=instrument_id.strip() if instrument_id else None,
            instrument_verification_status=(
                instrument_verification_status.strip()
                if instrument_verification_status
                else None
            ),
            notes=notes.strip() if notes else None,
        )
        db.add(result)
        db.flush()

        if complete:
            self._transition(task, VerificationTaskStatus.COMPLETED)
            task.completed_at = utcnow()

        # UI-07: the deterministic regulatory evaluation of this recorded
        # result, frozen on a MeasurementEvaluation row (rule code, version,
        # inputs). UNAVAILABLE when no permissible-error procedure is
        # configured — never a guessed tolerance. Skipped only when the
        # service was built without regulatory wiring (unit tests).
        evaluation = None
        if (
            task_type == VerificationTaskType.MEASUREMENT
            and self._regulatory is not None
        ):
            evaluation = evaluate_measurement(
                db,
                result=result,
                task=task,
                regulatory=self._regulatory,
            )
            db.flush()
            self._audit.record(
                db,
                event_type=AuditEventType.MEASUREMENT_EVALUATED,
                entity_type="measurement_evaluation",
                entity_id=evaluation.id,
                actor_id=actor.id,
                inspection_id=task.inspection_id,
                payload={
                    "resultId": str(result.id),
                    "status": evaluation.status,
                    "outcome": evaluation.outcome,
                    "ruleCode": evaluation.rule_code,
                    "actorRole": actor.role,
                },
            )

        # UI-07: a lot package's first recorded measurement moves it to
        # MEASURED (the status is derived state, not a decision).
        if task.lot_package_id is not None and task.lot_package is not None:
            if task.lot_package.status != LotPackageStatus.MEASURED.value:
                task.lot_package.status = LotPackageStatus.MEASURED.value
                db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.VERIFICATION_RESULT_RECORDED,
            entity_type="verification_task",
            entity_id=task.id,
            actor_id=actor.id,
            inspection_id=task.inspection_id,
            payload={
                "resultId": str(result.id),
                "taskType": task.task_type,
                "measuredValue": result.measured_value,
                "unit": result.unit,
                "instrumentId": result.instrument_id,
                "instrumentVerificationStatus": result.instrument_verification_status,
                "recordedAt": result.recorded_at.isoformat(),
                "actorRole": actor.role,
            },
        )
        if complete:
            self._audit.record(
                db,
                event_type=AuditEventType.VERIFICATION_COMPLETED,
                entity_type="verification_task",
                entity_id=task.id,
                actor_id=actor.id,
                inspection_id=task.inspection_id,
                payload={
                    "taskType": task.task_type,
                    "requirementLevel": task.requirement_level,
                    "actorRole": actor.role,
                },
            )
        db.commit()
        return task

    def cancel_task(
        self, db: Session, *, task_id: uuid.UUID, actor: User, reason: str
    ) -> VerificationTask:
        """POST /verifications/{id}/cancel — reason mandatory, append-only."""
        task = self.get_task(db, task_id)
        self._assert_actor_may_verify(db, task.inspection_id, actor)
        if not (reason and reason.strip()):
            raise ValidationError(
                "A cancellation reason is mandatory — the audit trail must "
                "show why a required verification was dropped."
            )
        self._transition(task, VerificationTaskStatus.CANCELLED)
        task.cancelled_reason = reason.strip()
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.VERIFICATION_CANCELLED,
            entity_type="verification_task",
            entity_id=task.id,
            actor_id=actor.id,
            inspection_id=task.inspection_id,
            payload={
                "taskType": task.task_type,
                "requirementLevel": task.requirement_level,
                "reason": task.cancelled_reason,
                "actorRole": actor.role,
            },
        )
        db.commit()
        return task

    # ------------------------------------------------------------- gate helper

    def open_required_tasks(
        self, db: Session, inspection_id: uuid.UUID
    ) -> int:
        """Count of open (PENDING/IN_PROGRESS) REQUIRED tasks.

        Used by the HITL decision gate: REQUIRED blocks a final decision while
        open; RECOMMENDED never does (an AI recommendation is not a legal
        obligation). Lot-anchored tasks are EXCLUDED — they gate the LOT
        decision, not the inspection decision.
        """
        return (
            db.execute(
                select(func.count())
                .select_from(VerificationTask)
                .where(
                    VerificationTask.inspection_id == inspection_id,
                    VerificationTask.requirement_level
                    == VerificationLevel.REQUIRED.value,
                    VerificationTask.lot_package_id.is_(None),
                    VerificationTask.status.in_(
                        [
                            VerificationTaskStatus.PENDING.value,
                            VerificationTaskStatus.IN_PROGRESS.value,
                        ]
                    ),
                )
            ).scalar_one()
            or 0
        )

    def required_task_blockers(
        self, db: Session, inspection_id: uuid.UUID
    ) -> list[str]:
        """Human-readable blockers for open REQUIRED tasks (gate messages)."""
        blockers: list[str] = []
        for task in db.execute(
            select(VerificationTask)
            .where(
                VerificationTask.inspection_id == inspection_id,
                VerificationTask.requirement_level
                == VerificationLevel.REQUIRED.value,
                VerificationTask.lot_package_id.is_(None),
                VerificationTask.status.in_(
                    [
                        VerificationTaskStatus.PENDING.value,
                        VerificationTaskStatus.IN_PROGRESS.value,
                    ]
                ),
            )
            .order_by(VerificationTask.created_at.asc())
        ).scalars():
            blockers.append(
                f"Required verification task {task.id} ({task.task_type}) is "
                f"{task.status}"
            )
        return blockers

    def measurement_history(
        self, db: Session, inspection_id: uuid.UUID
    ) -> list[dict]:
        """GET /inspections/{id}/measurements — every recorded measurement.

        Read model over append-only results: each row carries the declared
        value (never overwritten), the measured value, instrument metadata
        ("not recorded" is a fact, never "verified"), the inspector, the
        timestamp, and the frozen regulatory evaluation + observed
        difference. Nothing is editable — corrections are new rows + audit.
        """
        self._get_inspection(db, inspection_id)
        tasks = list(
            db.execute(
                select(VerificationTask)
                .where(
                    VerificationTask.inspection_id == inspection_id,
                    VerificationTask.task_type
                    == VerificationTaskType.MEASUREMENT.value,
                )
                .options(selectinload(VerificationTask.results))
                .order_by(VerificationTask.created_at.asc())
            ).scalars()
        )
        evaluations = evaluations_for_results(
            db, [r.id for t in tasks for r in t.results]
        )
        rows: list[dict] = []
        for task in tasks:
            declared = declared_text_for_task(task)
            for result in task.results:
                rows.append(
                    {
                        "measurement_id": result.id,
                        "task_id": task.id,
                        "task_status": task.status,
                        "anchor": (
                            {
                                "kind": "LOT_PACKAGE",
                                "lotPackageId": task.lot_package_id,
                            }
                            if task.lot_package_id
                            else (
                                {"kind": "FINDING", "findingId": task.finding_id}
                                if task.finding_id
                                else {
                                    "kind": "DECLARATION",
                                    "extractedFieldId": task.extracted_field_id,
                                }
                            )
                        ),
                        "declared_value": declared,
                        "measured_value": result.measured_value,
                        "unit": result.unit,
                        "observed": observed_difference(
                            declared, result.measured_value, result.unit or ""
                        ),
                        "instrument_id": result.instrument_id,
                        "instrument_verification_status": (
                            result.instrument_verification_status
                        ),
                        "recorded_by": result.recorded_by,
                        "recorded_at": result.recorded_at,
                        "observation": result.observation,
                        "notes": result.notes,
                        "evaluation": evaluation_out(
                            evaluations.get(result.id)
                        ),
                    }
                )
        return rows

    # ------------------------------------------------------- plan row builders

    def _finding_row(
        self,
        finding: EvaluationFinding,
        *,
        field: ExtractedField | None,
        tasks: _TaskIndex,
        has_image: bool,
        db: Session,
    ) -> dict:
        anchor = _Anchor(finding=finding, field=field)
        prov = finding.provenance or {}
        rule_code = None
        if finding.rule is not None:
            rule_code = finding.rule.rule_code

        evidence = [
            self._evidence_item(
                EvidenceRequirementKind.IMAGE,
                bool(finding.image_id or (field and field.image_id) or has_image),
                "Source image",
                detail=(
                    "The package image the finding was read from"
                    if (finding.image_id or (field and field.image_id) or has_image)
                    else "No image recorded for this finding"
                ),
            ),
            self._evidence_item(
                EvidenceRequirementKind.OCR,
                bool(field and field.source_ocr_result_id),
                "OCR text result",
                detail=(
                    "Raw OCR evidence behind the extracted value"
                    if (field and field.source_ocr_result_id)
                    else "No OCR evidence — the finding records an absence"
                ),
            ),
            self._evidence_item(
                EvidenceRequirementKind.REGION,
                bool(finding.evidence_region_id or (field and field.image_region_id)),
                "Image region",
                detail=(
                    "Highlighted region of the declared value"
                    if (finding.evidence_region_id or (field and field.image_region_id))
                    else "No region recorded"
                ),
            ),
            self._evidence_item(
                EvidenceRequirementKind.FIELD,
                field is not None,
                "Extracted field",
                detail=(
                    f"{field.field_type} (raw text preserved)"
                    if field
                    else "No extracted field — absence is the finding"
                ),
            ),
            self._evidence_item(
                EvidenceRequirementKind.EVALUATION,
                True,
                "Engine evaluation",
                detail=(
                    f"Evaluated under {prov.get('versionLabel') or 'unknown version'}"
                ),
            ),
        ]

        gaps: list[dict] = []
        needs_measurement = bool(
            field is not None and field.field_type in _MEASUREMENT_FIELD_TYPES
        )
        measurement_done = (
            tasks.completed_of_type(anchor, VerificationTaskType.MEASUREMENT)
            if needs_measurement
            else None
        )
        if needs_measurement and measurement_done is None:
            open_task = tasks.open_of_type(anchor, VerificationTaskType.MEASUREMENT)
            gaps.append(
                {
                    "kind": EvidenceRequirementKind.MEASUREMENT.value,
                    "reason": NET_QUANTITY_GAP_REASON,
                    "required": True,
                    "default_level": VerificationLevel.REQUIRED.value,
                    "task_id": open_task.id if open_task else None,
                    "task_status": open_task.status if open_task else None,
                }
            )

        low_confidence = bool(
            field is not None
            and field.status == ExtractionStatus.REVIEW_REQUIRED.value
        )
        observation_done = (
            field is not None
            and (
                field.corrected_value is not None
                or tasks.completed_of_type(
                    anchor, VerificationTaskType.INSPECTOR_OBSERVATION
                )
                is not None
            )
        )
        if low_confidence and not observation_done:
            open_task = tasks.open_of_type(
                anchor, VerificationTaskType.INSPECTOR_OBSERVATION
            )
            gaps.append(
                {
                    "kind": EvidenceRequirementKind.INSPECTOR_OBSERVATION.value,
                    "reason": LOW_CONFIDENCE_GAP_REASON,
                    "required": False,
                    "default_level": VerificationLevel.RECOMMENDED.value,
                    "task_id": open_task.id if open_task else None,
                    "task_status": open_task.status if open_task else None,
                }
            )

        status, summary = self._row_status(
            finding=finding,
            needs_measurement=needs_measurement,
            measurement_done=measurement_done is not None,
            gaps=gaps,
        )

        declared_value = None
        unit = None
        confidence = None
        if field is not None:
            declared_value = field.corrected_value or field.normalized_value
            unit = field.unit
            confidence = field.confidence

        return {
            "finding_id": finding.id,
            "field_id": field.id if field else None,
            "title": anchor.title,
            "declared_value": declared_value,
            "unit": unit,
            "confidence": confidence,
            "requirement_code": prov.get("requirementCode"),
            "requirement_title": prov.get("requirementTitle"),
            "rule_code": rule_code,
            "version_label": prov.get("versionLabel"),
            "finding_status": finding.status,
            "severity": finding.severity,
            "applicability": finding.applicability,
            "review_state": finding.review_state,
            "evidence": evidence,
            "gaps": gaps,
            "status": status,
            "summary": summary,
            "verification": self._plan_verification_ref(db, anchor, tasks),
        }

    def _declaration_row(
        self,
        fld: ExtractedField,
        *,
        tasks: _TaskIndex,
        has_image: bool,
        db: Session,
    ) -> dict:
        """A detected declaration no engine finding referenced yet."""
        anchor = _Anchor(field=fld)
        image_present = bool(fld.image_id or has_image)
        evidence = [
            self._evidence_item(
                EvidenceRequirementKind.IMAGE,
                image_present,
                "Source image",
                detail=(
                    "The package image the declaration was read from"
                    if image_present
                    else "No image recorded"
                ),
            ),
            self._evidence_item(
                EvidenceRequirementKind.OCR,
                bool(fld.source_ocr_result_id),
                "OCR text result",
            ),
            self._evidence_item(
                EvidenceRequirementKind.REGION,
                bool(fld.image_region_id),
                "Image region",
            ),
            self._evidence_item(
                EvidenceRequirementKind.FIELD,
                True,
                "Extracted field",
                detail=f"{fld.field_type} (raw text preserved)",
            ),
            self._evidence_item(
                EvidenceRequirementKind.EVALUATION,
                False,
                "Engine evaluation",
                detail="Awaiting regulatory evaluation of this declaration",
            ),
        ]

        gaps: list[dict] = []
        needs_measurement = fld.field_type in _MEASUREMENT_FIELD_TYPES
        measurement_done = (
            tasks.completed_of_type(anchor, VerificationTaskType.MEASUREMENT)
            if needs_measurement
            else None
        )
        if needs_measurement and measurement_done is None:
            open_task = tasks.open_of_type(anchor, VerificationTaskType.MEASUREMENT)
            gaps.append(
                {
                    "kind": EvidenceRequirementKind.MEASUREMENT.value,
                    "reason": NET_QUANTITY_GAP_REASON,
                    "required": True,
                    "default_level": VerificationLevel.REQUIRED.value,
                    "task_id": open_task.id if open_task else None,
                    "task_status": open_task.status if open_task else None,
                }
            )

        low_confidence = fld.status == ExtractionStatus.REVIEW_REQUIRED.value
        observation_done = fld.corrected_value is not None or (
            tasks.completed_of_type(
                anchor, VerificationTaskType.INSPECTOR_OBSERVATION
            )
            is not None
        )
        if low_confidence and not observation_done:
            open_task = tasks.open_of_type(
                anchor, VerificationTaskType.INSPECTOR_OBSERVATION
            )
            gaps.append(
                {
                    "kind": EvidenceRequirementKind.INSPECTOR_OBSERVATION.value,
                    "reason": LOW_CONFIDENCE_GAP_REASON,
                    "required": False,
                    "default_level": VerificationLevel.RECOMMENDED.value,
                    "task_id": open_task.id if open_task else None,
                    "task_status": open_task.status if open_task else None,
                }
            )

        if measurement_done is not None:
            status = EvidenceItemStatus.VERIFIED.value
            summary = (
                "Physical measurement recorded by an inspector — see the "
                "verification result; the declared value is unchanged."
            )
        elif any(g["required"] for g in gaps):
            status = EvidenceItemStatus.REQUIRES_VERIFICATION.value
            summary = (
                "Evidence gap: a required verification is still open. This is "
                "NOT a compliance verdict — it means the evidence is "
                "incomplete."
            )
        else:
            status = EvidenceItemStatus.AVAILABLE.value
            summary = (
                "Declaration evidence available; regulatory evaluation "
                "pending."
            )

        return {
            "finding_id": None,
            "field_id": fld.id,
            "title": str(fld.field_type),
            "declared_value": fld.corrected_value or fld.normalized_value,
            "unit": fld.unit,
            "confidence": fld.confidence,
            "requirement_code": None,
            "requirement_title": None,
            "rule_code": None,
            "version_label": None,
            "finding_status": None,
            "severity": None,
            "applicability": None,
            "review_state": None,
            "evidence": evidence,
            "gaps": gaps,
            "status": status,
            "summary": summary,
            "verification": self._plan_verification_ref(db, anchor, tasks),
        }

    def _row_status(
        self,
        *,
        finding: EvaluationFinding,
        needs_measurement: bool,
        measurement_done: bool,
        gaps: list[dict],
    ) -> tuple[str, str]:
        if finding.applicability == ApplicabilityOutcome.NO.value:
            return (
                EvidenceItemStatus.NOT_APPLICABLE.value,
                "Requirement determined not applicable — no evidence needed.",
            )
        if finding.review_state == FindingReviewState.REJECTED.value:
            return (
                EvidenceItemStatus.REJECTED.value,
                "The inspector rejected this finding — it carries no decision "
                "weight, but the system output is preserved.",
            )
        if needs_measurement and measurement_done:
            return (
                EvidenceItemStatus.VERIFIED.value,
                "Inspector recorded a physical measurement — the declared "
                "value and the measured value are both preserved. Compare "
                "them against the applicable rule yourself: the system does "
                "not evaluate the difference.",
            )
        if any(g["required"] for g in gaps):
            return (
                EvidenceItemStatus.REQUIRES_VERIFICATION.value,
                "Evidence gap: a required verification is still open. This is "
                "NOT a compliance verdict — it means the evidence is "
                "incomplete.",
            )
        return (
            EvidenceItemStatus.AVAILABLE.value,
            "Evidence available: image, OCR, region, extracted field and "
            "evaluation all recorded for this finding.",
        )

    @staticmethod
    def _evidence_item(
        kind: EvidenceRequirementKind, present: bool, label: str, detail: str | None = None
    ) -> dict:
        return {
            "kind": kind.value,
            "status": (
                EvidenceItemStatus.AVAILABLE.value
                if present
                else EvidenceItemStatus.MISSING.value
            ),
            "label": label,
            "detail": detail,
        }

    @staticmethod
    def _plan_verification_ref(
        db: Session, anchor: _Anchor, tasks: _TaskIndex
    ) -> dict | None:
        """The most relevant task on this anchor: an open one first, else the
        latest completed one (its recorded result is the evidence)."""
        candidates = tasks.for_anchor(anchor)
        if not candidates:
            return None
        open_tasks = [t for t in candidates if VerificationTaskStatus(t.status).is_open]
        task = open_tasks[0] if open_tasks else candidates[-1]
        latest = task.latest_result
        observed = None
        if (
            latest is not None
            and latest.measured_value is not None
            and latest.unit
        ):
            # UI-07: the OBSERVED difference — arithmetic only, explicitly
            # not a legal deficiency (the regulatory evaluation + inspector
            # own that judgement).
            observed = observed_difference(
                declared_text_for_task(task),
                latest.measured_value,
                latest.unit,
            )
        return {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "requirement_level": task.requirement_level,
            "reason": task.reason,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "observed": observed,
            "evaluation": (
                evaluation_out(
                    evaluations_for_results(db, [latest.id]).get(latest.id)
                )
                if latest is not None
                else None
            ),
            "latest_result": (
                {
                    "id": latest.id,
                    "task_id": latest.task_id,
                    "recorded_by": latest.recorded_by,
                    "recorded_at": latest.recorded_at,
                    "measured_value": latest.measured_value,
                    "unit": latest.unit,
                    "observation": latest.observation,
                    "instrument_id": latest.instrument_id,
                    "instrument_verification_status": latest.instrument_verification_status,
                    "notes": latest.notes,
                    "created_at": latest.created_at,
                }
                if latest
                else None
            ),
        }

    # --------------------------------------------------------------- internals

    def _get_inspection(self, db: Session, inspection_id: uuid.UUID) -> Inspection:
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        return inspection

    @staticmethod
    def _latest_evaluation(
        db: Session, inspection_id: uuid.UUID
    ) -> ComplianceEvaluation | None:
        return (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id == inspection_id)
                .order_by(ComplianceEvaluation.created_at.desc())
                .limit(1)
                .options(selectinload(ComplianceEvaluation.findings))
            )
            .scalars()
            .first()
        )

    @staticmethod
    def _inspection_fields(
        db: Session, inspection_id: uuid.UUID
    ) -> list[ExtractedField]:
        # Same traversal the evidence-graph builder uses (Prompt 7):
        # field → image → package → inspection.
        return list(
            db.execute(
                select(ExtractedField)
                .join(Package, Package.id == ExtractedField.package_id)
                .where(Package.inspection_id == inspection_id)
                .order_by(ExtractedField.created_at.asc())
            ).scalars()
        )

    def _resolve_anchor(
        self,
        db: Session,
        inspection_id: uuid.UUID,
        *,
        finding_id: uuid.UUID | None,
        field_id: uuid.UUID | None,
        lot_package_id: uuid.UUID | None = None,
    ) -> _Anchor:
        """Validate the anchor belongs to THIS inspection (no cross-inspection
        task creation, no anchor-less tasks)."""
        finding = None
        field = None
        lot_package = None
        if lot_package_id is not None:
            lot_package = db.get(LotPackage, lot_package_id)
            if lot_package is None:
                raise NotFoundError(f"Lot package not found: {lot_package_id}")
            if lot_package.lot.inspection_id != inspection_id:
                raise ValidationError(
                    "lotPackageId does not belong to this inspection."
                )
            if finding_id is not None or field_id is not None:
                raise ValidationError(
                    "A lot-anchored task carries only lotPackageId — a task "
                    "gates either the inspection decision or the lot "
                    "decision, never both."
                )
        if finding_id is not None:
            finding = db.get(EvaluationFinding, finding_id)
            if finding is None:
                raise NotFoundError(f"Finding not found: {finding_id}")
            if finding.evaluation.inspection_id != inspection_id:
                raise ValidationError(
                    "findingId does not belong to this inspection."
                )
            if field_id is not None and finding.extracted_field_id != field_id:
                raise ValidationError(
                    "fieldId does not match the finding's extracted field."
                )
        if field_id is not None:
            field = db.get(ExtractedField, field_id)
            if field is None:
                raise NotFoundError(f"Extracted field not found: {field_id}")
            if self._inspection_of_field(db, field) != inspection_id:
                raise ValidationError(
                    "fieldId does not belong to this inspection."
                )
        if finding is None and field is None and lot_package is None:
            raise ValidationError(
                "A verification task needs an anchor: findingId and/or "
                "fieldId, or lotPackageId for a lot measurement."
            )
        if finding is not None and finding.extracted_field_id is not None:
            field = finding.extracted_field
        return _Anchor(finding=finding, field=field, lot_package=lot_package)

    @staticmethod
    def _inspection_of_field(db: Session, fld: ExtractedField) -> uuid.UUID:
        package = db.get(Package, fld.package_id)
        if package is None or package.inspection_id is None:
            raise NotFoundError(
                f"The field's package has no inspection (field {fld.id})."
            )
        return package.inspection_id

    def _assert_actor_may_verify(
        self, db: Session, inspection_id: uuid.UUID, actor: User
    ) -> None:
        """Role + assignment guard (same semantics as the UI-05 assignment
        guard): SUPERVISOR/ADMIN always may; an INSPECTOR may unless the
        inspection is formally assigned to someone else."""
        inspection = self._get_inspection(db, inspection_id)
        if actor.role not in _VERIFY_ROLES:
            raise ForbiddenError(
                "Only an inspector, supervisor or admin may perform "
                "verification actions."
            )
        if actor.role == UserRole.INSPECTOR.value:
            formally_assigned = (
                db.execute(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.inspection_id == inspection.id,
                        AuditEvent.event_type
                        == AuditEventType.INSPECTION_ASSIGNED.value,
                    )
                ).scalar_one()
                > 0
            )
            if not formally_assigned:
                report = (
                    db.execute(
                        select(CitizenReport).where(
                            CitizenReport.inspection_id == inspection.id
                        )
                    )
                    .scalars()
                    .first()
                )
                formally_assigned = (
                    report is not None
                    and report.assigned_inspector_id is not None
                    and report.assigned_inspector_id == inspection.inspector_id
                )
            if (
                formally_assigned
                and inspection.inspector_id is not None
                and inspection.inspector_id != actor.id
            ):
                raise ForbiddenError(
                    "This inspection is formally assigned to another "
                    "inspector — only that inspector (or a supervisor/admin) "
                    "may verify its evidence."
                )

    @staticmethod
    def _transition(
        task: VerificationTask, target: VerificationTaskStatus
    ) -> None:
        current = VerificationTaskStatus(task.status)
        if target not in _TASK_TRANSITIONS[current]:
            raise ConflictError(
                f"Invalid verification task transition {current.value} → "
                f"{target.value}."
            )
        task.status = target.value
