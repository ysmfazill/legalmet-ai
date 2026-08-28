"""Shared test fixtures for the LEGALMET AI API.

Isolation strategy
------------------
* **In-memory SQLite** via a ``StaticPool`` so a single connection (and therefore
  a single in-memory database) is shared across the app and the test session.
* **One coherent ``Settings``** injected everywhere through FastAPI dependency
  overrides (``get_db``, ``get_settings_dep``, ``get_services_dep``). Because JWT
  signing and decoding both resolve settings through ``get_settings_dep``, using
  one object keeps auth self-consistent regardless of the developer's real env.
* The ``TestClient`` is created **without** its context manager, so the app's
  lifespan (which would ``create_all`` + seed on the *module* engine and write a
  ``legalmet.db`` file) never runs. We create the schema and seed the demo data
  ourselves against the in-memory engine instead.
"""
from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  — registers all tables on Base.metadata
from app.api.deps import get_services_dep, get_settings_dep
from app.core.config import Settings
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import get_db
from app.main import create_app
from app.services.registry import Services, build_services

# All v1 routes live under this prefix.
API = "/api/v1"

# Known demo passwords for the test database only (NOT real secrets).
ADMIN_PASSWORD = "test-admin-pass"
INSPECTOR_PASSWORD = "test-inspector-pass"
ADMIN_EMAIL = "admin@legalmet.local"
INSPECTOR_EMAIL = "inspector@legalmet.local"
SUPERVISOR_EMAIL = "supervisor@legalmet.local"  # seeded with INSPECTOR_PASSWORD
AUDITOR_EMAIL = "auditor@legalmet.local"  # seeded with INSPECTOR_PASSWORD

# Convenience aliases used across the test modules.
DEMO_ADMIN_PASSWORD = ADMIN_PASSWORD
DEMO_INSPECTOR_PASSWORD = INSPECTOR_PASSWORD


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    storage_dir = tempfile.mkdtemp(prefix="legalmet-test-storage-")
    return Settings(
        environment="test",
        debug=True,
        database_url="sqlite://",  # in-memory
        secret_key="test-only-secret-key-not-for-production-use",  # >=32 bytes (PyJWT/RFC 7518)
        seed_demo_data=False,  # we seed explicitly below
        storage_dir=storage_dir,
        demo_admin_email=ADMIN_EMAIL,
        demo_admin_password=ADMIN_PASSWORD,
        demo_inspector_email=INSPECTOR_EMAIL,
        demo_inspector_password=INSPECTOR_PASSWORD,
        log_level="WARNING",
        # Never download / initialise real OCR models from the unit-test suite.
        # The real PaddleOCR integration test opts in explicitly via its own
        # settings (tests/integration/).
        perception_ocr_backend="mock",
    )


@pytest.fixture(scope="session")
def db_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest.fixture(scope="session")
def session_factory(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session
    )


@pytest.fixture(scope="session")
def services(test_settings: Settings, session_factory: sessionmaker[Session]) -> Services:
    # The session factory is injected so the perception pipeline's background
    # execution hits the SAME in-memory engine the API overrides use.
    return build_services(test_settings, session_factory=session_factory)


@pytest.fixture(scope="session", autouse=True)
def _schema_and_seed(
    db_engine: Engine, session_factory: sessionmaker[Session], test_settings: Settings
) -> None:
    Base.metadata.create_all(db_engine)
    db = session_factory()
    try:
        seed_demo_data(db, test_settings)
        # Prompt 5: research-grade regulatory seed (idempotent, UNVERIFIED).
        # Mirrors the production lifespan so the regulatory API tests run
        # against exactly what a started server would expose.
        from app.db.regulatory_seed import seed_regulatory_data

        seed_regulatory_data(db)
    finally:
        db.close()


@pytest.fixture()
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(
    test_settings: Settings, session_factory: sessionmaker[Session], services: Services
) -> Iterator[TestClient]:
    application = create_app(test_settings)

    def _override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_settings_dep] = lambda: test_settings
    application.dependency_overrides[get_services_dep] = lambda: services

    # No context manager: lifespan (module-engine create_all + seed) must not run.
    yield TestClient(application)
    application.dependency_overrides.clear()


# --- Auth helpers ----------------------------------------------------------


def _login(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["accessToken"]


@pytest.fixture()
def inspector_credentials() -> dict[str, str]:
    return {"email": INSPECTOR_EMAIL, "password": INSPECTOR_PASSWORD}


@pytest.fixture()
def admin_credentials() -> dict[str, str]:
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}


@pytest.fixture()
def inspector_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, INSPECTOR_EMAIL, INSPECTOR_PASSWORD)}"}


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, ADMIN_EMAIL, ADMIN_PASSWORD)}"}


@pytest.fixture()
def auditor_headers(client: TestClient) -> dict[str, str]:
    # Auditor is seeded with the inspector demo password.
    return {"Authorization": f"Bearer {_login(client, AUDITOR_EMAIL, INSPECTOR_PASSWORD)}"}


# --- End-to-end flow helper ------------------------------------------------

# A valid 1x1 PNG. Its pixels are irrelevant — the foundation-phase perception
# layer is a deterministic mock — but it must base64-decode to real image bytes.
TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
    "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
TINY_PNG_B64 = TINY_PNG_BASE64  # alias used by some test modules


@pytest.fixture()
def make_analyzed_inspection(
    client: TestClient, inspector_headers: dict[str, str]
) -> Callable[..., dict]:
    """Factory: create an inspection, attach an image, and run analysis end to end.

    Returns a callable so one test can build several analyzed inspections. Each
    call returns ``{"id", "detail", "findings"}`` where ``detail`` is the
    analyzed inspection payload and ``findings`` is the *list* of finding DTOs.
    A recent context date is used so the version-aware regulatory service
    resolves the current (v2) DEMO rule set.
    """

    def _make(
        product_name: str = "DEMO Biscuits 500g",
        category: str = "food",
        context_date: str = "2026-06-01",
    ) -> dict:
        create = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": product_name, "productCategory": category},
        )
        assert create.status_code == 201, create.text
        inspection_id = create.json()["id"]

        # Large dimensions so the mock quality analyzer does not flag low-resolution.
        image = client.post(
            f"{API}/inspections/{inspection_id}/images",
            headers=inspector_headers,
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
            headers=inspector_headers,
            json={"contextDate": context_date},
        )
        assert analyze.status_code == 200, analyze.text

        findings = client.get(
            f"{API}/inspections/{inspection_id}/findings", headers=inspector_headers
        )
        assert findings.status_code == 200, findings.text

        # NOTE: GET /inspections/{id}/findings returns a BARE JSON LIST
        # (response_model=list[FindingOut]), not a paginated {items:[...]} object.
        return {
            "id": inspection_id,
            "detail": analyze.json(),
            "findings": findings.json(),
        }

    return _make


@pytest.fixture()
def analyzed_inspection(make_analyzed_inspection: Callable[..., dict]) -> dict:
    """One-shot convenience wrapper over :func:`make_analyzed_inspection`."""
    return make_analyzed_inspection()
