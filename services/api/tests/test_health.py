"""Liveness + service metadata endpoints."""
from __future__ import annotations

from tests.conftest import API


def test_health_ok(client):
    resp = client.get(f"{API}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root_declares_problem_statement_and_demo_notice(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["problemStatement"] == "SIH26034"
    # The DEMO marker must never be silently dropped.
    assert "DEMO DATA" in body["notice"]
