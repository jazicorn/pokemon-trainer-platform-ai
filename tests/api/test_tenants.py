"""Tests for the tenant account store — api.tenants (ROADMAP.md Phase 3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import config as config_module
from api.kms import VaultNotConfiguredError
from api.tenants import (
    create_tenant,
    deactivate_tenant,
    get_tenant_by_id,
    get_tenant_by_key_hash,
    hash_api_key,
    init_tenants_db,
    list_tenants,
    list_unmigrated_tenant_ids,
    migrate_tenant_to_vault_encryption,
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

    def test_self_hosted_is_the_default_hosting_and_opts_out_of_analytics(
        self, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db")
        tenant = get_tenant_by_id(tenant_id)
        assert tenant is not None
        assert tenant.hosting == "self_hosted"
        assert tenant.analytics_opt_in is False

    def test_self_hosted_without_platform_db_url_raises(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        with pytest.raises(ValueError, match="platform_db_url is required"):
            create_tenant("acme")

    def test_analytics_opt_in_is_overridable_for_self_hosted(
        self, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        tenant_id, _ = create_tenant("acme", "postgresql://u:p@h/db", analytics_opt_in=True)
        tenant = get_tenant_by_id(tenant_id)
        assert tenant is not None
        assert tenant.analytics_opt_in is True


def _fake_provision_named_db(tenant_id: str) -> str:
    return f"postgresql://tenant_{tenant_id}/db"


def _fake_provision_fixed_db(tenant_id: str) -> str:
    return "postgresql://h/db"


class TestCreateTenantManagedDb:
    def test_provisions_a_database_instead_of_using_platform_db_url(
        self, isolated_tenants_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("api.managed_db.provision_managed_database", _fake_provision_named_db)

        tenant_id, _ = create_tenant("acme", "postgresql://ignored:should-not-be-used@h/db", use_managed_db=True)

        tenant = get_tenant_by_id(tenant_id)
        assert tenant is not None
        assert tenant.hosting == "managed"
        assert tenant.platform_db_url == f"postgresql://tenant_{tenant_id}/db"
        assert "ignored" not in tenant.platform_db_url

    def test_analytics_opt_in_defaults_true_for_managed(
        self, isolated_tenants_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("api.managed_db.provision_managed_database", _fake_provision_fixed_db)

        tenant_id, _ = create_tenant("acme", use_managed_db=True)

        tenant = get_tenant_by_id(tenant_id)
        assert tenant is not None
        assert tenant.analytics_opt_in is True

    def test_analytics_opt_in_is_overridable_for_managed(
        self, isolated_tenants_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("api.managed_db.provision_managed_database", _fake_provision_fixed_db)

        tenant_id, _ = create_tenant("acme", use_managed_db=True, analytics_opt_in=False)

        tenant = get_tenant_by_id(tenant_id)
        assert tenant is not None
        assert tenant.analytics_opt_in is False


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


class TestMissingVaultConfig:
    """Phase 17 replaced the single static TENANT_DB_ENCRYPTION_KEY with a
    per-tenant Vault-wrapped DEK for every new tenant — create_tenant() now
    depends on Vault being configured, not that env var.
    """

    def test_create_tenant_raises_clear_error(self, isolated_tenants_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_module.config, "vault_addr", None)
        monkeypatch.setattr(config_module.config, "vault_token", None)

        with pytest.raises(VaultNotConfiguredError, match="VAULT_ADDR"):
            create_tenant("acme", "postgresql://u:p@h/db")

    def test_tenant_db_encryption_key_is_no_longer_required_for_new_tenants(
        self, isolated_tenants_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config_module.config, "tenant_db_encryption_key", None)

        tenant_id, raw_key = create_tenant("acme", "postgresql://u:p@h/db")

        assert tenant_id
        assert raw_key


def _insert_legacy_tenant(db_path: Path, encryption_key: str, tenant_id: str, platform_db_url: str) -> str:
    """Insert a row exactly as Phase 3 would have — static-key Fernet
    ciphertext, wrapped_dek left NULL — to test the pre-Phase-17 decrypt
    path and the migration script's own starting state.

    Returns the raw API key (for looking the tenant back up).
    """
    raw_key = "legacy-raw-key-" + tenant_id
    encrypted_url = Fernet(encryption_key.encode()).encrypt(platform_db_url.encode()).decode()

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO tenants (id, name, api_key_hash, platform_db_url_encrypted, is_active, wrapped_dek)
        VALUES (?, ?, ?, ?, 1, NULL)
        """,
        (tenant_id, "legacy-tenant", hash_api_key(raw_key), encrypted_url),
    )
    conn.commit()
    conn.close()
    return raw_key


