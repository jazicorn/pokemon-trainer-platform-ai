"""Tests for the local admin web UI (ROADMAP.md Phase 16)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import config as config_module
from admin.app import app
from admin.sessions import SESSION_COOKIE_NAME, get_csrf_token
from api.tenants import create_tenant, get_tenant_by_id, get_tenant_by_key_hash, hash_api_key, list_tenants

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture
def isolated_tenants_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "test_tenants.db"
    monkeypatch.setattr("api.tenants.get_db_path", lambda: db_file)
    return db_file


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(config_module.config, "tenant_db_encryption_key", key)
    return key


@pytest.fixture
def admin_token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(config_module.config, "admin_token", ADMIN_TOKEN)
    return ADMIN_TOKEN


@pytest.fixture
def client(isolated_tenants_db: Path, encryption_key: str, admin_token: str) -> TestClient:
    # base_url must be https:// — the session cookie is Secure, and httpx's
    # cookie jar (correctly) won't send a Secure cookie back over a plain
    # http:// test base_url, which would silently break every test below
    # that relies on the client staying logged in across requests.
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def logged_in_client(client: TestClient) -> TestClient:
    response = client.post("/login", data={"token": ADMIN_TOKEN}, follow_redirects=False)
    assert response.status_code == 303
    return client


def _csrf_token_for(client: TestClient) -> str:
    """Pull the CSRF token straight from the session store, keyed by the
    client's own session cookie — avoids fragile HTML-scraping in tests.
    """
    session_id = client.cookies.get(SESSION_COOKIE_NAME)
    token = get_csrf_token(session_id)
    assert token is not None
    return token


class TestLogin:
    def test_login_form_renders(self, client: TestClient) -> None:
        assert client.get("/login").status_code == 200

    def test_wrong_token_is_401_and_sets_no_session(self, client: TestClient) -> None:
        response = client.post("/login", data={"token": "wrong"}, follow_redirects=False)
        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in client.cookies

    def test_correct_token_redirects_and_sets_a_flagged_session_cookie(self, client: TestClient) -> None:
        response = client.post("/login", data={"token": ADMIN_TOKEN}, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        set_cookie = response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie
        assert "SameSite=strict" in set_cookie.lower() or "samesite=strict" in set_cookie.lower()

    def test_admin_token_not_configured_fails_loudly_not_a_silent_pass(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TestClient re-raises unhandled server exceptions by default (the
        same RuntimeError api.tenants._get_fernet() raises for a missing
        TENANT_DB_ENCRYPTION_KEY) rather than converting them to a 500
        response — this confirms it's a real raised error, not silently
        treated as "no token required".
        """
        monkeypatch.setattr(config_module.config, "admin_token", None)
        with pytest.raises(RuntimeError, match="ADMIN_TOKEN"):
            client.post("/login", data={"token": "anything"})


class TestSessionGating:
    def test_root_without_session_redirects_to_login(self, client: TestClient) -> None:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_root_with_session_is_200(self, logged_in_client: TestClient) -> None:
        assert logged_in_client.get("/").status_code == 200

    def test_logout_clears_the_session(self, logged_in_client: TestClient) -> None:
        assert logged_in_client.get("/").status_code == 200

        logout_response = logged_in_client.post("/logout", follow_redirects=False)
        assert logout_response.status_code == 303
        assert logout_response.headers["location"] == "/login"

        assert logged_in_client.get("/", follow_redirects=False).status_code == 303


