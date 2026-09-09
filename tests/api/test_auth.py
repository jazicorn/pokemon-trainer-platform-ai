"""Tests for API key authentication — api.auth (ROADMAP.md Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import config as config_module
from api.auth import require_api_key
from api.tenants import TenantContext, create_tenant


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
def client() -> TestClient:
    """A minimal, isolated FastAPI app exercising require_api_key.

    Deliberately NOT api.app's real `app`/`protected_router` singletons —
    mounting a test-only route on those would leak a stray route into the
    real app object for the rest of the process. This app exists only for
    these tests.
    """
    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(  # pyright: ignore[reportUnusedFunction] — registered via decorator
        tenant: TenantContext = Depends(require_api_key),
    ) -> dict[str, str]:
        return {"tenant_id": tenant.tenant_id, "platform_db_url": tenant.platform_db_url}

    return TestClient(test_app)


class TestRequireApiKey:
    def test_missing_key_is_401(self, client: TestClient) -> None:
        assert client.get("/protected").status_code == 401

    def test_wrong_key_is_403(self, client: TestClient) -> None:
        response = client.get("/protected", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

    def test_correct_key_resolves_the_right_tenant(
        self, client: TestClient, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")

        response = client.get("/protected", headers={"X-API-Key": raw_key})

        assert response.status_code == 200
        assert response.json() == {"tenant_id": tenant_id, "platform_db_url": "postgresql://u:p@h/db"}

    def test_deactivated_tenant_key_is_403(
        self, client: TestClient, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        import sqlite3

        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        conn = sqlite3.connect(isolated_tenants_db)
        conn.execute("UPDATE tenants SET is_active = 0 WHERE id = ?", (tenant_id,))
        conn.commit()
        conn.close()

        response = client.get("/protected", headers={"X-API-Key": raw_key})
        assert response.status_code == 403


class TestAppWiring:
    """Confirm api.app's actual wiring — not auth.py's logic in isolation,
    but that app.py correctly applies it. Only introspects/reads the real
    app; never mutates it, so this can't leak state into other tests.
    """

    def test_protected_router_requires_api_key(self) -> None:
        from api.app import protected_router

        assert any(dep.dependency is require_api_key for dep in protected_router.dependencies)

    def test_health_is_unauthenticated(self) -> None:
        from api.app import app

        response = TestClient(app).get("/health")
        assert response.status_code == 200
