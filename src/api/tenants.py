"""Tenant account store — the source of truth for API keys and per-tenant
database routing.

Separate from `data/memory.db` (the CLI's own single-user local data) and
from the global `PLATFORM_DB_URL` (the CLI's single configured platform
database) — this is operator-owned: one row per tenant, each with its own
encrypted `platform_db_url` and hashed API key. See ROADMAP.md Phase 3.

Provisioned either by `scripts/provision_tenant.py` (admin override), self-serve
via `POST /v1/accounts/register` with a caller-supplied `platform_db_url` (see
`api.registration`, ROADMAP.md Phase 15), or self-serve with a database
provisioned automatically (`api.managed_db`, ROADMAP_PLATFORM.md Phase 17) — all
three insert the same row shape.

`platform_db_url` is encrypted per-tenant via a Vault-wrapped Data Encryption
Key (`api.kms`, Phase 17), not the single static `TENANT_DB_ENCRYPTION_KEY`
Phase 3 originally used — see `_encrypt_platform_db_url`/`_decrypt_stored_url`.
A tenant row created before Phase 17 keeps working on the old static key until
`scripts/migrate_to_vault_encryption.py` migrates it.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet

from config import config

DB_NAME = "tenants.db"


def get_db_path() -> Path:
    """Get the tenants database file path (data/tenants.db)."""
    db_dir = Path(__file__).parent.parent.parent / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / DB_NAME


@contextmanager
def get_connection() -> Generator[sqlite3.Connection]:
    """Get a database connection as context manager."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_tenants_db() -> None:
    """Create the tenants table if it doesn't already exist, and apply any
    schema migrations an existing database is missing.
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                api_key_hash TEXT NOT NULL UNIQUE,
                platform_db_url_encrypted TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        _add_column_if_missing(conn, "tenants", "api_key_last4", "TEXT")
        # Phase 17 — envelope encryption + managed-hosting metadata. All
        # three are nullable/defaulted so an existing row keeps working
        # unmigrated: wrapped_dek NULL means "still on the Phase 3 static
        # key" (see _decrypt_stored_url); hosting/analytics_opt_in default
        # to the self-hosted values every pre-Phase-17 tenant actually is.
        _add_column_if_missing(conn, "tenants", "wrapped_dek", "TEXT")
        _add_column_if_missing(conn, "tenants", "hosting", "TEXT NOT NULL DEFAULT 'self_hosted'")
        _add_column_if_missing(conn, "tenants", "analytics_opt_in", "INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, column_definition: str) -> None:
    """SQLite has no `ADD COLUMN IF NOT EXISTS`, so check `PRAGMA table_info`
    first. `column_definition` is the SQL type plus any constraints (e.g.
    `"TEXT"`, or `"INTEGER NOT NULL DEFAULT 0"` to backfill existing rows).
    """
    existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing_columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_definition}")


def _get_fernet() -> Fernet:
    """Build the Fernet cipher from TENANT_DB_ENCRYPTION_KEY.

    Raises:
        RuntimeError: if the env var isn't set — every tenant operation needs
            it, so failing loudly here beats a confusing downstream error
            (e.g. a mysterious decrypt failure deep in a request handler).
    """
    key = config.tenant_db_encryption_key
    if not key:
        raise RuntimeError(
            "TENANT_DB_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "and back it up outside the deployment — losing it makes every stored "
            "platform_db_url permanently unrecoverable, not just hard to find."
        )
    return Fernet(key.encode())


def _encrypt_platform_db_url(url: str) -> tuple[str, str]:
    """Encrypt url with a fresh Vault-wrapped DEK (ROADMAP_PLATFORM.md
    Phase 17) — the scheme every new tenant gets now, replacing the single
    static TENANT_DB_ENCRYPTION_KEY above.

    Returns:
        (ciphertext, wrapped_dek) — both stored in tenants.db; the
        plaintext DEK itself is never persisted anywhere.
    """
    from api.kms import wrap_new_dek

    plaintext_dek, wrapped_dek = wrap_new_dek()
    ciphertext = Fernet(base64.urlsafe_b64encode(plaintext_dek)).encrypt(url.encode()).decode()
    return ciphertext, wrapped_dek


def _decrypt_platform_db_url(ciphertext: str, wrapped_dek: str) -> str:
    """The Phase 17 counterpart to _encrypt_platform_db_url: unwrap this
    tenant's own DEK via Vault, then Fernet-decrypt with it.
    """
    from api.kms import unwrap_dek

    plaintext_dek = unwrap_dek(wrapped_dek)
    return Fernet(base64.urlsafe_b64encode(plaintext_dek)).decrypt(ciphertext.encode()).decode()


def _decrypt_stored_url(ciphertext: str, wrapped_dek: str | None) -> str:
    """Dispatch to the right decryption scheme for one stored row:
    wrapped_dek set means Phase 17's per-tenant Vault DEK; NULL means a row
    scripts/migrate_to_vault_encryption.py hasn't migrated yet, still on
    Phase 3's static TENANT_DB_ENCRYPTION_KEY.
    """
    if wrapped_dek is not None:
        return _decrypt_platform_db_url(ciphertext, wrapped_dek)
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of a raw API key, for storage/lookup.

    The raw key itself is never stored or logged anywhere — same convention
    as GitHub/Stripe tokens, shown once at issuance and never retrievable
    again.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()


@dataclass
class TenantContext:
    """Resolved tenant identity + database routing for a single request."""

    tenant_id: str
    platform_db_url: str


@dataclass
class TenantSummary:
    """One row of the admin UI's tenant list (Phase 16) — never the
    decrypted `platform_db_url`, matching that page's own design note.
    """

    tenant_id: str
    name: str
    created_at: str
    is_active: bool
    api_key_last4: str | None
    hosting: str


@dataclass
class TenantDetail:
    """The admin UI's tenant detail view (Phase 16) — includes the decrypted
    `platform_db_url`, unlike `TenantSummary`; the admin app itself decides
    how much of it to actually render (masked by default, full DSN only
    after a "reveal" re-checks ADMIN_TOKEN).
    """

    tenant_id: str
    name: str
    created_at: str
    is_active: bool
    api_key_last4: str | None
    platform_db_url: str
    hosting: str
    analytics_opt_in: bool


def create_tenant(
    name: str,
    platform_db_url: str | None = None,
    *,
    use_managed_db: bool = False,
    analytics_opt_in: bool | None = None,
) -> tuple[str, str]:
    """Provision a new tenant: resolve its database, generate a key, encrypt
    the DB URL, insert the row.

    Args:
        name: A label for the tenant (e.g. their contact email).
        platform_db_url: The tenant's own Postgres connection string, matching
            the schema contract in docs/REFERENCE/PLATFORM_DB.md. Required
            when use_managed_db is False; ignored (a database is provisioned
            instead) when True.
        use_managed_db: Provision a dedicated Aiven database instead of using
            a caller-supplied platform_db_url (ROADMAP_PLATFORM.md Phase 17).
        analytics_opt_in: Whether this tenant's data feeds Phase 18's
            cross-tenant analytics. Defaults to True for managed tenants,
            False for self-hosted ones (per that phase's design) — either
            way, caller-overridable independent of hosting.

    Returns:
        (tenant_id, raw_api_key) — the raw key is returned exactly once; it
        is never stored and cannot be retrieved again after this call.

    Raises:
        ValueError: use_managed_db is False and no platform_db_url was given.
    """
    init_tenants_db()

    tenant_id = secrets.token_hex(8)

    if use_managed_db:
        from api.managed_db import provision_managed_database

        platform_db_url = provision_managed_database(tenant_id)
        hosting = "managed"
    else:
        if not platform_db_url:
            raise ValueError("platform_db_url is required when use_managed_db is False")
        hosting = "self_hosted"

    if analytics_opt_in is None:
        analytics_opt_in = use_managed_db

    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)
    encrypted_url, wrapped_dek = _encrypt_platform_db_url(platform_db_url)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tenants (
                id, name, api_key_hash, platform_db_url_encrypted, is_active,
                api_key_last4, wrapped_dek, hosting, analytics_opt_in
            )
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (tenant_id, name, key_hash, encrypted_url, raw_key[-4:], wrapped_dek, hosting, int(analytics_opt_in)),
        )
        conn.commit()

    return tenant_id, raw_key


def rotate_api_key(tenant_id: str) -> str:
    """Replace a tenant's API key with a newly generated one.

    The old key stops working immediately (its hash is overwritten, not kept
    alongside the new one). Returns the new raw key — shown once, same as
    `create_tenant`.
    """
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)

    with get_connection() as conn:
        conn.execute(
            "UPDATE tenants SET api_key_hash = ?, api_key_last4 = ? WHERE id = ?",
            (key_hash, raw_key[-4:], tenant_id),
        )
        conn.commit()

    return raw_key


def deactivate_tenant(tenant_id: str) -> None:
    """Deactivate a tenant — a soft delete, not a row removal.

    Matches `is_active`'s existing role in `get_tenant_by_key_hash`: a
    deactivated tenant's key stops resolving, indistinguishable from a
    wrong key, so a revoked key doesn't reveal it once existed.
    """
    with get_connection() as conn:
        conn.execute("UPDATE tenants SET is_active = 0 WHERE id = ?", (tenant_id,))
        conn.commit()


def get_tenant_by_key_hash(key_hash: str) -> TenantContext | None:
    """Look up an active tenant by API key hash, decrypting its platform_db_url.

    Returns:
        None if no *active* tenant matches — the caller (`require_api_key`)
        turns that into an HTTP 403, same for "wrong key" and "deactivated
        tenant" so neither state leaks which one it was.
    """
    init_tenants_db()

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, platform_db_url_encrypted, wrapped_dek FROM tenants WHERE api_key_hash = ? AND is_active = 1",
            (key_hash,),
        ).fetchone()

    if row is None:
        return None

    decrypted_url = _decrypt_stored_url(row["platform_db_url_encrypted"], row["wrapped_dek"])
    return TenantContext(tenant_id=row["id"], platform_db_url=decrypted_url)


def list_tenants() -> list[TenantSummary]:
    """Every tenant, most recently created first — for the admin UI's list
    page (Phase 16). Never touches `platform_db_url_encrypted` at all, let
    alone decrypts it — that page deliberately never shows it.
    """
    init_tenants_db()

    with get_connection() as conn:
        rows = conn.execute(
            # rowid DESC as a tiebreaker: created_at has only second-level
            # resolution, so two tenants created within the same second
            # would otherwise sort arbitrarily against each other.
            "SELECT id, name, created_at, is_active, api_key_last4, hosting FROM tenants "
            "ORDER BY created_at DESC, rowid DESC"
        ).fetchall()

    return [
        TenantSummary(
            tenant_id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
            api_key_last4=row["api_key_last4"],
            hosting=row["hosting"],
        )
        for row in rows
    ]


def get_tenant_by_id(tenant_id: str) -> TenantDetail | None:
    """One tenant's full detail, decrypted `platform_db_url` included — for
    the admin UI's detail page (Phase 16). Unlike `get_tenant_by_key_hash`,
    this returns an inactive tenant too (an operator managing tenants needs
    to see deactivated ones, not just active ones an API caller can reach).
    """
    init_tenants_db()

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at, is_active, api_key_last4, platform_db_url_encrypted, "
            "wrapped_dek, hosting, analytics_opt_in FROM tenants WHERE id = ?",
            (tenant_id,),
        ).fetchone()

    if row is None:
        return None

    decrypted_url = _decrypt_stored_url(row["platform_db_url_encrypted"], row["wrapped_dek"])
    return TenantDetail(
        tenant_id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
        api_key_last4=row["api_key_last4"],
        platform_db_url=decrypted_url,
        hosting=row["hosting"],
        analytics_opt_in=bool(row["analytics_opt_in"]),
    )


def list_unmigrated_tenant_ids() -> list[str]:
    """Every tenant still on Phase 3's static-key encryption scheme —
    scripts/migrate_to_vault_encryption.py iterates this to know what's left.
    """
    init_tenants_db()

    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM tenants WHERE wrapped_dek IS NULL").fetchall()

    return [row["id"] for row in rows]


def migrate_tenant_to_vault_encryption(tenant_id: str) -> bool:
    """Re-encrypt one tenant's platform_db_url under a fresh Vault-wrapped
    DEK, replacing the Phase 3 static-key ciphertext.

    Idempotent: a tenant already migrated (wrapped_dek already set) is left
    untouched, so re-running the migration script is always safe.

    Returns:
        True if this call actually migrated the row; False if it was
        already migrated or the tenant doesn't exist.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT platform_db_url_encrypted, wrapped_dek FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone()
        if row is None or row["wrapped_dek"] is not None:
            return False

        decrypted_url = _get_fernet().decrypt(row["platform_db_url_encrypted"].encode()).decode()
        new_ciphertext, wrapped_dek = _encrypt_platform_db_url(decrypted_url)

        conn.execute(
            "UPDATE tenants SET platform_db_url_encrypted = ?, wrapped_dek = ? WHERE id = ?",
            (new_ciphertext, wrapped_dek, tenant_id),
        )
        conn.commit()

    return True
