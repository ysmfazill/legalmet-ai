"""Regulatory intelligence API tests (Prompt 5) — HTTP surface.

Covers the read endpoints (sources / documents / versions / requirements with
filters + provenance), the admin-only audited verification mutation, auth
boundaries, pagination, and the candidate-mapping route's refusal to produce
any compliance verdict.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.enums import CandidateMappingStatus, VerificationStatus
from tests.conftest import API

LM_DOC_CODE = "LM-PC-RULES-2011"


def _lm_document_id(client: TestClient, headers: dict) -> str:
    resp = client.get(f"{API}/regulations/documents", headers=headers)
    assert resp.status_code == 200, resp.text
    docs = [d for d in resp.json() if d["code"] == LM_DOC_CODE]
    assert docs, "seeded LM(PC) document must be present"
    return docs[0]["id"]


# --- sources -----------------------------------------------------------------


class TestSourcesApi:
    def test_list_sources_requires_auth(self, client):
        assert client.get(f"{API}/regulations/sources").status_code == 401

    def test_list_sources_returns_seeded_source(self, client, inspector_headers):
        resp = client.get(f"{API}/regulations/sources", headers=inspector_headers)
        assert resp.status_code == 200
        sources = resp.json()
        assert len(sources) == 1
        source = sources[0]
        assert source["verificationStatus"] == VerificationStatus.UNVERIFIED.value
        assert source["sourceType"] == "GOVERNMENT_DEPARTMENT"
        assert source["canonicalUrl"].startswith("https://")

    def test_filter_by_verification_status(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/sources",
            headers=inspector_headers,
            params={"verificationStatus": "VERIFIED"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_source_by_id(self, client, inspector_headers):
        source_id = client.get(
            f"{API}/regulations/sources", headers=inspector_headers
        ).json()[0]["id"]
        resp = client.get(f"{API}/regulations/sources/{source_id}", headers=inspector_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == source_id

    def test_get_unknown_source_404s(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/sources/00000000-0000-0000-0000-000000000000",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_patch_source_is_admin_only(self, client, inspector_headers):
        source_id = client.get(
            f"{API}/regulations/sources", headers=inspector_headers
        ).json()[0]["id"]
        resp = client.patch(
            f"{API}/regulations/sources/{source_id}",
            headers=inspector_headers,
            json={"verificationStatus": "VERIFIED", "verificationNote": "nope"},
        )
        assert resp.status_code == 403

    def test_patch_to_verified_without_note_is_rejected(
        self, client, admin_headers
    ):
        source_id = client.get(
            f"{API}/regulations/sources", headers=admin_headers
        ).json()[0]["id"]
        resp = client.patch(
            f"{API}/regulations/sources/{source_id}",
            headers=admin_headers,
            json={"verificationStatus": "VERIFIED"},
        )
        assert resp.status_code == 422
        assert "note" in resp.json()["error"]["message"].lower()

    def test_patch_to_verified_with_note_is_audited(self, client, admin_headers):
        source_id = client.get(
            f"{API}/regulations/sources", headers=admin_headers
        ).json()[0]["id"]
        original_note = client.get(
            f"{API}/regulations/sources/{source_id}", headers=admin_headers
        ).json()["verificationNote"]
        note = "Checked against the official DoCA rules PDF on 2026-08-28."
        resp = client.patch(
            f"{API}/regulations/sources/{source_id}",
            headers=admin_headers,
            json={"verificationStatus": "VERIFIED", "verificationNote": note},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["verificationStatus"] == VerificationStatus.VERIFIED.value
        assert body["verificationNote"] == note

        # the audit trail records the before/after transition
        events = client.get(
            f"{API}/audit",
            headers=admin_headers,
            params={"limit": 20},
        )
        assert events.status_code == 200, events.text
        matching = [
            e
            for e in events.json()["items"]
            if e["eventType"] == "REGULATORY_SOURCE_UPDATED" and e["entityId"] == source_id
        ]
        assert matching, "verification change must be audited"
        payload = matching[0].get("payload") or {}
        assert payload["before"]["verificationStatus"] == VerificationStatus.UNVERIFIED.value
        assert payload["after"]["verificationStatus"] == VerificationStatus.VERIFIED.value

        # restore UNVERIFIED so later tests (shared session DB) see the seed state
        restore = client.patch(
            f"{API}/regulations/sources/{source_id}",
            headers=admin_headers,
            json={
                "verificationStatus": VerificationStatus.UNVERIFIED.value,
                "verificationNote": original_note,
            },
        )
        assert restore.status_code == 200, restore.text
        assert restore.json()["verificationStatus"] == VerificationStatus.UNVERIFIED.value

    def test_patch_unknown_status_is_rejected(self, client, admin_headers):
        source_id = client.get(
            f"{API}/regulations/sources", headers=admin_headers
        ).json()[0]["id"]
        resp = client.patch(
            f"{API}/regulations/sources/{source_id}",
            headers=admin_headers,
            json={"verificationStatus": "MAYBE"},
        )
        assert resp.status_code == 422


# --- documents + versions ------------------------------------------------------


class TestDocumentsAndVersionsApi:
    def test_list_documents_with_filters(self, client, inspector_headers):
        all_docs = client.get(
            f"{API}/regulations/documents", headers=inspector_headers
        ).json()
        assert any(d["code"] == LM_DOC_CODE for d in all_docs)

        real = client.get(
            f"{API}/regulations/documents",
            headers=inspector_headers,
            params={"isDemo": "false"},
        ).json()
        assert [d["code"] for d in real] == [LM_DOC_CODE]

        none = client.get(
            f"{API}/regulations/documents",
            headers=inspector_headers,
            params={"documentType": "ACT"},
        ).json()
        assert none == []

    def test_get_document_includes_versions(self, client, inspector_headers):
        doc_id = _lm_document_id(client, inspector_headers)
        resp = client.get(f"{API}/regulations/documents/{doc_id}", headers=inspector_headers)
        assert resp.status_code == 200
        doc = resp.json()
        assert doc["documentIdentifier"].startswith("G.S.R. 202(E)")
        assert len(doc["versions"]) == 3

    def test_list_versions_effective_on(self, client, inspector_headers):
        doc_id = _lm_document_id(client, inspector_headers)
        resp = client.get(
            f"{API}/regulations/versions",
            headers=inspector_headers,
            params={"documentId": doc_id, "effectiveOn": "2016-06-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 1
        assert versions[0]["versionLabel"] == "as amended by G.S.R. 385(E)/2015"

    def test_resolve_version_found(self, client, inspector_headers):
        doc_id = _lm_document_id(client, inspector_headers)
        resp = client.get(
            f"{API}/regulations/versions/resolve",
            headers=inspector_headers,
            params={"documentId": doc_id, "on": "2020-06-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "FOUND"
        assert body["version"]["versionLabel"].startswith("as amended through G.S.R. 629(E)")

    def test_resolve_version_no_applicable_version(self, client, inspector_headers):
        doc_id = _lm_document_id(client, inspector_headers)
        resp = client.get(
            f"{API}/regulations/versions/resolve",
            headers=inspector_headers,
            params={"documentId": doc_id, "on": "1999-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "NO_APPLICABLE_VERSION"
        assert body["version"] is None

    def test_resolve_version_requires_params(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/versions/resolve", headers=inspector_headers
        )
        assert resp.status_code == 422


# --- requirements --------------------------------------------------------------


class TestRequirementsApi:
    def test_list_requirements_paginated_with_filters(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/requirements",
            headers=inspector_headers,
            params={"isDemo": "false", "page": 1, "pageSize": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 22
        assert len(body["items"]) == 5
        assert body["page"] == 1
        for item in body["items"]:
            assert item["isDemo"] is False
            assert item["sourceReference"]

    def test_filter_by_field_key(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/requirements",
            headers=inspector_headers,
            params={"fieldKey": "COUNTRY_OF_ORIGIN"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["ruleCode"] for i in items] == ["LM-PC-2011-6.1(aa)"]
        assert items[0]["applicabilityDefinition"] != {}

    def test_filter_by_effective_date_excludes_future_requirements(
        self, client, inspector_headers
    ):
        # In 2012, country-of-origin / best-before / consumer-care did not exist.
        resp = client.get(
            f"{API}/regulations/requirements",
            headers=inspector_headers,
            params={"effectiveOn": "2012-06-01T00:00:00Z", "isDemo": "false"},
        )
        assert resp.status_code == 200
        codes = {i["ruleCode"] for i in resp.json()["items"]}
        assert "LM-PC-2011-6.1(aa)" not in codes
        assert "LM-PC-2011-6.1(da)" not in codes
        assert "LM-PC-2011-6.2" not in codes
        assert "LM-PC-2011-6.1(a)" in codes

    def test_get_requirement_returns_full_provenance(self, client, inspector_headers):
        listing = client.get(
            f"{API}/regulations/requirements",
            headers=inspector_headers,
            params={"fieldKey": "COUNTRY_OF_ORIGIN"},
        ).json()
        req_id = listing["items"][0]["id"]
        resp = client.get(
            f"{API}/regulations/requirements/{req_id}", headers=inspector_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        prov = body["provenance"]
        assert prov["authority"] == (
            "Department of Consumer Affairs, Ministry of Consumer Affairs, "
            "Food and Public Distribution, Government of India"
        )
        assert prov["documentTitle"].startswith("Legal Metrology")
        assert prov["documentIdentifier"].startswith("G.S.R. 202(E)")
        assert prov["versionLabel"].startswith("as amended through G.S.R. 629(E)")
        assert prov["effectiveFrom"].startswith("2017-06-23")
        assert prov["requirementReference"] == "LM-PC-2011-6.1(aa)"
        assert prov["sourceVerificationStatus"] == VerificationStatus.UNVERIFIED.value
        assert prov["sourceName"]
        assert body["version"]["id"] == body["versionId"]

    def test_get_unknown_requirement_404s(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/requirements/00000000-0000-0000-0000-000000000000",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_current_filter(self, client, inspector_headers):
        resp = client.get(
            f"{API}/regulations/requirements",
            headers=inspector_headers,
            params={"current": "true", "isDemo": "false"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 9

    def test_requirements_require_auth(self, client):
        assert (
            client.get(f"{API}/regulations/requirements").status_code == 401
        )


# --- candidate mapping route ----------------------------------------------------


class TestCandidatesApiGuards:
    def test_candidate_route_requires_auth(self, client):
        resp = client.get(
            f"{API}/inspections/00000000-0000-0000-0000-000000000000/regulatory-candidates"
        )
        assert resp.status_code == 401

    def test_candidate_route_404_for_unknown_inspection(self, client, inspector_headers):
        resp = client.get(
            f"{API}/inspections/00000000-0000-0000-0000-000000000000/regulatory-candidates",
            headers=inspector_headers,
        )
        assert resp.status_code == 404


# --- no-compliance-verdict + Prompt 1 regression --------------------------------


class TestScopeGuardrails:
    def test_candidate_payload_has_no_verdict_fields(
        self, client, inspector_headers, perceived_inspection_for_regulatory
    ):
        resp = client.get(
            f"{API}/inspections/{perceived_inspection_for_regulatory}/regulatory-candidates",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["regulatoryEvaluation"] == "AWAITING_REGULATORY_EVALUATION"
        forbidden = {"compliant", "nonCompliant", "compliance", "verdict", "score"}
        for field in body["fields"]:
            assert field["evaluationStatus"] == (
                CandidateMappingStatus.AWAITING_COMPLIANCE_ENGINE.value
            )
            assert not (forbidden & set(field.keys()))

    def test_demo_rule_flow_still_works(self, client, inspector_headers, analyzed_inspection):
        """Prompt 1 demo compliance flow is unaffected by the regulatory layer."""
        assert analyzed_inspection["findings"], "demo findings must still be produced"
        detail = analyzed_inspection["detail"]
        assert detail["id"] == analyzed_inspection["id"]


@pytest.fixture()
def perceived_inspection_for_regulatory(
    client, inspector_headers, services, monkeypatch
):
    """Inspection with a completed perception run (deterministic fakes)."""
    from tests.test_perception_pipeline import FakeOCRService, FakeVisionService, _label_png

    pipeline = services.perception._pipeline
    monkeypatch.setattr(pipeline, "_ocr", FakeOCRService())
    monkeypatch.setattr(pipeline, "_vision", FakeVisionService())

    resp = client.post(
        f"{API}/inspections",
        headers=inspector_headers,
        json={"productName": "API Guard Sample", "productCategory": "food"},
    )
    assert resp.status_code == 201, resp.text
    inspection_id = resp.json()["id"]

    img = client.post(
        f"{API}/inspections/{inspection_id}/images/upload",
        headers=inspector_headers,
        files={"file": ("front.png", _label_png(), "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
    )
    assert img.status_code == 201, img.text

    kick = client.post(
        f"{API}/inspections/{inspection_id}/perceive", headers=inspector_headers
    )
    assert kick.status_code == 202, kick.text
    return inspection_id
