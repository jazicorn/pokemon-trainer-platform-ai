"""Tenant account store — the source of truth for API keys and per-tenant
database routing.

Separate from `data/memory.db` (the CLI's own single-user local data) and
from the global `PLATFORM_DB_URL` (the CLI's single configured platform
database) — this is operator-owned: one row per tenant, each with its own
encrypted `platform_db_url` and hashed API key. See ROADMAP.md Phase 3.

Provisioned either by `scripts/provision_tenant.py` (admin override) or
self-serve via `POST /v1/accounts/register` (see `api.registration`,
ROADMAP.md Phase 15) — both insert the same row shape.
"""

from __future__ import annotations

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
        conn.commit()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, sql_type: str) -> None:
    """SQLite has no `ADD COLUMN IF NOT EXISTS`, so check `PRAGMA table_info`
    first. Nullable — a tenant row created before this migration has no
    recoverable last-4 to backfill (Phase 3 never stored the raw key), so
    `api_key_last4` is None for tenants until they next rotate.
    """
    existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing_columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


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


def create_tenant(name: str, platform_db_url: str) -> tuple[str, str]:
    """Provision a new tenant: generate a key, encrypt the DB URL, insert the row.

    Args:
        name: A label for the tenant (e.g. their contact email).
        platform_db_url: The tenant's own Postgres connection string, matching
            the schema contract in docs/REFERENCE/PLATFORM_DB.md.

    Returns:
        (tenant_id, raw_api_key) — the raw key is returned exactly once; it
        is never stored and cannot be retrieved again after this call.
    """
    init_tenants_db()

    tenant_id = secrets.token_hex(8)
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)
    encrypted_url = _get_fernet().encrypt(platform_db_url.encode()).decode()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tenants (id, name, api_key_hash, platform_db_url_encrypted, is_active, api_key_last4)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (tenant_id, name, key_hash, encrypted_url, raw_key[-4:]),
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
            "SELECT id, platform_db_url_encrypted FROM tenants WHERE api_key_hash = ? AND is_active = 1",
            (key_hash,),
        ).fetchone()

    if row is None:
        return None

    decrypted_url = _get_fernet().decrypt(row["platform_db_url_encrypted"].encode()).decode()
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
            "SELECT id, name, created_at, is_active, api_key_last4 FROM tenants ORDER BY created_at DESC, rowid DESC"
        ).fetchall()

    return [
        TenantSummary(
            tenant_id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
            api_key_last4=row["api_key_last4"],
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
            "SELECT id, name, created_at, is_active, api_key_last4, platform_db_url_encrypted "
            "FROM tenants WHERE id = ?",
            (tenant_id,),
        ).fetchone()

    if row is None:
        return None

    decrypted_url = _get_fernet().decrypt(row["platform_db_url_encrypted"].encode()).decode()
    return TenantDetail(
        tenant_id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
        api_key_last4=row["api_key_last4"],
        platform_db_url=decrypted_url,
    )
