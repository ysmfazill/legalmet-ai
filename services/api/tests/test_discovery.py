"""UI-09 discovery & operational intelligence tests.

Covers the contract (spec §2–§26, §27–§30, §33):

* global search: grouped hits across the six categories, case-insensitive,
  server-side; anonymous access 401; citizen reporter PII never returned
* inspection history: real KPI counts, server-side filters (result / source /
  status / date / query), pagination, timeline built ONLY from recorded events
* product repository: searchable list + historical detail (declared fields,
  inspection history, recurring findings, evidence gallery, boundary note)
* operational analytics: every figure cross-checked against another endpoint's
  real counts (no fabricated numbers); complaint pipeline stages; evidence
  quality (REQUIRED-only); repeat findings across inspections of one product
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.models import (
    CitizenReport,
    CitizenScan,
    ComplianceEvaluation,
    EvaluationFinding,
    Inspection,
    Rule,
    User,
    VerificationTask,
)
from tests.conftest import TINY_PNG_BASE64

API = "/api/v1"
INSPECTOR_EMAIL = "inspector@legalmet.local"


# --------------------------------------------------------------------- helpers


def _make_analyzed(client, headers, product_name="SearchTest Tea 250g"):
    """A real inspection with an image + a completed engine evaluation."""
    create = client.post(
        f"{API}/inspections",
        headers=headers,
        json={"productName": product_name, "productCategory": "food"},
    )
    assert create.status_code == 201, create.text
    inspection_id = create.json()["id"]

    image = client.post(
        f"{API}/inspections/{inspection_id}/images",
        headers=headers,
        json={
            "originalFilename": "front.png",
            "mimeType": "image/png",
            "imageType": "FRONT",
            "contentBase64": TINY_PNG_BASE64,
            "width": 1200,
            "height": 1600,
            "fileSize": 2048,
        },
    )
    assert image.status_code == 201, image.text

    analyze = client.post(
        f"{API}/inspections/{inspection_id}/analyze",
        headers=headers,
        json={"contextDate": "2026-06-01"},
    )
    assert analyze.status_code == 200, analyze.text

    evaluate = client.post(f"{API}/inspections/{inspection_id}/evaluate", headers=headers)
    assert evaluate.status_code == 200, evaluate.text
    return inspection_id


def _make_complaint(db, *, status="ACCEPTED", location="Test Market, Delhi", inspection_id=None):
    """A real CitizenReport row (scan + report) with an optional inspection link."""
    scan = CitizenScan(
        reference=f"CSC-{uuid.uuid4().hex[:10].upper()}",
        storage_key=f"citizen/{uuid.uuid4().hex}.png",
        filename="package.png",
        outcome="POSSIBLE_ISSUE",
        is_live=True,
    )
    db.add(scan)
    db.flush()
    report = CitizenReport(
        reference=f"CMP-{uuid.uuid4().hex[:10].upper()}",
        scan_id=scan.id,
        status=status,
        product="SearchTest Tea 250g",
        issue="Declared quantity looks wrong",
        location=location,
        reporter_name="Secret Citizen Name",
        reporter_contact="secret@example.invalid",
        inspection_id=uuid.UUID(inspection_id) if inspection_id else None,
        is_live=True,
    )
    db.add(report)
    db.commit()
    return report


def _inspector_user(db):
    return db.execute(select(User).where(User.email == INSPECTOR_EMAIL)).scalar_one()


def _make_required_task(db, inspection_id, *, status="PENDING"):
    task = VerificationTask(
        inspection_id=uuid.UUID(inspection_id),
        task_type="MEASUREMENT",
        requirement_level="REQUIRED",
        reason="Net quantity must be physically measured",
        status=status,
        created_by=_inspector_user(db).id,
    )
    db.add(task)
    db.commit()
    return task


def _engine_findings(client, headers, inspection_id):
    return client.get(
        f"{API}/inspections/{inspection_id}/compliance/findings", headers=headers
    ).json()


# --------------------------------------------------------------- global search


class TestGlobalSearch:
    def test_anonymous_401(self, client):
        assert client.get(f"{API}/search", params={"q": "tea"}).status_code == 401

    def test_finds_inspection_and_product_by_name(
        self, client, inspector_headers
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        resp = client.get(
            f"{API}/search", headers=inspector_headers, params={"q": "searchtest tea"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["query"] == "searchtest tea"
        inspection_hits = body["inspections"]
        assert any(h["id"] == inspection_id for h in inspection_hits)
        assert any(
            h["name"] == "SearchTest Tea 250g" for h in body["products"]
        )

    def test_short_query_returns_empty_groups(self, client, inspector_headers):
        resp = client.get(f"{API}/search", headers=inspector_headers, params={"q": "t"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["inspections"] == []
        assert body["complaints"] == []

    def test_complaint_hit_has_no_reporter_pii(self, client, inspector_headers, db):
        complaint = _make_complaint(db, status="UNDER_REVIEW")
        resp = client.get(
            f"{API}/search",
            headers=inspector_headers,
            params={"q": complaint.reference},
        )
        assert resp.status_code == 200
        raw = resp.text
        # The hit is returned…
        assert any(
            h["reference"] == complaint.reference for h in resp.json()["complaints"]
        )
        # …but the reporter's name/contact never leaves the server (§28).
        assert "Secret Citizen Name" not in raw
        assert "secret@example.invalid" not in raw
        for hit in resp.json()["complaints"]:
            assert "reporterName" not in hit
            assert "reporterContact" not in hit

    def test_finds_engine_finding_by_rule_code(self, client, inspector_headers):
        inspection_id = _make_analyzed(client, inspector_headers)
        findings = _engine_findings(client, inspector_headers, inspection_id)
        assert findings, "engine evaluation should produce findings"
        # The frozen requirement citation (always recorded in provenance).
        rule_code = findings[0]["provenance"]["requirementCode"]
        assert rule_code
        resp = client.get(
            f"{API}/search", headers=inspector_headers, params={"q": rule_code}
        )
        assert resp.status_code == 200
        assert resp.json()["findings"], f"expected finding hits for {rule_code}"
        hit = resp.json()["findings"][0]
        assert hit["inspectionReference"]

    def test_finds_finding_and_evidence_by_id(self, client, inspector_headers):
        """§3: search by finding ID and evidence ID."""
        inspection_id = _make_analyzed(client, inspector_headers)
        findings = _engine_findings(client, inspector_headers, inspection_id)
        assert findings
        resp = client.get(
            f"{API}/search",
            headers=inspector_headers,
            params={"q": findings[0]["id"]},
        )
        assert resp.status_code == 200
        assert any(
            h["id"] == findings[0]["id"] for h in resp.json()["findings"]
        )

        evidence = client.get(
            f"{API}/search", headers=inspector_headers, params={"q": "MRP"}
        ).json()["evidence"]
        assert evidence
        by_id = client.get(
            f"{API}/search", headers=inspector_headers, params={"q": evidence[0]["id"]}
        ).json()["evidence"]
        assert any(h["id"] == evidence[0]["id"] for h in by_id)

    def test_finds_evidence_by_extracted_text(self, client, inspector_headers):
        _make_analyzed(client, inspector_headers)
        # The demo mock extraction writes MRP text; search the field type.
        resp = client.get(
            f"{API}/search", headers=inspector_headers, params={"q": "MRP"}
        )
        assert resp.status_code == 200
        assert resp.json()["evidence"], "expected evidence hits for MRP"

    def test_limit_is_bounded(self, client, inspector_headers):
        assert (
            client.get(
                f"{API}/search", headers=inspector_headers, params={"q": "e", "limit": 0}
            ).status_code
            == 422
        )
        assert (
            client.get(
                f"{API}/search", headers=inspector_headers, params={"q": "e", "limit": 21}
            ).status_code
            == 422
        )


# ---------------------------------------------------------- inspection history


class TestInspectionHistory:
    def test_anonymous_401(self, client):
        assert client.get(f"{API}/history/inspections").status_code == 401

    def test_lists_inspections_with_real_kpis(self, client, inspector_headers):
        before = client.get(
            f"{API}/history/inspections", headers=inspector_headers
        ).json()
        _make_analyzed(client, inspector_headers)
        after = client.get(
            f"{API}/history/inspections", headers=inspector_headers
        ).json()

        assert after["total"] == before["total"] + 1
        assert after["kpis"]["total"] == after["total"]
        # KPI buckets can never disagree with the table (same filtered set).
        assert (
            after["kpis"]["compliant"]
            + after["kpis"]["nonCompliant"]
            + after["kpis"]["reviewRequired"]
            <= after["kpis"]["total"]
        )
        item = after["items"][0]
        for key in (
            "id",
            "reference",
            "createdAt",
            "status",
            "result",
            "source",
        ):
            assert key in item

    def test_filter_by_result_uses_human_decision(
        self, client, inspector_headers
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        decision = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All requirements verified."},
        )
        assert decision.status_code in (200, 201), decision.text

        resp = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"result": "COMPLIANT"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert all(item["result"] == "COMPLIANT" for item in body["items"])
        assert any(item["id"] == inspection_id for item in body["items"])

    def test_filter_by_source_citizen_complaint(
        self, client, inspector_headers, db
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        _make_complaint(db, status="INSPECTION_COMPLETED", inspection_id=inspection_id)

        complaint_led = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"source": "CITIZEN_COMPLAINT"},
        ).json()
        assert any(item["id"] == inspection_id for item in complaint_led["items"])
        assert all(
            item["source"] == "CITIZEN_COMPLAINT" for item in complaint_led["items"]
        )
        assert any(
            item["id"] == inspection_id and item["sourceComplaintReference"]
            for item in complaint_led["items"]
        )

        direct = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"source": "DIRECT_INSPECTION"},
        ).json()
        assert all(item["source"] == "DIRECT_INSPECTION" for item in direct["items"])
        assert not any(item["id"] == inspection_id for item in direct["items"])

    def test_filter_by_status_and_date_range(self, client, inspector_headers):
        inspection_id = _make_analyzed(client, inspector_headers)

        analyzed = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"status": "ANALYZED"},
        ).json()
        assert any(item["id"] == inspection_id for item in analyzed["items"])
        assert all(item["status"] == "ANALYZED" for item in analyzed["items"])

        # A window that ends before the inspection was created excludes it.
        early = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"dateTo": "2020-01-01T00:00:00Z"},
        ).json()
        assert not any(item["id"] == inspection_id for item in early["items"])
        # A window starting before everything includes it.
        late = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"dateFrom": "2020-01-01T00:00:00Z"},
        ).json()
        assert any(item["id"] == inspection_id for item in late["items"])

    def test_query_filter_by_reference(self, client, inspector_headers):
        inspection_id = _make_analyzed(client, inspector_headers)
        inspection = client.get(
            f"{API}/inspections/{inspection_id}", headers=inspector_headers
        ).json()
        reference = inspection["referenceNo"]
        # A lowercase partial of the reference still matches (trimmed + case-insensitive).
        resp = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"q": reference.lower()[:8]},
        ).json()
        assert any(item["id"] == inspection_id for item in resp["items"])

    def test_pagination_is_consistent(self, client, inspector_headers):
        total = client.get(
            f"{API}/history/inspections", headers=inspector_headers
        ).json()["total"]
        if total < 2:
            _make_analyzed(client, inspector_headers)
            total = client.get(
                f"{API}/history/inspections", headers=inspector_headers
            ).json()["total"]
        page1 = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"page": 1, "pageSize": 1},
        ).json()
        page2 = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"page": 2, "pageSize": 1},
        ).json()
        assert len(page1["items"]) == 1
        assert len(page2["items"]) == 1
        assert page1["items"][0]["id"] != page2["items"][0]["id"]
        assert page1["total"] == page2["total"] == total

    def test_timeline_shows_only_recorded_events(
        self, client, inspector_headers
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        resp = client.get(
            f"{API}/history/inspections/{inspection_id}/timeline",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        stages = [event["stage"] for event in body["events"]]
        # The anchor always exists (§8: INSPECTION CREATED first).
        assert "INSPECTION_CREATED" in stages
        # The engine ran → findings were generated for real.
        assert "FINDINGS_GENERATED" in stages
        # Nothing was reported or decided → those stages must NOT appear.
        assert "REPORT_GENERATED" not in stages
        assert "REPORT_FINALIZED" not in stages
        assert "DECISION" not in stages
        # Chronological order.
        times = [event["at"] for event in body["events"]]
        assert times == sorted(times)

    def test_timeline_unknown_inspection_404(self, client, inspector_headers):
        assert (
            client.get(
                f"{API}/history/inspections/{uuid.uuid4()}/timeline",
                headers=inspector_headers,
            ).status_code
            == 404
        )

    def test_timeline_grows_with_real_actions(self, client, inspector_headers):
        inspection_id = _make_analyzed(client, inspector_headers)
        decision = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All requirements verified."},
        )
        assert decision.status_code in (200, 201), decision.text

        timeline = client.get(
            f"{API}/history/inspections/{inspection_id}/timeline",
            headers=inspector_headers,
        ).json()
        stages = [event["stage"] for event in timeline["events"]]
        assert "DECISION" in stages
        decision_event = next(e for e in timeline["events"] if e["stage"] == "DECISION")
        assert decision_event["decision"] == "COMPLIANT"
        assert decision_event["actorName"]  # a human, by name


# --------------------------------------------------------- product repository


class TestProductRepository:
    def test_anonymous_401(self, client):
        assert client.get(f"{API}/products").status_code == 401

    def test_list_and_query(self, client, inspector_headers):
        _make_analyzed(client, inspector_headers, product_name="Repo Chips 100g")
        listing = client.get(
            f"{API}/products", headers=inspector_headers, params={"q": "repo chips"}
        )
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] >= 1
        assert any(item["name"] == "Repo Chips 100g" for item in body["items"])
        item = body["items"][0]
        assert item["inspectionCount"] >= 1

    def test_detail_is_a_historical_record(self, client, inspector_headers):
        product_name = "Repo Biscuits 200g"
        inspection_id = _make_analyzed(client, inspector_headers, product_name=product_name)
        product_id = client.get(
            f"{API}/inspections/{inspection_id}", headers=inspector_headers
        ).json()["productId"]

        detail = client.get(f"{API}/products/{product_id}", headers=inspector_headers)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["name"] == product_name
        assert body["inspectionCount"] >= 1
        # The honesty contract is carried verbatim (§11).
        assert "Historical inspection record" in body["boundaryNote"]
        assert "do not prove current compliance" in body["boundaryNote"]
        # Real linked sections, keyed to real rows.
        assert any(i["id"] == inspection_id for i in body["inspections"])
        assert isinstance(body["findingsHistory"], list)
        gallery = body["evidenceGallery"]
        assert len(gallery) >= 1  # the FRONT image captured above
        assert gallery[0]["inspectionReference"]
        assert isinstance(gallery[0]["fieldTypes"], list)

    def test_detail_unknown_404(self, client, inspector_headers):
        assert (
            client.get(f"{API}/products/{uuid.uuid4()}", headers=inspector_headers).status_code
            == 404
        )

    def test_history_filter_by_product_id(self, client, inspector_headers):
        """Explicit §33 coverage: filtering history by product works."""
        inspection_id = _make_analyzed(client, inspector_headers, product_name="Repo Juice 1L")
        product_id = client.get(
            f"{API}/inspections/{inspection_id}", headers=inspector_headers
        ).json()["productId"]
        resp = client.get(
            f"{API}/history/inspections",
            headers=inspector_headers,
            params={"productId": str(product_id)},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


# ------------------------------------------------------- operational analytics


class TestOperationalAnalytics:
    def test_anonymous_401(self, client):
        assert client.get(f"{API}/analytics/operational").status_code == 401

    def test_invalid_granularity_422(self, client, inspector_headers):
        assert (
            client.get(
                f"{API}/analytics/operational",
                headers=inspector_headers,
                params={"granularity": "century"},
            ).status_code
            == 422
        )

    def test_kpis_agree_with_history_counts(self, client, inspector_headers):
        """Cross-check: the analytics totals must equal the history totals over
        the same database (§34 — every number has a clear source)."""
        _make_analyzed(client, inspector_headers)
        operational = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()
        history = client.get(
            f"{API}/history/inspections", headers=inspector_headers
        ).json()

        assert operational["kpis"]["totalInspections"] == history["kpis"]["total"]
        assert operational["kpis"]["openInspections"] == history["kpis"]["open"]
        # Outcome slices partition the same total.
        assert sum(slice["count"] for slice in operational["outcomes"]) == history["total"]

    def test_trend_points_sum_to_total(self, client, inspector_headers):
        _make_analyzed(client, inspector_headers)
        body = client.get(
            f"{API}/analytics/operational",
            headers=inspector_headers,
            params={"granularity": "day"},
        ).json()
        assert body["granularity"] == "day"
        total = client.get(
            f"{API}/history/inspections", headers=inspector_headers
        ).json()["total"]
        assert sum(point["count"] for point in body["trend"]) == total

    def test_complaint_pipeline_stages_are_real_counts(
        self, client, inspector_headers, db
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        before = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["complaintPipeline"]
        _make_complaint(db, status="INSPECTION_COMPLETED", inspection_id=inspection_id)
        _make_complaint(db, status="SUBMITTED")
        after = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["complaintPipeline"]

        stages = {s["stage"]: s["count"] for s in after["stages"]}
        assert [s["stage"] for s in after["stages"]] == [
            "COMPLAINTS",
            "REVIEWED",
            "ACCEPTED",
            "INSPECTIONS",
            "COMPLETED",
            "FINDINGS",
        ]
        # Two more complaints exist now.
        assert stages["COMPLAINTS"] == (
            {s["stage"]: s["count"] for s in before["stages"]}["COMPLAINTS"] + 2
        )
        # One is linked to a real inspection with an evaluation → FINDINGS >= 1.
        assert stages["INSPECTIONS"] >= 1
        assert stages["FINDINGS"] >= 1
        # Monotone funnel over the shared machine vocabulary.
        assert stages["REVIEWED"] <= stages["COMPLAINTS"]
        if after["conversionRate"] is not None:
            assert 0.0 <= after["conversionRate"] <= 1.0

    def test_evidence_quality_counts_required_only(
        self, client, inspector_headers, db
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        before = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["evidenceQuality"]
        _make_required_task(db, inspection_id, status="PENDING")
        after = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["evidenceQuality"]

        assert after["missingRequiredEvidence"] == before["missingRequiredEvidence"] + 1
        assert after["incompleteInspections"] >= 1
        assert after["measurementsPending"] >= 1
        assert after["inspectionsWithPlanner"] >= 1

    def test_reports_blocked_by_open_required_evidence(
        self, client, inspector_headers, db
    ):
        """The report gate, reflected in analytics: a GENERATED report with an
        open REQUIRED task counts as blocked."""
        inspection_id = _make_analyzed(client, inspector_headers)
        _make_required_task(db, inspection_id, status="PENDING")
        report = client.post(
            f"{API}/reports",
            headers=inspector_headers,
            json={"inspectionId": str(inspection_id)},
        )
        assert report.status_code == 201, report.text
        generate = client.post(
            f"{API}/reports/{report.json()['id']}/generate", headers=inspector_headers
        )
        assert generate.status_code == 200, generate.text

        quality = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["evidenceQuality"]
        assert quality["reportsBlockedByEvidence"] >= 1

    def test_finding_categories_come_from_real_rules(
        self, client, inspector_headers, db
    ):
        inspection_id = _make_analyzed(client, inspector_headers)
        findings = _engine_findings(client, inspector_headers, inspection_id)
        body = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()
        categories = body["findingCategories"]
        assert categories, "at least one real rule category must exist"
        # Every category shown is a REAL seeded requirement citation (§18 —
        # categories only ever come from the existing rule system).
        real_codes = set(
            db.execute(select(Rule.rule_code)).scalars().all()
        )
        for category in categories:
            assert category["ruleCode"] in real_codes
            assert category["count"] >= 1
            assert category["inspectionCount"] >= 1
        # The just-evaluated inspection's citations are real rule codes too,
        # and at least one of them made the top list.
        evaluated = {f["provenance"]["requirementCode"] for f in findings}
        assert evaluated <= real_codes
        assert evaluated & {c["ruleCode"] for c in categories}

    def test_repeat_findings_across_evaluations_of_one_product(
        self, client, inspector_headers, db
    ):
        """Two engine evaluations of the same product → the repeat-finding
        pattern surfaces with neutral wording (a repeated finding, never a
        violator label)."""
        from app.models import Package, Product

        rule = db.execute(select(Rule).limit(1)).scalar_one()
        product = Product(
            name=f"Repeat Product {uuid.uuid4().hex[:6]}",
            category="food",
            is_demo=False,
        )
        db.add(product)
        db.flush()

        # Two inspections sharing ONE product row, each with one evaluation +
        # one finding against the same rule (the repeated pattern).
        for index in range(2):
            inspection = Inspection(
                reference_no=f"INS-RP-{uuid.uuid4().hex[:8].upper()}",
                status="ANALYZED",
                product_id=product.id,
                context_date=datetime(2026, 6, 1, tzinfo=UTC),
                is_demo=False,
            )
            db.add(inspection)
            db.flush()
            db.add(Package(inspection_id=inspection.id, label=f"Pkg {index}"))
            evaluation = ComplianceEvaluation(
                inspection_id=inspection.id,
                status="COMPLETED",
                engine_version="test-engine",
                context_date=datetime(2026, 6, 1, tzinfo=UTC),
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                summary={"totalFindings": 1},
                actor_id=_inspector_user(db).id,
            )
            db.add(evaluation)
            db.flush()
            db.add(
                EvaluationFinding(
                    evaluation_id=evaluation.id,
                    requirement_id=rule.id,
                    status="NON_COMPLIANT",
                    severity="MINOR",
                    applicability="YES",
                    detected_value="150 g",
                    expected_value="200 g",
                    explanation="Declared quantity does not match the requirement.",
                    provenance={},
                    detail={},
                )
            )
        db.commit()

        body = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()
        # Whatever the top-8 list shows is real: every entry is a repeated
        # finding across >= 2 inspections, with neutral wording (a repeated
        # INSPECTION finding — the payload carries counts, never a label).
        for entry in body["repeatFindings"]:
            assert entry["inspectionCount"] >= 2
            assert entry["occurrenceCount"] >= entry["inspectionCount"]
            assert entry["productName"]

        # The deterministic pattern itself is verified per-product through the
        # product repository: the same rule flagged in BOTH inspections.
        detail = client.get(
            f"{API}/products/{product.id}", headers=inspector_headers
        )
        assert detail.status_code == 200, detail.text
        history = [
            h for h in detail.json()["findingsHistory"] if h["ruleCode"] == rule.rule_code
        ]
        assert history, "expected the repeated rule in the product's findings history"
        assert history[0]["inspectionCount"] == 2
        assert history[0]["occurrenceCount"] == 2
        assert history[0]["nonCompliantCount"] == 2

    def test_sections_present_and_honestly_flagged(self, client, inspector_headers):
        body = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()
        for section in (
            "kpis",
            "trend",
            "outcomes",
            "complaintPipeline",
            "evidenceQuality",
            "findingCategories",
            "repeatFindings",
            "locations",
            "reports",
        ):
            assert section in body
        assert "dataNote" in body
        assert "generatedAt" in body
        # Either a full location view or the honest empty state — never a
        # fabricated map (§19).
        if not body["locations"]["sufficient"]:
            assert body["locations"]["locations"] == []
            assert body["locations"]["note"]
        # Rates are numbers or null (N/A) — never a fake 0% (§13).
        for key in ("complianceRate", "nonComplianceRate"):
            assert body["kpis"][key] is None or isinstance(body["kpis"][key], float)

    def test_report_analytics_counts_exports_from_audit(
        self, client, inspector_headers
    ):
        body = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["reports"]
        for key in ("generated", "finalized", "amended", "pdfExports", "docxExports"):
            assert isinstance(body[key], int) and body[key] >= 0

    def test_location_intelligence_counts_real_complaints(
        self, client, inspector_headers, db
    ):
        location = f"SearchTest Market {uuid.uuid4().hex[:6]}"
        _make_complaint(db, status="SUBMITTED", location=location)
        body = client.get(
            f"{API}/analytics/operational", headers=inspector_headers
        ).json()["locations"]
        if body["sufficient"]:
            match = [loc for loc in body["locations"] if loc["location"] == location]
            assert match and match[0]["complaintCount"] >= 1
