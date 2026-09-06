"""Lot intelligence service (UI-07).

LOT → PACKAGES → SAMPLE → MEASUREMENTS → REGULATORY EVALUATION → LOT RESULT.

Physical measurements of lot packages reuse the UI-06 verification machinery
(``VerificationTask`` anchored on a ``LotPackage`` via ``lot_package_id`` +
append-only ``VerificationResult``), so validation, RBAC, audit and
append-only semantics exist exactly once — this service never records a
measurement itself.

LEGAL SAFETY — the boundaries this module refuses to cross:

* SAMPLING: the sample size/method come from a CONFIGURED legal procedure
  when one exists (referenced by code + version). When none is configured the
  run is explicitly labelled AI-recommended and requires inspector
  confirmation — the system never claims "AI selected the legally required
  sample" and never invents a sampling percentage.
* STATISTICS: every number is computed from measurement rows that actually
  exist, and is labelled OBSERVED — never a legal compliance result. The
  average is plain arithmetic over normalized values; a "corrected average"
  per a configured procedure would be added as a versioned procedure, never
  invented here.
* DECISION: the lot status changes ONLY through an explicit inspector
  submission, gated on complete required evidence. Missing evidence blocks
  the decision; it never implies compliance or non-compliance.
"""
from __future__ import annotations

import random
import secrets
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    AuditEventType,
    LotPackageStatus,
    LotStatus,
    MeasurementOutcome,
    RegulatoryProcedureKind,
    SamplingMethod,
    UserRole,
    VerificationLevel,
    VerificationTaskStatus,
    VerificationTaskType,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.base import utcnow
from app.models import (
    Lot,
    LotPackage,
    Product,
    SamplingRun,
    User,
    VerificationTask,
)
from app.services.audit.service import AuditService
from app.services.compliance.resolvers import RequirementResolver
from app.services.regulatory.service import RegulatoryService
from app.services.verification.measurement_eval import (
    evaluation_out,
    evaluations_for_results,
)
from app.services.verification.units import (
    normalize_quantity,
    normalize_unit,
    observed_difference,
    parse_declared_quantity,
    plain_decimal,
)

_LOT_ROLES = frozenset(
    {UserRole.INSPECTOR.value, UserRole.SUPERVISOR.value, UserRole.ADMIN.value}
)

SAMPLING_CONFIRMATION_REQUIRED = "Sampling procedure requires inspector confirmation."


