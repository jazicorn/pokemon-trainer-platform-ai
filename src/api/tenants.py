"""Tenant account store — the source of truth for API keys and per-tenant
database routing.

Separate from `data/memory.db` (the CLI's own single-user local data) and
from the global `PLATFORM_DB_URL` (the CLI's single configured platform
database) — this is operator-owned: one row per tenant, each with its own
encrypted `platform_db_url` and hashed API key. See ROADMAP.md Phase 3.

Provisioning is admin-only for now (`scripts/provision_tenant.py`); Phase 15
adds self-serve registration on top of this same schema.
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
    """Create the tenants table if it doesn't already exist."""
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
        conn.commit()


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
            INSERT INTO tenants (id, name, api_key_hash, platform_db_url_encrypted, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (tenant_id, name, key_hash, encrypted_url),
        )
        conn.commit()

    return tenant_id, raw_key


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
