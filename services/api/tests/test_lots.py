"""Lot intelligence + physical verification integration tests (UI-07).

Covers the contract (spec §15–§30, §33–§43):

* LOT → PACKAGES → SAMPLE → MEASUREMENTS → EVALUATION → LOT RESULT, built
  from REAL records only — no fabricated package or sample data
* sampling: AI-recommended requires inspector confirmation (exact 422
  message); a configured legal procedure drives size/method and is referenced
  by code + version; RANDOM draws are seeded and reproducible, never
  regenerated on read, never silently replaced after a measurement
* statistics are OBSERVED values from measurement rows, labelled as such
* the lot decision is explicit and GATED: missing evidence blocks it with
  "Insufficient evidence", it never implies an outcome
* lot-anchored tasks gate the LOT decision, NOT the inspection decision
* RBAC: anonymous 401; AUDITOR read-only (403 on every write); the write
  roles are assignment-guarded
* audit: lot created, sample generated, decision submitted — append-only rows
"""
from __future__ import annotations

import random
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import delete, select

from app.core.enums import AuditEventType, RegulatoryProcedureKind
from app.models import LotPackage, RegulatoryProcedure, User

from tests.test_compliance_engine import _make_inspection
from tests.test_measurement_eval import _active_version

API = "/api/v1"
INSPECTOR_EMAIL = "inspector@legalmet.local"


def _inspector_id(db) -> uuid.UUID:
    return db.execute(
        select(User.id).where(User.email == INSPECTOR_EMAIL)
    ).scalar_one()


@contextmanager
def _sampling_procedure(db, *, code="TEST-SAMPLING", configuration):
    """Seed a SAMPLING procedure; remove it afterwards (shared session DB)."""
    procedure = RegulatoryProcedure(
        regulation_version_id=_active_version(db).id,
        kind=RegulatoryProcedureKind.SAMPLING.value,
        code=code,
        title=f"[TEST] {code}",
        configuration=configuration,
        active=True,
        is_demo=False,
    )
    db.add(procedure)
    db.commit()
    try:
        yield procedure
    finally:
        db.execute(
            delete(RegulatoryProcedure).where(RegulatoryProcedure.id == procedure.id)
        )
        db.commit()