class LotService:
    """Lot lifecycle: create → packages → sample → (measure via verification)
    → statistics → gated decision."""

    def __init__(
        self, audit: AuditService, regulatory: RegulatoryService | None = None
    ) -> None:
        self._audit = audit
        self._regulatory = regulatory

    # ------------------------------------------------------------- creation

    def create_lot(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        actor: User,
        label: str,
        declared_value: str,
        lot_size: int,
        product_id: uuid.UUID | None = None,
        location: str | None = None,
        notes: str | None = None,
    ) -> Lot:
        """POST /inspections/{id}/lots — create a lot + its package records.

        The declared quantity is stored VERBATIM and immutable after creation
        (it is the reference measurements are compared against). It must be a
        parseable quantity with a supported unit — the comparison later needs
        it, so an unparseable declaration is rejected up front, never guessed.
        """
        self._assert_actor(db, inspection_id, actor)

        if not (label and label.strip()):
            raise ValidationError("A lot label is mandatory.")
        if lot_size < 1:
            raise ValidationError("Lot size must be at least 1 package.")
        parsed = parse_declared_quantity(declared_value)
        if parsed is None:
            raise ValidationError(
                f"The declared quantity '{declared_value}' is not a parseable "
                "quantity+unit pair (e.g. '500 g')."
            )
        # Validate the unit now so measurements can normalize against it.
        normalize_unit(parsed[1])

        product = None
        if product_id is not None:
            product = db.get(Product, product_id)
            if product is None:
                raise NotFoundError(f"Product not found: {product_id}")

        duplicate = db.execute(
            select(func.count())
            .select_from(Lot)
            .where(
                Lot.inspection_id == inspection_id,
                func.lower(Lot.label) == label.strip().lower(),
            )
        ).scalar_one()
        if duplicate:
            raise ConflictError(
                f"A lot labelled '{label.strip()}' already exists in this "
                "inspection."
            )

        lot = Lot(
            inspection_id=inspection_id,
            label=label.strip(),
            product_id=product_id,
            declared_value=declared_value.strip(),
            lot_size=lot_size,
            location=location.strip() if location else None,
            notes=notes.strip() if notes else None,
            status=LotStatus.IN_PROGRESS.value,
            created_by=actor.id,
        )
        db.add(lot)
        db.flush()

        # Package records: real, positional rows the sample draws from.
        for position in range(1, lot_size + 1):
            db.add(
                LotPackage(
                    lot_id=lot.id,
                    label=f"{lot.label}-PKG-{position:03d}",
                    status=LotPackageStatus.NOT_SAMPLED.value,
                    position=position,
                )
            )
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.LOT_CREATED,
            entity_type="lot",
            entity_id=lot.id,
            actor_id=actor.id,
            inspection_id=inspection_id,
            payload={
                "label": lot.label,
                "declaredValue": lot.declared_value,
                "lotSize": lot.lot_size,
                "location": lot.location,
                "productId": str(product_id) if product_id else None,
                "actorRole": actor.role,
            },
        )
        db.commit()
        return lot

    def list_lots(self, db: Session, inspection_id: uuid.UUID) -> list[dict]:
        """GET /inspections/{id}/lots — summary rows (detail is per-lot)."""
        lots = list(
            db.execute(
                select(Lot)
                .where(Lot.inspection_id == inspection_id)
                .options(selectinload(Lot.packages))
                .order_by(Lot.created_at.asc())
            ).scalars()
        )
        out = []
        for lot in lots:
            summary = self._lot_progress(lot)
            out.append(
                {
                    "id": lot.id,
                    "label": lot.label,
                    "product_id": lot.product_id,
                    "declared_value": lot.declared_value,
                    "lot_size": lot.lot_size,
                    "location": lot.location,
                    "status": lot.status,
                    "decision": lot.decision,
                    "decision_reason": lot.decision_reason,
                    "decided_at": lot.decided_at,
                    "created_at": lot.created_at,
                    "progress": summary,
                }
            )
        return out

    def get_lot(self, db: Session, lot_id: uuid.UUID) -> dict:
        """GET /lots/{id} — the full lot intelligence read model.

        Packages carry their real measurement records (task + results +
        frozen evaluations); statistics are computed here from those rows and
        labelled OBSERVED.
        """
        lot = self._get_lot(db, lot_id)
        packages = self._lot_packages_with_tasks(db, lot_id)
        runs = list(
            db.execute(
                select(SamplingRun)
                .where(SamplingRun.lot_id == lot_id)
                .order_by(SamplingRun.created_at.asc())
            ).scalars()
        )
        sampling = self._sampling_procedure_out(
            self._resolve_sampling_procedure(db), db
        )
        return {
            "id": lot.id,
            "inspection_id": lot.inspection_id,
            "label": lot.label,
            "product_id": lot.product_id,
            "declared_value": lot.declared_value,
            "lot_size": lot.lot_size,
            "location": lot.location,
            "notes": lot.notes,
            "status": lot.status,
            "decision": lot.decision,
            "decision_reason": lot.decision_reason,
            "decided_by": lot.decided_by,
            "decided_at": lot.decided_at,
            "created_by": lot.created_by,
            "created_at": lot.created_at,
            "packages": [self._package_row(p) for p in packages],
            "sampling_runs": [self.run_row(r) for r in runs],
            "sampling_procedure": sampling,
            "statistics": self._statistics(lot, packages),
            "progress": self._lot_progress(lot),
        }

    # -------------------------------------------------------------- sampling

    def generate_sample(
        self,
        db: Session,
        *,
        lot_id: uuid.UUID,
        actor: User,
        sample_size: int | None = None,
        selection_method: SamplingMethod = SamplingMethod.RANDOM,
        seed: str | None = None,
        confirm_ai_sample: bool = False,
    ) -> SamplingRun:
        """POST /lots/{id}/sample — draw ONE audited, reproducible sample.

        * A configured legal sampling procedure (kind=SAMPLING, applicable
          version) drives the size/method deterministically and is referenced
          by code + version label.
        * Without a configured procedure the requested size is used and the
          run is labelled AI-RECOMMENDED — which REQUIRES explicit inspector
          confirmation (``confirm_ai_sample``); otherwise 422 with the exact
          message "Sampling procedure requires inspector confirmation.".
        * RANDOM draws are seeded: the seed (inspector-supplied or generated)
          is stored, so the draw is reproducible for audit and is NEVER
          regenerated on read.
        """
        lot = self._get_lot(db, lot_id)
        self._assert_actor(db, lot.inspection_id, actor)

        if lot.status != LotStatus.IN_PROGRESS.value:
            raise ConflictError(
                f"The lot decision was already submitted ({lot.status}) — "
                "the sample can no longer change."
            )

        packages = list(
            db.execute(
                select(LotPackage)
                .where(LotPackage.lot_id == lot_id)
                .order_by(LotPackage.position.asc())
            ).scalars()
        )
        measured = [
            p for p in packages if p.status == LotPackageStatus.MEASURED.value
        ]
        if measured:
            raise ConflictError(
                f"{len(measured)} package(s) in this lot already have "
                "recorded measurements — the recorded sample cannot be "
                "silently replaced. Record the remaining measurements or "
                "submit the lot decision."
            )

        procedure = self._resolve_sampling_procedure(db)
        procedure_code = None
        procedure_version_label = None
        is_ai_recommended = False

        if procedure is not None:
            config = procedure.configuration or {}
            size = config.get("sampleSize")
            method = config.get("method")
            if not isinstance(size, int) or size < 1 or method not in (
                SamplingMethod.RANDOM.value,
                SamplingMethod.MANUAL.value,
            ):
                # A configured but malformed procedure is surfaced, never
                # silently defaulted.
                raise ValidationError(
                    "The configured sampling procedure could not be "
                    "interpreted deterministically (malformed "
                    "configuration)."
                )
            sample_size = size
            selection_method = SamplingMethod(method)
            procedure_code = procedure.code
            procedure_version_label = self._procedure_version_label(db, procedure)
        else:
            if sample_size is None:
                raise ValidationError(
                    "A sample size is required — no configured legal "
                    "sampling procedure defines one, and the system does not "
                    "invent a sampling percentage."
                )
            if sample_size < 1:
                raise ValidationError("Sample size must be at least 1.")
            if not confirm_ai_sample:
                raise ValidationError(SAMPLING_CONFIRMATION_REQUIRED)
            is_ai_recommended = True

        if sample_size > len(packages):
            raise ValidationError(
                f"Sample size {sample_size} exceeds the lot size "
                f"({len(packages)} packages)."
            )

        run_seed = (seed.strip() if seed and seed.strip() else None) or (
            secrets.token_hex(8)
        )
        rng = random.Random(run_seed)

        # Reset any previous draw (none measured — guarded above), then select.
        for package in packages:
            package.status = LotPackageStatus.NOT_SAMPLED.value
            package.sampling_run_id = None
        if selection_method == SamplingMethod.RANDOM:
            chosen = sorted(
                rng.sample(range(len(packages)), sample_size),
                key=lambda i: packages[i].position,
            )
            selected_positions = [packages[i].position for i in chosen]
        else:  # MANUAL — the first N by position; the inspector reorders in
            # the UI by (re)submitting labels, the run records the method.
            selected_positions = [p.position for p in packages[:sample_size]]

        run = SamplingRun(
            lot_id=lot_id,
            sample_size=sample_size,
            selection_method=selection_method.value,
            procedure_code=procedure_code,
            procedure_version_label=procedure_version_label,
            is_ai_recommended=is_ai_recommended,
            seed=run_seed,
            randomization={
                "algorithm": "python random.Random (Mersenne Twister)",
                "seedSource": "inspector" if (seed and seed.strip()) else "generated",
                "packageCount": len(packages),
                "selectedPositions": selected_positions,
            },
            created_by=actor.id,
        )
        db.add(run)
        db.flush()

        for position in selected_positions:
            package = next(p for p in packages if p.position == position)
            package.status = LotPackageStatus.PENDING.value
            package.sampling_run_id = run.id
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.LOT_SAMPLE_GENERATED,
            entity_type="sampling_run",
            entity_id=run.id,
            actor_id=actor.id,
            inspection_id=lot.inspection_id,
            payload={
                "lotId": str(lot_id),
                "sampleSize": run.sample_size,
                "selectionMethod": run.selection_method,
                "procedureCode": run.procedure_code,
                "procedureVersionLabel": run.procedure_version_label,
                "isAiRecommended": run.is_ai_recommended,
                "seed": run.seed,
                "selectedPositions": selected_positions,
                "actorRole": actor.role,
            },
        )
        db.commit()
        return run

    # -------------------------------------------------------------- decision

    def submit_decision(
        self,
        db: Session,
        *,
        lot_id: uuid.UUID,
        actor: User,
        decision: LotStatus,
        reason: str,
    ) -> Lot:
        """POST /lots/{id}/decision — the explicit, gated lot result.

        Gate: every sampled (PENDING) package must have a recorded
        measurement. Missing evidence blocks the submission with
        "Insufficient evidence — N measurements remaining" — it never
        implies any outcome.
        """
        lot = self._get_lot(db, lot_id)
        self._assert_actor(db, lot.inspection_id, actor)

        if decision not in (
            LotStatus.COMPLIANT,
            LotStatus.NON_COMPLIANT,
            LotStatus.REQUIRES_REVIEW,
        ):
            raise ValidationError(
                "The lot decision must be COMPLIANT, NON_COMPLIANT or "
                "REQUIRES_REVIEW."
            )
        if not (reason and reason.strip()):
            raise ValidationError(
                "A decision reason is mandatory — the audit trail must show "
                "the inspector's basis."
            )
        if lot.status != LotStatus.IN_PROGRESS.value:
            raise ConflictError(
                "The lot decision was already submitted — decisions are "
                "append-only; start a new lot for a re-verification."
            )

        pending = (
            db.execute(
                select(func.count())
                .select_from(LotPackage)
                .where(
                    LotPackage.lot_id == lot_id,
                    LotPackage.status == LotPackageStatus.PENDING.value,
                )
            ).scalar_one()
        )
        if pending > 0:
            raise ConflictError(
                f"Insufficient evidence — {pending} measurement(s) remaining "
                "on sampled packages. The lot cannot be classified while "
                "required evidence is missing."
            )
        if not any(
            p.status == LotPackageStatus.MEASURED.value
            for p in lot.packages
        ):
            raise ConflictError(
                "Insufficient evidence — no package in this lot has a "
                "recorded measurement. Generate a sample and record the "
                "measurements first."
            )

        lot.status = decision.value
        lot.decision = decision.value
        lot.decision_reason = reason.strip()
        lot.decided_by = actor.id
        lot.decided_at = utcnow()
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.LOT_DECISION_SUBMITTED,
            entity_type="lot",
            entity_id=lot.id,
            actor_id=actor.id,
            inspection_id=lot.inspection_id,
            payload={
                "decision": lot.decision,
                "reason": lot.decision_reason,
                "actorRole": actor.role,
            },
        )
        db.commit()
        return lot

    # ------------------------------------------------------ lot gate helper

    def pending_measurements(self, db: Session, lot_id: uuid.UUID) -> int:
        """Sampled packages still awaiting a measurement (the lot gate)."""
        return (
            db.execute(
                select(func.count())
                .select_from(LotPackage)
                .where(
                    LotPackage.lot_id == lot_id,
                    LotPackage.status == LotPackageStatus.PENDING.value,
                )
            ).scalar_one()
            or 0
        )

    def open_required_lot_tasks(
        self, db: Session, lot_id: uuid.UUID
    ) -> list[VerificationTask]:
        """Open REQUIRED verification tasks anchored on this lot's packages."""
        return list(
            db.execute(
                select(VerificationTask)
                .join(LotPackage, LotPackage.id == VerificationTask.lot_package_id)
                .where(
                    LotPackage.lot_id == lot_id,
                    VerificationTask.requirement_level
                    == VerificationLevel.REQUIRED.value,
                    VerificationTask.status.in_(
                        [
                            VerificationTaskStatus.PENDING.value,
                            VerificationTaskStatus.IN_PROGRESS.value,
                        ]
                    ),
                )
                .order_by(VerificationTask.created_at.asc())
            ).scalars()
        )

    # -------------------------------------------------------------- read out

    @staticmethod
    def _get_lot(db: Session, lot_id: uuid.UUID) -> Lot:
        lot = db.get(Lot, lot_id)
        if lot is None:
            raise NotFoundError(f"Lot not found: {lot_id}")
        return lot

    def _lot_packages_with_tasks(
        self, db: Session, lot_id: uuid.UUID
    ) -> list[tuple[LotPackage, list[VerificationTask]]]:
        packages = list(
            db.execute(
                select(LotPackage)
                .where(LotPackage.lot_id == lot_id)
                .order_by(LotPackage.position.asc())
            ).scalars()
        )
        tasks = list(
            db.execute(
                select(VerificationTask)
                .join(LotPackage, LotPackage.id == VerificationTask.lot_package_id)
                .where(LotPackage.lot_id == lot_id)
                .options(selectinload(VerificationTask.results))
                .order_by(VerificationTask.created_at.asc())
            ).scalars()
        )
        evaluations = evaluations_for_results(
            db, [r.id for t in tasks for r in t.results]
        )
        by_package: dict = {}
        for task in tasks:
            by_package.setdefault(task.lot_package_id, []).append(task)
        # Stash evaluations on the tuples via a parallel list.
        out = []
        for package in packages:
            package_tasks = by_package.get(package.id, [])
            for task in package_tasks:
                for result in task.results:
                    result._measurement_evaluation = evaluations.get(result.id)
            out.append((package, package_tasks))
        return out

    def _package_row(self, entry: tuple) -> dict:
        package, tasks = entry
        measurement_task = None
        for task in tasks:
            if task.task_type == VerificationTaskType.MEASUREMENT.value:
                measurement_task = task
                break
        latest = measurement_task.latest_result if measurement_task else None
        observed = None
        if latest is not None and latest.measured_value is not None and latest.unit:
            observed = observed_difference(
                package.lot.declared_value, latest.measured_value, latest.unit
            )
        return {
            "id": package.id,
            "label": package.label,
            "package_id": package.package_id,
            "position": package.position,
            "status": package.status,
            "sampling_run_id": package.sampling_run_id,
            "measurement": (
                {
                    "task_id": measurement_task.id,
                    "task_status": measurement_task.status,
                    "latest_result": {
                        "id": latest.id,
                        "measuredValue": latest.measured_value,
                        "unit": latest.unit,
                        "instrumentId": latest.instrument_id,
                        "instrumentVerificationStatus": (
                            latest.instrument_verification_status
                        ),
                        "recordedBy": latest.recorded_by,
                        "recordedAt": latest.recorded_at,
                        "observation": latest.observation,
                    },
                    "observed": observed,
                    "evaluation": evaluation_out(
                        getattr(latest, "_measurement_evaluation", None)
                    ),
                }
                if latest is not None
                else None
            ),
        }

    @staticmethod
    def run_row(run: SamplingRun) -> dict:
        return {
            "id": run.id,
            "sample_size": run.sample_size,
            "selection_method": run.selection_method,
            "procedure_code": run.procedure_code,
            "procedure_version_label": run.procedure_version_label,
            "is_ai_recommended": run.is_ai_recommended,
            "seed": run.seed,
            "randomization": run.randomization,
            "created_by": run.created_by,
            "created_at": run.created_at,
        }

    def _lot_progress(self, lot: Lot) -> dict:
        """Progress from real package states — e.g. 7/10 measurements done."""
        packages = lot.packages
        sampled = [
            p
            for p in packages
            if p.status
            in (LotPackageStatus.PENDING.value, LotPackageStatus.MEASURED.value)
        ]
        measured = [
            p for p in packages if p.status == LotPackageStatus.MEASURED.value
        ]
        remaining = len(sampled) - len(measured)
        return {
            "packages_total": len(packages),
            "sampled": len(sampled),
            "measured": len(measured),
            "remaining": remaining,
            "summary": (
                f"{len(measured)} / {len(sampled)} measurements completed"
                if sampled
                else "No sample drawn yet"
            ),
            "action": (
                "Continue Lot Verification" if remaining > 0 else None
            ),
        }

    def _statistics(self, lot: Lot, packages: list) -> dict:
        """OBSERVED statistics computed from measurement rows that exist.

        Every label says "observed": these are arithmetic facts, not legal
        compliance results. The count exceeding threshold counts frozen
        evaluations with outcome EXCEEDS_TOLERANCE (only those the
        configured rule actually produced).
        """
        measured_rows = []
        for package, tasks in packages:
            if package.status != LotPackageStatus.MEASURED.value:
                continue
            for task in tasks:
                if task.task_type != VerificationTaskType.MEASUREMENT.value:
                    continue
                latest = task.latest_result
                if latest is not None and latest.measured_value is not None:
                    measured_rows.append((package, task, latest))

        evaluated = 0
        exceeding = 0
        for _, _, latest in measured_rows:
            evaluation = getattr(latest, "_measurement_evaluation", None)
            if evaluation is not None and evaluation.outcome:
                evaluated += 1
                if evaluation.outcome == MeasurementOutcome.EXCEEDS_TOLERANCE.value:
                    exceeding += 1

        # Average measured: only over measurements that normalize to the
        # declared dimension, expressed in the DECLARED unit.
        parsed = parse_declared_quantity(lot.declared_value)
        average = None
        average_note = None
        normalized_values = []
        if parsed is not None:
            try:
                declared_unit = normalize_unit(parsed[1])
                for _, _, latest in measured_rows:
                    if not latest.unit:
                        continue
                    normalized = normalize_quantity(
                        latest.measured_value, latest.unit
                    )
                    declared = normalize_quantity(parsed[0], declared_unit)
                    if normalized.dimension == declared.dimension:
                        # Value expressed in the declared unit.
                        factor = {
                            "mg": Decimal("0.001"),
                            "g": Decimal("1"),
                            "kg": Decimal("1000"),
                            "ml": Decimal("1"),
                            "l": Decimal("1000"),
                        }[declared_unit]
                        normalized_values.append(
                            normalized.value / factor
                        )
                if normalized_values:
                    average = plain_decimal(
                        sum(normalized_values) / len(normalized_values)
                    )
                elif measured_rows:
                    average_note = (
                        "Average not computed — the measured values cannot "
                        "be normalized against the declared unit."
                    )
            except Exception:  # noqa: BLE001 - dimension mismatch etc.
                average_note = (
                    "Average not computed — the measured values cannot be "
                    "normalized against the declared unit."
                )
        elif measured_rows:
            average_note = (
                "Average not computed — the declared value is not a "
                "parseable quantity+unit pair."
            )

        # Observed deficiencies: comparable measurements below the declared
        # value (an arithmetic fact, not a legal conclusion).
        deficiencies = 0
        for _, _, latest in measured_rows:
            observed = observed_difference(
                lot.declared_value, latest.measured_value, latest.unit or ""
            )
            if observed and observed.get("comparable"):
                try:
                    if Decimal(observed["difference"]) < 0:
                        deficiencies += 1
                except Exception:  # noqa: BLE001 - defensive
                    pass

        return {
            "sampled": sum(
                1
                for p, _ in packages
                if p.status
                in (LotPackageStatus.PENDING.value, LotPackageStatus.MEASURED.value)
            ),
            "measured": len(measured_rows),
            "average_measured": average,
            "average_note": average_note,
            "observed_deficiencies": deficiencies,
            "exceeding_threshold": exceeding,
            "evaluated": evaluated,
            "note": (
                "Observed statistics computed from recorded measurements — "
                "NOT legal compliance results. Only the regulatory "
                "evaluation (where configured) and the inspector may draw "
                "conclusions."
            ),
        }

    def _sampling_procedure_out(self, procedure, db: Session) -> dict | None:
        """Read-model shape of the configured sampling procedure (or None —
        'not configured' is a fact the UI must surface, never a default)."""
        if procedure is None:
            return None
        config = procedure.configuration or {}
        return {
            "code": procedure.code,
            "title": procedure.title,
            "sample_size": (
                config.get("sampleSize")
                if isinstance(config.get("sampleSize"), int)
                else None
            ),
            "method": config.get("method") if isinstance(config.get("method"), str) else None,
            "source_reference": procedure.source_reference,
            "version_label": self._procedure_version_label(db, procedure),
        }

    def _resolve_sampling_procedure(self, db: Session):
        """The configured SAMPLING procedure for the applicable version, or
        None. Deterministic: same DB state → same answer."""
        from app.models import RegulatoryProcedure

        if self._regulatory is None:
            return None
        resolution = RequirementResolver(self._regulatory).resolve_version(
            db, at=utcnow()
        )
        if resolution.version is None:
            return None
        return db.execute(
            select(RegulatoryProcedure)
            .where(
                RegulatoryProcedure.regulation_version_id == resolution.version.id,
                RegulatoryProcedure.kind == RegulatoryProcedureKind.SAMPLING.value,
                RegulatoryProcedure.active.is_(True),
                RegulatoryProcedure.is_demo.is_(False),
            )
            .order_by(RegulatoryProcedure.code.asc())
            .limit(1)
        ).scalar_one_or_none()

    def _procedure_version_label(
        self, db: Session, procedure
    ) -> str | None:
        from app.models import RegulationVersion

        version = db.get(RegulationVersion, procedure.regulation_version_id)
        return version.version_label if version else None

    # --------------------------------------------------------------- guard

    def _assert_actor(
        self, db: Session, inspection_id: uuid.UUID, actor: User
    ) -> None:
        """Lot operations follow the verification RBAC: inspector, supervisor
        or admin, with the UI-05 assignment guard delegated to the
        verification service semantics (an inspector may not act on an
        inspection formally assigned to someone else)."""
        from app.models import Inspection

        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        if actor.role not in _LOT_ROLES:
            raise ForbiddenError(
                "Only an inspector, supervisor or admin may work with lots "
                "and physical verification."
            )
        if actor.role == UserRole.INSPECTOR.value:
            # Reuse the exact verification assignment guard (UI-05
            # semantics): constructing the service is cheap and stateless —
            # the guard logic must exist exactly once.
            from app.services.verification.service import VerificationService

            VerificationService(
                self._audit, self._regulatory
            )._assert_actor_may_verify(db, inspection_id, actor)
