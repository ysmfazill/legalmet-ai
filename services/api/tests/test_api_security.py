"""PROMPT 9 Phase 10 — API security (default, fast suite).

Guards the authentication/authorisation contract of every mutating endpoint:

* **No anonymous writes.** Every POST/PUT/PATCH/DELETE route (except the
  public ``/auth/login``) must reject an unauthenticated request with 401 —
  before any body validation happens.
* **Read-only stays read-only.** The AUDITOR role may read everything but must
  receive 403 on every write path (the gaps this suite was written for:
  create-inspection / add-image / analyze / create-batch used to accept any
  authenticated role).
* **Bad tokens are rejected** with a structured 401, never a 500.
* **Storage keys cannot escape the storage root** (path traversal, including
  the sibling-directory prefix-collision variant).
"""
from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import API

_DUMMY_ID = "00000000-0000-0000-0000-000000000000"


def _mutating_routes() -> list[tuple[str, str]]:
    """Every mutating (sub)application route, with path params substituted."""
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods & {"POST", "PUT", "PATCH", "DELETE"}
        if not methods:
            continue
        if route.path == "/api/v1/auth/login":  # the one public mutation
            continue
        path = re.sub(r"\{[^}]+\}", _DUMMY_ID, route.path)
        for method in sorted(methods):
            routes.append((method, path))
    return sorted(routes)


class TestNoAnonymousWrites:
    @pytest.mark.parametrize(("method", "path"), _mutating_routes())
    def test_unauthenticated_request_is_rejected(self, client, method, path):
        """No mutating endpoint may act without a valid bearer token."""
        resp = client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"
        assert resp.json()["error"]["code"] in ("UNAUTHORIZED", "AUTHENTICATION_REQUIRED")

    def test_invalid_token_is_rejected_cleanly(self, client):
        resp = client.get(f"{API}/inspections", headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 401
        assert "traceback" not in resp.text.lower()

    def test_mutation_route_inventory_is_nonempty(self):
        """The dynamic scan above must actually cover the API surface."""
        assert len(_mutating_routes()) >= 20


class TestReadOnlyRoleCannotWrite:
    """AUDITOR is a read-only role: every write path must 403."""

    def test_auditor_cannot_create_inspection(self, client, auditor_headers):
        resp = client.post(
            f"{API}/inspections",
            headers=auditor_headers,
            json={"productName": "x", "productCategory": "food"},
        )
        assert resp.status_code == 403, resp.text

    def test_auditor_cannot_register_image(self, client, auditor_headers):
        resp = client.post(
            f"{API}/inspections/{_DUMMY_ID}/images", headers=auditor_headers, json={}
        )
        assert resp.status_code == 403, resp.text

    def test_auditor_cannot_analyze(self, client, auditor_headers):
        resp = client.post(
            f"{API}/inspections/{_DUMMY_ID}/analyze", headers=auditor_headers
        )
        assert resp.status_code == 403, resp.text

    def test_auditor_cannot_create_batch(self, client, auditor_headers):
        resp = client.post(f"{API}/batches", headers=auditor_headers, json={"name": "x"})
        assert resp.status_code == 403, resp.text

    def test_auditor_cannot_perceive(self, client, auditor_headers):
        resp = client.post(
            f"{API}/inspections/{_DUMMY_ID}/perceive", headers=auditor_headers
        )
        assert resp.status_code == 403, resp.text

    def test_auditor_cannot_decide(self, client, auditor_headers):
        resp = client.post(
            f"{API}/inspections/{_DUMMY_ID}/decision", headers=auditor_headers, json={}
        )
        assert resp.status_code == 403, resp.text

    def test_auditor_can_still_read(self, client, auditor_headers):
        """Read access is untouched — the audit trail remains fully visible."""
        resp = client.get(f"{API}/inspections", headers=auditor_headers)
        assert resp.status_code == 200, resp.text


class TestStorageTraversal:
    def test_sibling_directory_prefix_collision_is_blocked(self, tmp_path):
        """A key like ``../<base>-secret`` resolves to a sibling whose path
        STARTS WITH the storage root as a string — the old ``startswith``
        check let it through. ``is_relative_to`` must reject it."""
        from app.core.errors import NotFoundError
        from app.services.storage.local import LocalStorage

        base = tmp_path / "storage"
        storage = LocalStorage(str(base))
        sibling = tmp_path / "storage-secret"
        sibling.mkdir()
        (sibling / "loot.txt").write_bytes(b"loot")

        with pytest.raises(NotFoundError):
            storage.read(key=f"../{base.name}-secret/loot.txt")

    def test_traversal_outside_root_is_blocked(self, tmp_path):
        from app.core.errors import NotFoundError
        from app.services.storage.local import LocalStorage

        storage = LocalStorage(str(tmp_path / "storage"))
        (tmp_path / "outside.txt").write_bytes(b"x")
        with pytest.raises(NotFoundError):
            storage.read(key="../../outside.txt")

    def test_normal_key_roundtrip(self, tmp_path):
        from app.services.storage.local import LocalStorage

        storage = LocalStorage(str(tmp_path / "storage"))
        storage.save(key="inspections/a/b.png", data=b"data")
        assert storage.read(key="inspections/a/b.png") == b"data"


class TestSecurityHeadersAndErrors:
    def test_error_responses_are_structured_not_tracebacks(self, client, inspector_headers):
        """A malformed UUID path yields a structured validation error (auth
        first, then validation) — never a leaked traceback."""
        resp = client.get(f"{API}/inspections/not-a-uuid", headers=inspector_headers)
        assert resp.status_code in (400, 404, 422)
        body = resp.json()
        assert "traceback" not in resp.text.lower()
        assert body  # some structured payload is present