def _create_lot(
    client,
    headers,
    inspection_id,
    *,
    label=None,
    declared="500 g",
    lot_size=10,
):
    resp = client.post(
        f"{API}/inspections/{inspection_id}/lots",
        headers=headers,
        json={
            "label": label or f"LOT-{uuid.uuid4().hex[:6].upper()}",
            "declaredValue": declared,
            "lotSize": lot_size,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _draw_sample(client, headers, lot_id, *, size=2, seed="seed-01", confirm=True):
    resp = client.post(
        f"{API}/lots/{lot_id}/sample",
        headers=headers,
        json={
            "sampleSize": size,
            "selectionMethod": "RANDOM",
            "seed": seed,
            "confirmAiSample": confirm,
        },
    )
    return resp


def _sampled_packages(lot_detail: dict) -> list[dict]:
    return [p for p in lot_detail["packages"] if p["status"] == "PENDING"]


def _measure_package(client, headers, inspection_id, package, value, unit):
    """Create + complete the lot-anchored MEASUREMENT task for one package."""
    resp = client.post(
        f"{API}/inspections/{inspection_id}/verifications",
        headers=headers,
        json={
            "lotPackageId": package["id"],
            "type": "MEASUREMENT",
            "reason": "Physical measurement of a sampled lot package.",
        },
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["id"]
    resp = client.post(
        f"{API}/verifications/{task_id}/result",
        headers=headers,
        json={
            "measuredValue": value,
            "unit": unit,
            "instrumentId": "SCALE-01",
            "instrumentVerificationStatus": "CALIBRATED_2026",
        },
    )
    assert resp.status_code == 200, resp.text
    return task_id


@pytest.fixture()
def inspection(db):
    return _make_inspection(db)


@pytest.fixture()
def lot(client, inspector_headers, inspection):
    return _create_lot(client, inspector_headers, inspection.id)


class TestLotCreation:
    def test_create_builds_real_package_records(self, client, inspector_headers, inspection, db):
        detail = _create_lot(
            client, inspector_headers, inspection.id, label="LOT-A", lot_size=3
        )
        assert detail["status"] == "IN_PROGRESS"
        assert detail["declaredValue"] == "500 g"
        assert detail["lotSize"] == 3
        assert [p["label"] for p in detail["packages"]] == [
            "LOT-A-PKG-001",
            "LOT-A-PKG-002",
            "LOT-A-PKG-003",
        ]
        assert all(p["status"] == "NOT_SAMPLED" for p in detail["packages"])
        assert all(p["measurement"] is None for p in detail["packages"])
        assert detail["progress"]["summary"] == "No sample drawn yet"
        # Real DB rows, not a generated view.
        rows = db.execute(
            select(LotPackage).where(LotPackage.lot_id == uuid.UUID(detail["id"]))
        ).scalars().all()
        assert len(rows) == 3
        assert {r.position for r in rows} == {1, 2, 3}

    def test_creation_is_audited(self, client, inspector_headers, inspection, db, lot):
        from app.models import AuditEvent

        event = db.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "lot",
                AuditEvent.entity_id == uuid.UUID(lot["id"]),
            )
        ).scalar_one()
        assert event.event_type == AuditEventType.LOT_CREATED.value
        assert event.inspection_id == inspection.id
        assert event.payload["declaredValue"] == "500 g"
        assert event.payload["lotSize"] == 10

    @pytest.mark.parametrize(
        "declared",
        ["500", "half kilo", "500 lb", "g", ""],
    )
    def test_unusable_declaration_rejected(
        self, client, inspector_headers, inspection, declared
    ):
        # Unparseable or unsupported-unit declarations are rejected up front —
        # the comparison later needs them, and the system never guesses.
        resp = client.post(
            f"{API}/inspections/{inspection.id}/lots",
            headers=inspector_headers,
            json={"label": "LOT-BAD", "declaredValue": declared, "lotSize": 2},
        )
        assert resp.status_code == 422, resp.text

    def test_lot_size_must_be_positive(self, client, inspector_headers, inspection):
        resp = client.post(
            f"{API}/inspections/{inspection.id}/lots",
            headers=inspector_headers,
            json={"label": "LOT-ZERO", "declaredValue": "500 g", "lotSize": 0},
        )
        assert resp.status_code == 422

    def test_duplicate_label_conflicts(self, client, inspector_headers, inspection):
        _create_lot(client, inspector_headers, inspection.id, label="LOT-DUP")
        resp = client.post(
            f"{API}/inspections/{inspection.id}/lots",
            headers=inspector_headers,
            json={"label": "lot-dup", "declaredValue": "500 g", "lotSize": 2},
        )
        assert resp.status_code == 409

    def test_unknown_inspection_404(self, client, inspector_headers):
        resp = client.post(
            f"{API}/inspections/{uuid.uuid4()}/lots",
            headers=inspector_headers,
            json={"label": "LOT-X", "declaredValue": "500 g", "lotSize": 1},
        )
        assert resp.status_code == 404

    def test_list_carries_progress(self, client, inspector_headers, inspection, lot):
        resp = client.get(
            f"{API}/inspections/{inspection.id}/lots", headers=inspector_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        mine = next(l for l in body["lots"] if l["id"] == lot["id"])
        assert mine["progress"]["packagesTotal"] == 10
        assert body["boundaryNote"]

    def test_rbac(self, client, auditor_headers, inspection, lot):
        assert client.post(
            f"{API}/inspections/{inspection.id}/lots",
            headers=auditor_headers,
            json={"label": "LOT-AUD", "declaredValue": "500 g", "lotSize": 1},
        ).status_code == 403
        assert (
            client.post(
                f"{API}/inspections/{inspection.id}/lots",
                json={"label": "LOT-ANON", "declaredValue": "500 g", "lotSize": 1},
            ).status_code
            == 401
        )
        # Read is open to any authenticated role — auditors must be able to
        # audit (spec §47).
        assert (
            client.get(f"{API}/lots/{lot['id']}", headers=auditor_headers).status_code
            == 200
        )


class TestSampling:
    def test_ai_sample_requires_inspector_confirmation(
        self, client, inspector_headers, lot
    ):
        resp = _draw_sample(client, inspector_headers, lot["id"], confirm=False)
        assert resp.status_code == 422
        assert resp.json()["error"]["message"] == (
            "Sampling procedure requires inspector confirmation."
        )

    def test_ai_sample_requires_explicit_size(self, client, inspector_headers, lot):
        # No configured procedure → no invented sampling percentage (spec §18).
        resp = client.post(
            f"{API}/lots/{lot['id']}/sample",
            headers=inspector_headers,
            json={"confirmAiSample": True},
        )
        assert resp.status_code == 422
        assert "does not" in resp.json()["error"]["message"]

    def test_confirmed_sample_persists(self, client, inspector_headers, lot):
        resp = _draw_sample(client, inspector_headers, lot["id"], size=4)
        assert resp.status_code == 201, resp.text
        run = resp.json()
        assert run["isAiRecommended"] is True
        assert run["procedureCode"] is None
        assert run["seed"]
        assert len(run["randomization"]["selectedPositions"]) == 4

        detail = client.get(
            f"{API}/lots/{lot['id']}", headers=inspector_headers
        ).json()
        sampled = _sampled_packages(detail)
        assert len(sampled) == 4
        assert all(p["samplingRunId"] == run["id"] for p in sampled)
        assert detail["progress"]["summary"] == "0 / 4 measurements completed"

    def test_seed_makes_the_draw_reproducible(self, client, inspector_headers, lot):
        run = _draw_sample(
            client, inspector_headers, lot["id"], size=3, seed="repro-1"
        ).json()
        expected = [
            i + 1
            for i in sorted(random.Random("repro-1").sample(range(10), 3))
        ]
        assert run["randomization"]["selectedPositions"] == expected
        assert run["randomization"]["seedSource"] == "inspector"

        # Re-drawing with the same seed reproduces the same selection…
        again = _draw_sample(
            client, inspector_headers, lot["id"], size=3, seed="repro-1"
        ).json()
        assert again["randomization"]["selectedPositions"] == expected

    def test_sample_is_stable_across_reads(self, client, inspector_headers, lot):
        _draw_sample(client, inspector_headers, lot["id"], size=2)
        first = client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        second = client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        # Reading never regenerates the sample (spec §20).
        assert len(first["samplingRuns"]) == len(second["samplingRuns"]) == 1
        assert _sampled_packages(first) == _sampled_packages(second)

    def test_sample_size_cannot_exceed_lot(self, client, inspector_headers, lot):
        resp = _draw_sample(client, inspector_headers, lot["id"], size=11)
        assert resp.status_code == 422
        assert "exceeds the lot size" in resp.json()["error"]["message"]

    def test_redraw_blocked_after_measurement(
        self, client, inspector_headers, inspection, lot
    ):
        _draw_sample(client, inspector_headers, lot["id"], size=1)
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        )[0]
        _measure_package(client, inspector_headers, inspection.id, package, 492, "g")
        resp = _draw_sample(client, inspector_headers, lot["id"], size=2)
        assert resp.status_code == 409
        assert "cannot be silently replaced" in resp.json()["error"]["message"]

    def test_configured_procedure_drives_size_and_method(self, client, inspector_headers, inspection, db):
        with _sampling_procedure(
            db, configuration={"sampleSize": 2, "method": "RANDOM"}
        ):
            lot = _create_lot(client, inspector_headers, inspection.id)
            # No confirmation needed and the requested size (5) is IGNORED —
            # the configured legal procedure decides.
            resp = client.post(
                f"{API}/lots/{lot['id']}/sample",
                headers=inspector_headers,
                json={"sampleSize": 5, "seed": "proc-1"},
            )
            assert resp.status_code == 201, resp.text
            run = resp.json()
            assert run["isAiRecommended"] is False
            assert run["procedureCode"] == "TEST-SAMPLING"
            assert run["procedureVersionLabel"]
            assert run["sampleSize"] == 2
            detail = client.get(
                f"{API}/lots/{lot['id']}", headers=inspector_headers
            ).json()
            assert detail["samplingProcedure"]["code"] == "TEST-SAMPLING"

    def test_malformed_procedure_is_surfaced(self, client, inspector_headers, inspection, db):
        with _sampling_procedure(db, configuration={"sampleSize": "many"}):
            lot = _create_lot(client, inspector_headers, inspection.id)
            resp = client.post(
                f"{API}/lots/{lot['id']}/sample",
                headers=inspector_headers,
                json={"seed": "x"},
            )
            assert resp.status_code == 422
            assert "malformed" in resp.json()["error"]["message"]

    def test_sampling_is_audited(self, client, inspector_headers, inspection, db, lot):
        run = _draw_sample(client, inspector_headers, lot["id"], size=2).json()
        from app.models import AuditEvent

        event = db.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "sampling_run",
                AuditEvent.entity_id == uuid.UUID(run["id"]),
            )
        ).scalar_one()
        assert event.event_type == AuditEventType.LOT_SAMPLE_GENERATED.value
        assert event.payload["seed"] == run["seed"]
        assert event.payload["selectedPositions"]
        assert event.inspection_id == inspection.id

    def test_rbac(self, client, auditor_headers, lot):
        assert (
            _draw_sample(client, auditor_headers, lot["id"]).status_code == 403
        )
        assert _draw_sample(client, {}, lot["id"]).status_code in (401, 403)


