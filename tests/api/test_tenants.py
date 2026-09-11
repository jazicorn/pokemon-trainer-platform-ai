"""Tests for the tenant account store — api.tenants (ROADMAP.md Phase 3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import config as config_module
from api.tenants import (
    create_tenant,
    deactivate_tenant,
    get_tenant_by_id,
    get_tenant_by_key_hash,
    hash_api_key,
    init_tenants_db,
    list_tenants,
    rotate_api_key,
)


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

    def test_stores_only_the_last_4_chars_of_the_key(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        _, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        conn = sqlite3.connect(isolated_tenants_db)
        row = conn.execute("SELECT api_key_last4 FROM tenants").fetchone()
        conn.close()
        assert row[0] == raw_key[-4:]


class TestRotateApiKey:
    def test_old_key_stops_resolving_new_key_works(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, old_key = create_tenant("acme", "postgresql://u:p@h/db")

        new_key = rotate_api_key(tenant_id)

        assert new_key != old_key
        assert get_tenant_by_key_hash(hash_api_key(old_key)) is None
        result = get_tenant_by_key_hash(hash_api_key(new_key))
        assert result is not None
        assert result.tenant_id == tenant_id

    def test_updates_the_stored_last4(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")
        new_key = rotate_api_key(tenant_id)

        tenant = get_tenant_by_id(tenant_id)

        assert tenant is not None
        assert tenant.api_key_last4 == new_key[-4:]


class TestDeactivateTenant:
    def test_deactivated_tenant_stops_resolving(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")

        deactivate_tenant(tenant_id)

        assert get_tenant_by_key_hash(hash_api_key(raw_key)) is None

    def test_get_tenant_by_id_still_returns_it(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        """Unlike get_tenant_by_key_hash, get_tenant_by_id (the admin UI's
        own lookup) must still see a deactivated tenant — an operator
        managing tenants needs to see inactive ones too.
        """
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")
        deactivate_tenant(tenant_id)

        tenant = get_tenant_by_id(tenant_id)

        assert tenant is not None
        assert tenant.is_active is False


class TestListTenants:
    def test_empty_when_no_tenants(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        assert list_tenants() == []

    def test_returns_every_tenant_most_recent_first(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        first_id, _ = create_tenant("acme", "postgresql://u:p@h/db1")
        second_id, _ = create_tenant("beta", "postgresql://u:p@h/db2")

        summaries = list_tenants()

        assert [t.tenant_id for t in summaries] == [second_id, first_id]

    def test_never_exposes_platform_db_url(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        create_tenant("acme", "postgresql://u:p@h/db")
        summary = list_tenants()[0]
        assert not hasattr(summary, "platform_db_url")

    def test_includes_masked_key_fragment(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        _, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        assert list_tenants()[0].api_key_last4 == raw_key[-4:]


class TestGetTenantById:
    def test_returns_full_detail_including_decrypted_url(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")

        tenant = get_tenant_by_id(tenant_id)

        assert tenant is not None
        assert tenant.name == "acme"
        assert tenant.platform_db_url == "postgresql://u:p@h/db"

    def test_unknown_id_returns_none(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        assert get_tenant_by_id("does-not-exist") is None


class TestSchemaMigration:
    def test_api_key_last4_is_added_to_a_pre_existing_table(
        self, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        """A tenants.db created before Phase 16 has no api_key_last4 column —
        init_tenants_db() must add it without dropping existing data.
        """
        conn = sqlite3.connect(isolated_tenants_db)
        conn.execute(
            """
            CREATE TABLE tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                api_key_hash TEXT NOT NULL UNIQUE,
                platform_db_url_encrypted TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            "INSERT INTO tenants (id, name, api_key_hash, platform_db_url_encrypted) VALUES (?, ?, ?, ?)",
            ("pre-existing", "acme", "somehash", "encrypted"),
        )
        conn.commit()
        conn.close()

        init_tenants_db()

        conn = sqlite3.connect(isolated_tenants_db)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tenants)").fetchall()}
        row = conn.execute("SELECT api_key_last4 FROM tenants WHERE id = ?", ("pre-existing",)).fetchone()
        conn.close()

        assert "api_key_last4" in columns
        assert row[0] is None  # nothing to backfill — the raw key was never stored


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
