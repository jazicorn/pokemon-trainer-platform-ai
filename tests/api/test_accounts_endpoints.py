"""Tests for self-serve tenant account endpoints — POST /v1/accounts/register,
POST /v1/accounts/rotate-key, DELETE /v1/accounts (ROADMAP.md Phase 15).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import config as config_module
from api.app import app
from api.paths import ACCOUNTS, ACCOUNTS_REGISTER, ACCOUNTS_ROTATE_KEY
from api.registration import PlatformDBValidationError
from api.tenants import create_tenant, get_tenant_by_key_hash, hash_api_key


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
def client(isolated_tenants_db: Path, encryption_key: str) -> TestClient:
    return TestClient(app)


class TestAccountsRegister:
    def test_success_creates_a_real_tenant_and_returns_a_key(self, client: TestClient) -> None:
        with patch("api.app.validate_platform_db_url") as mock_validate:
            response = client.post(
                ACCOUNTS_REGISTER,
                json={"name": "acme", "platform_db_url": "postgresql://u:p@h/db"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"]
        assert body["api_key"]
        mock_validate.assert_called_once_with("postgresql://u:p@h/db")

        # The returned key actually resolves to the tenant just created —
        # the same lookup require_api_key uses on every protected route.
        resolved = get_tenant_by_key_hash(hash_api_key(body["api_key"]))
        assert resolved is not None
        assert resolved.tenant_id == body["tenant_id"]

    def test_invalid_platform_db_url_is_rejected_before_storing(self, client: TestClient) -> None:
        with patch(
            "api.app.validate_platform_db_url",
            side_effect=PlatformDBValidationError("platform_db_url is missing required table(s): trade_offers"),
        ):
            response = client.post(
                ACCOUNTS_REGISTER,
                json={"name": "bad-tenant", "platform_db_url": "postgresql://u:p@h/empty_db"},
            )

        assert response.status_code == 422
        assert "trade_offers" in response.json()["detail"]

    def test_unreachable_platform_db_url_is_rejected(self, client: TestClient) -> None:
        with patch(
            "api.app.validate_platform_db_url",
            side_effect=PlatformDBValidationError("Could not connect to platform_db_url: connection refused"),
        ):
            response = client.post(
                ACCOUNTS_REGISTER,
                json={"name": "bad-tenant", "platform_db_url": "postgresql://u:p@h/nowhere"},
            )

        assert response.status_code == 422

    def test_missing_platform_db_dependency_is_a_503_not_a_500(self, client: TestClient) -> None:
        with patch(
            "api.app.validate_platform_db_url",
            side_effect=RuntimeError("platform_db_url validation requires the 'platform-db' dependency group"),
        ):
            response = client.post(
                ACCOUNTS_REGISTER,
                json={"name": "acme", "platform_db_url": "postgresql://u:p@h/db"},
            )

        assert response.status_code == 503

    def test_missing_required_field_is_422(self, client: TestClient) -> None:
        response = client.post(ACCOUNTS_REGISTER, json={"name": "acme"})
        assert response.status_code == 422


class TestAccountsRotateKey:
    def test_success_old_key_stops_working_new_key_works(self, client: TestClient) -> None:
        _, old_key = create_tenant("acme", "postgresql://u:p@h/db")

        response = client.post(ACCOUNTS_ROTATE_KEY, headers={"X-API-Key": old_key})

        assert response.status_code == 200
        new_key = response.json()["api_key"]
        assert new_key != old_key

        assert get_tenant_by_key_hash(hash_api_key(old_key)) is None
        assert get_tenant_by_key_hash(hash_api_key(new_key)) is not None

        # End-to-end confirmation via a real protected route (rotate-key
        # itself, no agent/LLM code involved): the old key is now rejected.
        assert client.post(ACCOUNTS_ROTATE_KEY, headers={"X-API-Key": old_key}).status_code == 403

    def test_without_key_is_401(self, client: TestClient) -> None:
        assert client.post(ACCOUNTS_ROTATE_KEY).status_code == 401


class TestAccountsDelete:
    def test_success_deactivates_the_caller_s_own_tenant(self, client: TestClient) -> None:
        _, raw_key = create_tenant("acme", "postgresql://u:p@h/db")

        response = client.delete(ACCOUNTS, headers={"X-API-Key": raw_key})

        assert response.status_code == 200
        assert get_tenant_by_key_hash(hash_api_key(raw_key)) is None
        # End-to-end: the same now-deactivated key is rejected on a second call.
        assert client.delete(ACCOUNTS, headers={"X-API-Key": raw_key}).status_code == 403

    def test_without_key_is_401(self, client: TestClient) -> None:
        assert client.delete(ACCOUNTS).status_code == 401