class TestLotMeasurements:
    @pytest.fixture()
    def measured_lot(self, client, inspector_headers, inspection, lot):
        _draw_sample(client, inspector_headers, lot["id"], size=2, seed="m-1")
        detail = client.get(
            f"{API}/lots/{lot['id']}", headers=inspector_headers
        ).json()
        packages = _sampled_packages(detail)
        # 0.492 kg and 505 g against a 500 g declaration — units normalize.
        _measure_package(
            client, inspector_headers, inspection.id, packages[0], 0.492, "kg"
        )
        _measure_package(
            client, inspector_headers, inspection.id, packages[1], 505, "g"
        )
        return client.get(
            f"{API}/lots/{lot['id']}", headers=inspector_headers
        ).json()

    def test_packages_reach_measured_with_real_records(
        self, client, inspector_headers, measured_lot
    ):
        measured = [
            p
            for p in measured_lot["packages"]
            if p["status"] == "MEASURED"
        ]
        assert len(measured) == 2
        for package in measured:
            block = package["measurement"]
            assert block["taskStatus"] == "COMPLETED"
            assert block["latestResult"]["instrumentId"] == "SCALE-01"
            assert (
                block["latestResult"]["instrumentVerificationStatus"]
                == "CALIBRATED_2026"
            )
            assert block["observed"]["comparable"] is True

    def test_statistics_are_observed_not_legal(
        self, client, inspector_headers, measured_lot
    ):
        stats = measured_lot["statistics"]
        assert stats["sampled"] == 2
        assert stats["measured"] == 2
        # (0.492 kg + 505 g) / 2 → 498.5 g, in the DECLARED unit.
        assert stats["averageMeasured"] == "498.5"
        assert stats["observedDeficiencies"] == 1  # 492 < 500 (arithmetic fact)
        assert stats["exceedingThreshold"] == 0  # no procedure configured
        assert stats["evaluated"] == 0
        assert "NOT legal compliance results" in stats["note"]
        assert measured_lot["progress"]["summary"] == "2 / 2 measurements completed"
        assert measured_lot["progress"]["remaining"] == 0

    def test_exceeding_threshold_counts_frozen_evaluations(
        self, client, inspector_headers, inspection, db, lot
    ):
        from tests.test_measurement_eval import _procedure

        with _procedure(
            db,
            code="TEST-TOL-LOTS",
            configuration={"permissibleError": {"type": "PERCENT", "value": "1"}},
        ):
            _draw_sample(client, inspector_headers, lot["id"], size=2, seed="e-1")
            detail = client.get(
                f"{API}/lots/{lot['id']}", headers=inspector_headers
            ).json()
            packages = _sampled_packages(detail)
            _measure_package(
                client, inspector_headers, inspection.id, packages[0], 470, "g"
            )
            _measure_package(
                client, inspector_headers, inspection.id, packages[1], 499, "g"
            )
            stats = client.get(
                f"{API}/lots/{lot['id']}", headers=inspector_headers
            ).json()["statistics"]
            assert stats["evaluated"] == 2
            assert stats["exceedingThreshold"] == 1  # -6% vs a 1% limit
            assert stats["observedDeficiencies"] == 2

    def test_lot_tasks_do_not_gate_the_inspection_decision(
        self, client, inspector_headers, inspection, lot, services, db
    ):
        _draw_sample(client, inspector_headers, lot["id"], size=1)
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        )[0]
        # Open, REQUIRED, lot-anchored…
        resp = client.post(
            f"{API}/inspections/{inspection.id}/verifications",
            headers=inspector_headers,
            json={
                "lotPackageId": package["id"],
                "type": "MEASUREMENT",
                "reason": "Lot package measurement pending.",
            },
        )
        assert resp.status_code == 201
        # …but excluded from the INSPECTION decision gate.
        assert services.verification.open_required_tasks(db, inspection.id) == 0
        assert services.verification.required_task_blockers(db, inspection.id) == []

    def test_unsupported_unit_rejected(self, client, inspector_headers, inspection, lot):
        _draw_sample(client, inspector_headers, lot["id"], size=1)
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        )[0]
        task = client.post(
            f"{API}/inspections/{inspection.id}/verifications",
            headers=inspector_headers,
            json={
                "lotPackageId": package["id"],
                "type": "MEASUREMENT",
                "reason": "Weighing the sampled package.",
            },
        ).json()
        resp = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 1.1, "unit": "lb"},
        )
        assert resp.status_code == 422
        assert "Unsupported quantity unit 'lb'" in resp.json()["error"]["message"]

    def test_completed_task_rejects_more_results(
        self, client, inspector_headers, inspection, lot
    ):
        _draw_sample(client, inspector_headers, lot["id"], size=1)
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        )[0]
        task_id = _measure_package(
            client, inspector_headers, inspection.id, package, 492, "g"
        )
        resp = client.post(
            f"{API}/verifications/{task_id}/result",
            headers=inspector_headers,
            json={"measuredValue": 493, "unit": "g"},
        )
        assert resp.status_code == 409  # append-only: a correction is a NEW task

    def test_measurement_history_covers_lot_rows(
        self, client, inspector_headers, inspection, measured_lot
    ):
        resp = client.get(
            f"{API}/inspections/{inspection.id}/measurements",
            headers=inspector_headers,
        )
        assert resp.status_code == 200
        rows = resp.json()["measurements"]
        assert len(rows) == 2
        assert all(r["anchor"]["kind"] == "LOT_PACKAGE" for r in rows)
        assert all(r["declaredValue"] == "500 g" for r in rows)
        assert {r["measuredValue"] for r in rows} == {0.492, 505}
        assert all(r["recordedByName"] for r in rows)

    def test_rbac_citizen_writes_rejected(
        self, client, inspector_headers, auditor_headers, inspection, lot
    ):
        _draw_sample(client, inspector_headers, lot["id"], size=1)
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        )[0]
        # AUDITOR may read evidence but never alter it (spec §47); a citizen
        # has no account at all — anonymous writes are 401.
        resp = client.post(
            f"{API}/inspections/{inspection.id}/verifications",
            headers=auditor_headers,
            json={
                "lotPackageId": package["id"],
                "type": "MEASUREMENT",
                "reason": "Auditor must not create verification tasks.",
            },
        )
        assert resp.status_code == 403
        assert (
            client.post(
                f"{API}/inspections/{inspection.id}/verifications",
                json={
                    "lotPackageId": package["id"],
                    "type": "MEASUREMENT",
                    "reason": "Anonymous must not create tasks.",
                },
            ).status_code
            == 401
        )