class TestTenantsNew:
    def test_without_csrf_token_is_403(self, logged_in_client: TestClient) -> None:
        response = logged_in_client.post(
            "/tenants/new", data={"name": "acme", "platform_db_url": "postgresql://u:p@h/db"}
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_with_wrong_csrf_token_is_403(self, logged_in_client: TestClient) -> None:
        response = logged_in_client.post(
            "/tenants/new",
            data={"name": "acme", "platform_db_url": "postgresql://u:p@h/db", "csrf_token": "wrong"},
        )
        assert response.status_code == 403

    def test_success_creates_a_real_tenant_and_shows_the_key_once(self, logged_in_client: TestClient) -> None:
        csrf_token = _csrf_token_for(logged_in_client)

        response = logged_in_client.post(
            "/tenants/new",
            data={"name": "acme", "platform_db_url": "postgresql://u:p@h/db", "csrf_token": csrf_token},
        )

        assert response.status_code == 200
        assert "acme" in response.text

        tenants = [t for t in list_tenants() if t.name == "acme"]
        assert len(tenants) == 1

    def test_without_a_session_is_a_redirect_not_a_csrf_error(self, client: TestClient) -> None:
        """Missing session takes priority in the redirect dependency's own
        scope, but _require_valid_csrf runs on this route too and correctly
        403s a sessionless POST — either is an acceptable rejection, but it
        must not be a 200 or 500.
        """
        response = client.post(
            "/tenants/new",
            data={"name": "acme", "platform_db_url": "postgresql://u:p@h/db"},
            follow_redirects=False,
        )
        assert response.status_code in (303, 403)


class TestTenantDetail:
    def test_unknown_tenant_is_404(self, logged_in_client: TestClient) -> None:
        assert logged_in_client.get("/tenants/does-not-exist").status_code == 404

    def test_shows_masked_url_not_credentials(self, logged_in_client: TestClient) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://secretuser:secretpass@dbhost/mydb")

        response = logged_in_client.get(f"/tenants/{tenant_id}")

        assert response.status_code == 200
        assert "dbhost" in response.text
        assert "mydb" in response.text
        assert "secretuser" not in response.text
        assert "secretpass" not in response.text


class TestTenantReveal:
    def test_wrong_admin_token_does_not_reveal(self, logged_in_client: TestClient) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://secretuser:secretpass@dbhost/mydb")
        csrf_token = _csrf_token_for(logged_in_client)

        response = logged_in_client.post(
            f"/tenants/{tenant_id}/reveal",
            data={"admin_token": "wrong", "csrf_token": csrf_token},
        )

        assert response.status_code == 200
        assert "secretpass" not in response.text

    def test_correct_admin_token_reveals_the_full_dsn(self, logged_in_client: TestClient) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://secretuser:secretpass@dbhost/mydb")
        csrf_token = _csrf_token_for(logged_in_client)

        response = logged_in_client.post(
            f"/tenants/{tenant_id}/reveal",
            data={"admin_token": ADMIN_TOKEN, "csrf_token": csrf_token},
        )

        assert response.status_code == 200
        assert "secretuser:secretpass@dbhost" in response.text

    def test_without_csrf_token_is_403(self, logged_in_client: TestClient) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")
        response = logged_in_client.post(f"/tenants/{tenant_id}/reveal", data={"admin_token": ADMIN_TOKEN})
        assert response.status_code == 403


class TestTenantDeactivate:
    def test_without_csrf_token_is_403(self, logged_in_client: TestClient) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")
        response = logged_in_client.post(f"/tenants/{tenant_id}/deactivate")
        assert response.status_code == 403

    def test_success_deactivates_and_redirects(self, logged_in_client: TestClient) -> None:
        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        csrf_token = _csrf_token_for(logged_in_client)

        response = logged_in_client.post(
            f"/tenants/{tenant_id}/deactivate", data={"csrf_token": csrf_token}, follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers["location"] == f"/tenants/{tenant_id}"
        tenant = get_tenant_by_id(tenant_id)
        assert tenant is not None
        assert tenant.is_active is False
        assert get_tenant_by_key_hash(hash_api_key(raw_key)) is None

    def test_unknown_tenant_is_404(self, logged_in_client: TestClient) -> None:
        csrf_token = _csrf_token_for(logged_in_client)
        response = logged_in_client.post("/tenants/does-not-exist/deactivate", data={"csrf_token": csrf_token})
        assert response.status_code == 404


class TestTenantRotateKey:
    def test_without_csrf_token_is_403(self, logged_in_client: TestClient) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")
        response = logged_in_client.post(f"/tenants/{tenant_id}/rotate-key")
        assert response.status_code == 403

    def test_success_shows_new_key_and_invalidates_the_old_one(self, logged_in_client: TestClient) -> None:
        tenant_id, old_key = create_tenant("acme", "postgresql://u:p@h/db")
        csrf_token = _csrf_token_for(logged_in_client)

        response = logged_in_client.post(f"/tenants/{tenant_id}/rotate-key", data={"csrf_token": csrf_token})

        assert response.status_code == 200
        assert get_tenant_by_key_hash(hash_api_key(old_key)) is None

    def test_unknown_tenant_is_404(self, logged_in_client: TestClient) -> None:
        csrf_token = _csrf_token_for(logged_in_client)
        response = logged_in_client.post("/tenants/does-not-exist/rotate-key", data={"csrf_token": csrf_token})
        assert response.status_code == 404
