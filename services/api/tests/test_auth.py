"""Authentication + authorization behaviour."""
from __future__ import annotations

from tests.conftest import API, DEMO_INSPECTOR_PASSWORD


def test_login_returns_token_and_user(client):
    resp = client.post(
        f"{API}/auth/login",
        json={"email": "inspector@legalmet.local", "password": DEMO_INSPECTOR_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accessToken"]
    assert body["tokenType"] == "bearer"
    assert body["user"]["role"] == "INSPECTOR"


def test_login_rejects_bad_password(client):
    resp = client.post(
        f"{API}/auth/login",
        json={"email": "inspector@legalmet.local", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    # Structured error envelope.
    assert "error" in resp.json()
    assert resp.json()["error"]["code"]


def test_me_requires_authentication(client):
    resp = client.get(f"{API}/auth/me")
    assert resp.status_code == 401
    assert "error" in resp.json()


def test_me_returns_current_user(client, inspector_headers):
    resp = client.get(f"{API}/auth/me", headers=inspector_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "inspector@legalmet.local"


def test_admin_login_has_admin_role(client, admin_headers):
    resp = client.get(f"{API}/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "ADMIN"
