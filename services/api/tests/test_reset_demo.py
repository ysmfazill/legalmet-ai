"""Regression tests for the SAFE DEMO RESET (scripts/reset_demo.py).

Covers the guarantees the reset must keep:

* transactional activity (inspections, findings, evidence, images, files) is
  wiped;
* configuration (users, regulatory data, rules, compliance rules) survives;
* running the reset repeatedly is idempotent — no duplicate demo inspections;
* the post-reset guard refuses to bless a database with empty config tables.

Isolation: every test runs against its OWN in-memory engine + storage dir (the
reset is destructive, so the shared session-scoped database must never be
touched). The seed step normally runs the REAL OCR pipeline; here the
perception backend is the deterministic mock, so the reset runs in
milliseconds without touching PaddleOCR.
"""
from __future__ import annotations

import tempfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  — registers all tables on Base.metadata
import app.db.demo_inspections_seed as demo_seed_module
from app.api.deps import get_services_dep, get_settings_dep
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import get_db
from app.main import create_app
from app.services.registry import build_services
from scripts.reset_demo import (
    _verify_preserved,
    _wipe_transactional,
    reset_demo_data,
)

# Same demo credentials conftest seeds (test-only values, not real secrets).
INSPECTOR_EMAIL = "inspector@legalmet.local"
INSPECTOR_PASSWORD = "test-inspector-pass"


@pytest.fixture()
def stack(test_settings) -> SimpleNamespace:
    """A private engine + storage dir + API client, seeded like a real boot."""
    storage_dir = tempfile.mkdtemp(prefix="legalmet-reset-test-")
    settings = test_settings.model_copy(update={"storage_dir": storage_dir})

    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False,
        class_=Session,
    )

    db = factory()
    try:
        seed_demo_data(db, settings)  # login accounts (config — must survive)
        from app.db.regulatory_seed import seed_regulatory_data

        seed_regulatory_data(db)
        from app.services.compliance.seed_rules import seed_compliance_rules

        seed_compliance_rules(db)
    finally:
        db.close()

    services = build_services(settings, session_factory=factory)
    application = create_app(settings)

    def _override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_services_dep] = lambda: services

    yield SimpleNamespace(
        engine=engine,
        factory=factory,
        settings=settings,
        client=TestClient(application),
    )
    engine.dispose()


def _count(factory, table: str) -> int:
    db = factory()
    try:
        return db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
    finally:
        db.close()


def _login(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login", json={"email": INSPECTOR_EMAIL, "password": INSPECTOR_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['accessToken']}"}


def test_wipe_removes_activity_but_preserves_config(stack):
    # One analyzed inspection = inspections + images + runs + fields +
    # findings + audit rows.
    headers = _login(stack.client)
    create = stack.client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"productName": "stale dev activity", "productCategory": "food"},
    )
    assert create.status_code == 201, create.text
    image = stack.client.post(
        f"/api/v1/inspections/{create.json()['id']}/images",
        headers=headers,
        json={
            "originalFilename": "front.png",
            "mimeType": "image/png",
            "imageType": "FRONT",
            "contentBase64": (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
                "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            ),
            "width": 1200,
            "height": 1600,
            "fileSize": 2048,
        },
    )
    assert image.status_code == 201, image.text
    analyze = stack.client.post(
        f"/api/v1/inspections/{create.json()['id']}/analyze",
        headers=headers,
        json={"contextDate": "2026-06-01"},
    )
    assert analyze.status_code == 200, analyze.text

    before = {t: _count(stack.factory, t) for t in ("users", "rules", "compliance_rules")}
    assert before["users"] >= 1 and before["rules"] >= 1 and before["compliance_rules"] >= 1

    db = stack.factory()
    try:
        removed = _wipe_transactional(db)
    finally:
        db.close()

    assert _count(stack.factory, "inspections") == 0
    assert _count(stack.factory, "images") == 0
    assert _count(stack.factory, "audit_events") == 0
    # Configuration survives untouched.
    after = {t: _count(stack.factory, t) for t in ("users", "rules", "compliance_rules")}
    assert after == before
    # Findings exist in the engine table or the legacy table depending on the
    # analyze path — either way the reset must have removed them.
    assert (
        removed.get("evaluation_findings", 0) + removed.get("compliance_findings", 0) >= 1
    )
    assert removed["inspections"] == 1


def test_reset_is_idempotent_and_seeds_exactly_one_demo_inspection(
    stack, monkeypatch
):
    # The seed step resolves services from the global registry (real settings,
    # real OCR). Point it at THIS stack's services (mock perception, this
    # engine) so the seed lands in the isolated database.
    services = build_services(stack.settings, session_factory=stack.factory)
    monkeypatch.setattr(demo_seed_module, "get_services", lambda: services)

    reset_demo_data(session_factory=stack.factory, settings=stack.settings)
    refs = _refs(stack.factory)
    assert refs == ["DEMO-FOOD"]  # the configured default subset, no more

    # Second run: idempotent — the seed must skip, not duplicate.
    reset_demo_data(session_factory=stack.factory, settings=stack.settings)
    assert _refs(stack.factory) == ["DEMO-FOOD"]

    # The seeded demo inspection carries a full evidence chain.
    assert _count(stack.factory, "extracted_fields") >= 1
    assert _count(stack.factory, "evaluation_findings") >= 1
    assert _count(stack.factory, "images") == 1

    _verify_preserved(session_factory=stack.factory)


def _refs(factory) -> list[str]:
    db = factory()
    try:
        return [
            r[0]
            for r in db.execute(text("SELECT reference_no FROM inspections")).fetchall()
        ]
    finally:
        db.close()


def test_reset_clears_stored_files(stack, monkeypatch):
    services = build_services(stack.settings, session_factory=stack.factory)
    monkeypatch.setattr(demo_seed_module, "get_services", lambda: services)

    from pathlib import Path

    junk = Path(stack.settings.storage_dir) / "stale-activity" / "img.png"
    junk.parent.mkdir(parents=True, exist_ok=True)
    junk.write_bytes(b"stale")

    reset_demo_data(session_factory=stack.factory, settings=stack.settings)

    assert not junk.exists()  # old transactional files are gone
    # The re-seed wrote its own image files under the same root.
    assert any(Path(stack.settings.storage_dir).rglob("*.png"))


def test_verify_preserved_rejects_empty_config(stack):
    # Guard fires when a preserved config table is emptied — the reset must
    # never be able to bless a database with no login accounts.
    db = stack.factory()
    try:
        db.execute(text("DELETE FROM users"))
        db.commit()
    finally:
        db.close()
    with pytest.raises(RuntimeError, match="users"):
        _verify_preserved(session_factory=stack.factory)