class TestLotDecision:
    def test_missing_evidence_blocks_decision(
        self, client, inspector_headers, inspection, lot
    ):
        _draw_sample(client, inspector_headers, lot["id"], size=2)
        detail = client.get(
            f"{API}/lots/{lot['id']}", headers=inspector_headers
        ).json()
        packages = _sampled_packages(detail)
        _measure_package(
            client, inspector_headers, inspection.id, packages[0], 492, "g"
        )
        # 1 of 2 measured — the partial state persists and blocks (spec §24).
        resp = client.post(
            f"{API}/lots/{lot['id']}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All sampled packages within error."},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["message"].startswith(
            "Insufficient evidence — 1 measurement(s) remaining"
        )
        progress = client.get(
            f"{API}/lots/{lot['id']}", headers=inspector_headers
        ).json()["progress"]
        assert progress["summary"] == "1 / 2 measurements completed"
        assert progress["remaining"] == 1

    def test_no_measurements_at_all_blocks(self, client, inspector_headers, lot):
        resp = client.post(
            f"{API}/lots/{lot['id']}/decision",
            headers=inspector_headers,
            json={"decision": "REQUIRES_REVIEW", "reason": "Nothing measured yet."},
        )
        assert resp.status_code == 409
        assert "no package" in resp.json()["error"]["message"]

    def test_decision_after_complete_evidence(
        self, client, inspector_headers, inspection, lot, db
    ):
        from app.models import AuditEvent

        _draw_sample(client, inspector_headers, lot["id"], size=2, seed="d-1")
        detail = client.get(
            f"{API}/lots/{lot['id']}", headers=inspector_headers
        ).json()
        packages = _sampled_packages(detail)
        _measure_package(
            client, inspector_headers, inspection.id, packages[0], 492, "g"
        )
        _measure_package(
            client, inspector_headers, inspection.id, packages[1], 505, "g"
        )
        resp = client.post(
            f"{API}/lots/{lot['id']}/decision",
            headers=inspector_headers,
            json={
                "decision": "COMPLIANT",
                "reason": "Both sampled packages within the permissible error.",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "COMPLIANT"
        assert body["decision"] == "COMPLIANT"
        assert body["decisionReason"].startswith("Both sampled")
        assert body["decidedAt"]

        event = db.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "lot",
                AuditEvent.entity_id == uuid.UUID(lot["id"]),
                AuditEvent.event_type == AuditEventType.LOT_DECISION_SUBMITTED.value,
            )
        ).scalar_one()
        assert event.payload["decision"] == "COMPLIANT"

        # Decisions are append-only: a second submission is a 409.
        again = client.post(
            f"{API}/lots/{lot['id']}/decision",
            headers=inspector_headers,
            json={"decision": "NON_COMPLIANT", "reason": "Changed my mind."},
        )
        assert again.status_code == 409

        # And a decided lot no longer accepts a new sample.
        assert (
            _draw_sample(client, inspector_headers, lot["id"]).status_code == 409
        )

    @pytest.mark.parametrize("decision", ["IN_PROGRESS", "BOGUS"])
    def test_non_result_decisions_rejected(
        self, client, inspector_headers, lot, decision
    ):
        resp = client.post(
            f"{API}/lots/{lot['id']}/decision",
            headers=inspector_headers,
            json={"decision": decision, "reason": "Invalid decision value."},
        )
        assert resp.status_code == 422

    def test_reason_mandatory(self, client, inspector_headers, lot):
        resp = client.post(
            f"{API}/lots/{lot['id']}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": ""},
        )
        assert resp.status_code == 422

    def test_rbac(self, client, auditor_headers, lot):
        assert (
            client.post(
                f"{API}/lots/{lot['id']}/decision",
                headers=auditor_headers,
                json={"decision": "COMPLIANT", "reason": "Auditors cannot decide."},
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"{API}/lots/{lot['id']}/decision",
                json={"decision": "COMPLIANT", "reason": "Anonymous cannot decide."},
            ).status_code
            == 401
        )