class TestLegacyDecryption:
    """A tenant row created before Phase 17 (wrapped_dek NULL) must keep
    resolving correctly on the old static-key scheme, without requiring
    Vault at all — migration is operator-paced, not a hard cutover.
    """

    def test_get_tenant_by_key_hash_decrypts_a_legacy_row(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        init_tenants_db()
        raw_key = _insert_legacy_tenant(isolated_tenants_db, encryption_key, "legacy1", "postgresql://u:p@h/legacydb")

        result = get_tenant_by_key_hash(hash_api_key(raw_key))

        assert result is not None
        assert result.platform_db_url == "postgresql://u:p@h/legacydb"

    def test_get_tenant_by_id_decrypts_a_legacy_row(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        init_tenants_db()
        _insert_legacy_tenant(isolated_tenants_db, encryption_key, "legacy2", "postgresql://u:p@h/legacydb2")

        tenant = get_tenant_by_id("legacy2")

        assert tenant is not None
        assert tenant.platform_db_url == "postgresql://u:p@h/legacydb2"

    def test_legacy_row_never_needs_vault(
        self, isolated_tenants_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config_module.config, "vault_addr", None)
        monkeypatch.setattr(config_module.config, "vault_token", None)
        init_tenants_db()
        raw_key = _insert_legacy_tenant(isolated_tenants_db, encryption_key, "legacy3", "postgresql://u:p@h/legacydb3")

        result = get_tenant_by_key_hash(hash_api_key(raw_key))

        assert result is not None
        assert result.platform_db_url == "postgresql://u:p@h/legacydb3"


class TestMigrateToVaultEncryption:
    def test_list_unmigrated_tenant_ids_includes_legacy_rows_only(
        self, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        init_tenants_db()
        _insert_legacy_tenant(isolated_tenants_db, encryption_key, "legacy1", "postgresql://u:p@h/db1")
        migrated_id, _ = create_tenant("acme", "postgresql://u:p@h/db2")

        unmigrated = list_unmigrated_tenant_ids()

        assert "legacy1" in unmigrated
        assert migrated_id not in unmigrated

    def test_migrates_a_legacy_row_and_it_still_decrypts_correctly(
        self, isolated_tenants_db: Path, encryption_key: str
    ) -> None:
        init_tenants_db()
        raw_key = _insert_legacy_tenant(isolated_tenants_db, encryption_key, "legacy1", "postgresql://u:p@h/legacydb")

        migrated = migrate_tenant_to_vault_encryption("legacy1")

        assert migrated is True
        assert "legacy1" not in list_unmigrated_tenant_ids()
        result = get_tenant_by_key_hash(hash_api_key(raw_key))
        assert result is not None
        assert result.platform_db_url == "postgresql://u:p@h/legacydb"

    def test_is_idempotent(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        init_tenants_db()
        _insert_legacy_tenant(isolated_tenants_db, encryption_key, "legacy1", "postgresql://u:p@h/legacydb")

        assert migrate_tenant_to_vault_encryption("legacy1") is True
        assert migrate_tenant_to_vault_encryption("legacy1") is False

    def test_unknown_tenant_returns_false(self, isolated_tenants_db: Path, encryption_key: str) -> None:
        init_tenants_db()
        assert migrate_tenant_to_vault_encryption("does-not-exist") is False
