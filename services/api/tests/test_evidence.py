"""Evidence graph invariants.

The system-wide guarantee: **no finding exists without at least one evidence
row**, and every finding can be traced back through the Evidence Graph to the
visual source and the rule it was based on.
"""
from __future__ import annotations

from tests.conftest import API

_SPINE_NODE_TYPES = {"INSPECTION", "PACKAGE", "FINDING", "EVIDENCE"}


def test_every_finding_has_evidence(client, inspector_headers, make_analyzed_inspection):
    data = make_analyzed_inspection()
    findings = data["findings"]
    assert findings, "analysis should produce at least one finding"

    for finding in findings:
        detail = client.get(f"{API}/findings/{finding['id']}", headers=inspector_headers)
        assert detail.status_code == 200, detail.text
        evidence = detail.json()["evidence"]
        assert len(evidence) >= 1, "invariant: a finding must have >= 1 evidence row"


def test_evidence_graph_shape(client, inspector_headers, make_analyzed_inspection):
    data = make_analyzed_inspection()
    finding = data["findings"][0]

    resp = client.get(f"{API}/findings/{finding['id']}/evidence-graph", headers=inspector_headers)
    assert resp.status_code == 200, resp.text
    graph = resp.json()

    assert graph["findingId"] == finding["id"]
    assert graph["nodes"] and graph["edges"]

    node_types = {n["type"] for n in graph["nodes"]}
    # The core spine must be present so the finding is explainable end-to-end.
    assert _SPINE_NODE_TYPES.issubset(node_types), node_types

    # Edges must reference declared nodes only (well-formed graph).
    node_ids = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids
        assert edge["relation"]


def test_findings_are_marked_demo(client, inspector_headers, make_analyzed_inspection):
    data = make_analyzed_inspection()
    for finding in data["findings"]:
        assert finding["isDemo"] is True