class TestEvidenceGraphAndDashboard:
    def test_graph_traces_the_lot_chain(
        self, client, inspector_headers, inspection, lot
    ):
        _draw_sample(client, inspector_headers, lot["id"], size=1, seed="g-1")
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot['id']}", headers=inspector_headers).json()
        )[0]
        _measure_package(client, inspector_headers, inspection.id, package, 492, "g")

        resp = client.get(
            f"{API}/inspections/{inspection.id}/evidence-graph",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        graph = resp.json()
        types = {n["type"] for n in graph["nodes"]}
        assert "LOT" in types
        assert "LOT_PACKAGE" in types
        assert "SAMPLING_RUN" in types
        assert "MEASUREMENT" in types
        edges = {(e["source"], e["type"], e["target"]) for e in graph["edges"]}
        edge_types = {t for _, t, _ in edges}
        assert "INSPECTION_HAS_LOT" in edge_types
        assert "LOT_HAS_PACKAGE" in edge_types
        assert "LOT_HAS_SAMPLING_RUN" in edge_types
        assert "SAMPLING_RUN_SELECTED_PACKAGE" in edge_types
        # MEASUREMENT → INSTRUMENT → record, and the frozen evaluation.
        assert "INSTRUMENT" in types
        assert "MEASUREMENT_EVALUATION" in types
        assert "INSTRUMENT_USED_FOR_MEASUREMENT" in edge_types
        assert "MEASUREMENT_VERIFIES_LOT_PACKAGE" in edge_types

    def test_dashboard_physical_verification_block(
        self, client, inspector_headers, inspection
    ):
        # Lot A: sampled AND measured (feeds measurementsCompleted).
        lot_a = _create_lot(client, inspector_headers, inspection.id)
        _draw_sample(client, inspector_headers, lot_a["id"], size=1)
        package = _sampled_packages(
            client.get(f"{API}/lots/{lot_a['id']}", headers=inspector_headers).json()
        )[0]
        _measure_package(client, inspector_headers, inspection.id, package, 492, "g")

        # Lot B: sampled but NOT measured (feeds lotsAwaitingMeasurement) —
        # the partial state the dashboard must surface as work to do.
        lot_b = _create_lot(client, inspector_headers, inspection.id)
        _draw_sample(client, inspector_headers, lot_b["id"], size=1)

        resp = client.get(
            f"{API}/department/dashboard", headers=inspector_headers
        )
        assert resp.status_code == 200
        block = resp.json()["physicalVerification"]
        # Real counts over the whole DB: at least what this test just created.
        assert block["measurementsCompleted"] >= 1
        assert block["lotsUnderVerification"] >= 1
        assert block["lotsAwaitingMeasurement"] >= 1
        # Every key is present — the UI never renders a fabricated metric.
        assert set(block) == {
            "inspectionsRequiringVerification",
            "measurementsCompleted",
            "lotsUnderVerification",
            "lotsAwaitingMeasurement",
            "lotsCompleted",
        }
