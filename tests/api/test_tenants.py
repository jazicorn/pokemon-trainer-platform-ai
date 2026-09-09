"""Tests for the tenant account store — api.tenants (ROADMAP.md Phase 3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import config as config_module
from api.tenants import create_tenant, get_tenant_by_key_hash, hash_api_key


@pytest.fixture
def isolated_tenants_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect tenants.db to a fresh temp file — never touches the real one.

    Mirrors the isolated_db pattern used for memory.db (see
    docs/REFERENCE/TESTING.md's "Memory Persistence Tests" section).
    """
    db_file = tmp_path / "test_tenants.db"
    monkeypatch.setattr("api.tenants.get_db_path", lambda: db_file)
    return db_file


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A real (test-only) Fernet key, isolated per test via monkeypatch."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(config_module.config, "tenant_db_encryption_key", key)
    return key


class TestHashApiKey:
    def test_same_key_hashes_identically(self) -> None:
        assert hash_api_key("abc") == hash_api_key("abc")

    def test_different_keys_hash_differently(self) -> None:
        assert hash_api_key("abc") != hash_api_key("xyz")

    def test_raw_key_never_appears_in_its_own_hash(self) -> None:
        assert "abc" not in hash_api_key("abc")


class TestCreateTenant:
    def test_returns_tenant_id_and_raw_key(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        assert tenant_id
        assert raw_key

    def test_platform_db_url_is_encrypted_at_rest(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        create_tenant("acme", "postgresql://u:p@h/db")
        conn = sqlite3.connect(isolated_tenants_db)
        row = conn.execute("SELECT platform_db_url_encrypted FROM tenants").fetchone()
        conn.close()
        assert "postgresql://u:p@h/db" not in row[0]

    def test_raw_key_is_never_stored(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        _, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        conn = sqlite3.connect(isolated_tenants_db)
        row = conn.execute("SELECT * FROM tenants").fetchone()
        conn.close()
        assert raw_key not in row


class TestGetTenantByKeyHash:
    def test_correct_key_resolves_the_right_tenant(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")

        result = get_tenant_by_key_hash(hash_api_key(raw_key))

        assert result is not None
        assert result.tenant_id == tenant_id
        assert result.platform_db_url == "postgresql://u:p@h/db"

    def test_wrong_key_returns_none(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        create_tenant("acme", "postgresql://u:p@h/db")
        assert get_tenant_by_key_hash(hash_api_key("wrong-key")) is None

    def test_deactivated_tenant_returns_none(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        conn = sqlite3.connect(isolated_tenants_db)
        conn.execute("UPDATE tenants SET is_active = 0 WHERE id = ?", (tenant_id,))
        conn.commit()
        conn.close()

        assert get_tenant_by_key_hash(hash_api_key(raw_key)) is None


class TestMissingEncryptionKey:
    def test_create_tenant_raises_clear_error(self, isolated_tenants_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_module.config, "tenant_db_encryption_key", None)

        with pytest.raises(RuntimeError, match="TENANT_DB_ENCRYPTION_KEY"):
            create_tenant("acme", "postgresql://u:p@h/db")
