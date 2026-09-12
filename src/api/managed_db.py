"""Managed Postgres provisioning via Aiven (ROADMAP_PLATFORM.md Phase 17).

Lets a tenant register without bringing their own `PLATFORM_DB_URL` — this
module provisions a dedicated database for them instead, on one shared
Aiven PostgreSQL *service* (one Postgres server, one database per tenant,
per that phase's design note — not a shared database with a tenant_id
column, and not a separate managed-service instance per tenant).

Aiven documents creating multiple databases within one service, including
via a plain Postgres client connection — unlike some BaaS platforms (e.g.
Supabase), whose own dashboard/tooling only recognizes a project's single
default database. `CREATE DATABASE`/`CREATE ROLE` here is Aiven's own
supported path, not a workaround.
"""

from __future__ import annotations

import re
import secrets
from typing import LiteralString
from urllib.parse import urlsplit, urlunsplit

from config import config

# tenant_id is always api.tenants.create_tenant()'s secrets.token_hex(8)
# output — hex-only. Validated here anyway before use in an identifier
# position, since Postgres has no parameterized identifiers.
_TENANT_ID_PATTERN = re.compile(r"^[0-9a-f]+$")

# The exact schema contract from docs/REFERENCE/PLATFORM_DB.md — one source
# of truth for both a self-hosted operator following that doc by hand and
# this automated path. Split into individual statements: psycopg's execute()
# runs one command per call, not a semicolon-separated batch.
SCHEMA_STATEMENTS: list[LiteralString] = [
    """
    CREATE TABLE trades (
        trade_id          TEXT        PRIMARY KEY,
        traded_at         TIMESTAMPTZ NOT NULL,
        offered_pokemon   TEXT        NOT NULL,
        requested_pokemon TEXT        NOT NULL,
        status            TEXT        NOT NULL
                          CHECK (status IN ('pending', 'completed', 'rejected', 'cancelled')),
        user_a_id         TEXT        NOT NULL,
        user_b_id         TEXT        NOT NULL
    )
    """,
    "CREATE INDEX idx_trades_traded_at ON trades (traded_at DESC)",
    """
    CREATE TABLE user_pokemon (
        id            BIGSERIAL PRIMARY KEY,
        user_id       TEXT      NOT NULL,
        pokemon_id    TEXT      NOT NULL,
        nickname      TEXT,
        acquired_date DATE      NOT NULL,
        acquired_via  TEXT      NOT NULL,
        tradeable     BOOLEAN   NOT NULL DEFAULT TRUE,
        is_shiny      BOOLEAN   NOT NULL DEFAULT FALSE,
        ball_type     TEXT
    )
    """,
    "CREATE INDEX idx_user_pokemon_user_id ON user_pokemon (user_id)",
    """
    CREATE TABLE user_preferences (
        user_id        TEXT    PRIMARY KEY,
        favorite_types TEXT[]  NOT NULL DEFAULT '{}',
        goal           TEXT    NOT NULL DEFAULT '',
        trading_style  TEXT    NOT NULL DEFAULT 'balanced',
        never_trade    TEXT[]  NOT NULL DEFAULT '{}',
        seeking        TEXT[]  NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE user_trade_history (
        id         BIGSERIAL PRIMARY KEY,
        user_id    TEXT      NOT NULL,
        trade_id   TEXT      NOT NULL,
        traded_at  DATE      NOT NULL,
        gave       TEXT      NOT NULL,
        received   TEXT      NOT NULL,
        satisfied  BOOLEAN   NOT NULL DEFAULT TRUE
    )
    """,
    "CREATE INDEX idx_user_trade_history_user_id ON user_trade_history (user_id)",
    """
    CREATE TABLE trade_offers (
        id                BIGSERIAL   PRIMARY KEY,
        sender_id         TEXT        NOT NULL,
        recipient_id      TEXT        NOT NULL,
        offered_pokemon   TEXT        NOT NULL,
        requested_pokemon TEXT        NOT NULL,
        status            TEXT        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
        ai_analysis       TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        responded_at      TIMESTAMPTZ
    )
    """,
    "CREATE INDEX idx_trade_offers_recipient ON trade_offers (recipient_id, status)",
]


class ManagedDBNotConfiguredError(RuntimeError):
    """AIVEN_ADMIN_DB_URL isn't set — raised at the point of use, same
    pattern as api.tenants._get_fernet()'s missing-key error.
    """


def _admin_url() -> str:
    url = config.aiven_admin_db_url
    if not url:
        raise ManagedDBNotConfiguredError(
            "AIVEN_ADMIN_DB_URL is not set. It should point at one Aiven PostgreSQL "
            "service's admin connection — see docs/REFERENCE/PLATFORM_DB.md."
        )
    return url


def _with_database(url: str, database: str) -> str:
    """The same connection, pointed at a different database name."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _tenant_connection_string(admin_url: str, database: str, role: str, password: str) -> str:
    """The tenant's own connection string — that role's credentials only,
    never the admin/superuser's own. `sslmode=require` carries over from the
    admin URL's own query string (Aiven connection strings already include
    it) or is added if somehow missing.
    """
    parts = urlsplit(admin_url)
    netloc = f"{role}:{password}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    query = parts.query or "sslmode=require"
    return urlunsplit((parts.scheme, netloc, f"/{database}", query, ""))


def provision_managed_database(tenant_id: str) -> str:
    """Provision a dedicated database + role for one tenant on the shared
    Aiven service, run the schema contract against it, and return that
    tenant's own connection string.

    Raises:
        ValueError: tenant_id isn't the expected hex format.
        ManagedDBNotConfiguredError: AIVEN_ADMIN_DB_URL isn't set.
    """
    if not _TENANT_ID_PATTERN.match(tenant_id):
        raise ValueError(f"tenant_id must be hex-only (got {tenant_id!r})")

    admin_url = _admin_url()
    database = f"tenant_{tenant_id}"
    role = f"tenant_{tenant_id}"
    password = secrets.token_urlsafe(32)

    import psycopg  # pyright: ignore[reportMissingImports]
    from psycopg import sql  # pyright: ignore[reportMissingImports]

    # sql.Identifier/sql.Literal quote and escape properly — the regex check
    # above already guarantees database/role are hex-only, and
    # secrets.token_urlsafe's alphabet has no quote characters, but
    # composing this way is the correct psycopg idiom regardless of that,
    # not a workaround for it.
    database_id = sql.Identifier(database)
    role_id = sql.Identifier(role)

    # autocommit=True: CREATE DATABASE can't run inside a transaction block.
    with psycopg.connect(admin_url, autocommit=True) as admin_conn:
        admin_conn.execute(sql.SQL("CREATE DATABASE {}").format(database_id))
        admin_conn.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(role_id, sql.Literal(password)))

    with psycopg.connect(_with_database(admin_url, database), autocommit=True) as tenant_db_conn:
        for statement in SCHEMA_STATEMENTS:
            tenant_db_conn.execute(statement)
        # Same grants as docs/REFERENCE/PLATFORM_DB.md's "Database Role
        # (Recommended)" section, automated per tenant instead of a manual
        # one-time step.
        tenant_db_conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database_id, role_id))
        tenant_db_conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role_id))
        tenant_db_conn.execute(
            sql.SQL("GRANT SELECT ON trades, user_pokemon, user_preferences, user_trade_history TO {}").format(role_id)
        )
        tenant_db_conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON trade_offers TO {}").format(role_id))
        tenant_db_conn.execute(sql.SQL("GRANT USAGE ON SEQUENCE trade_offers_id_seq TO {}").format(role_id))

    return _tenant_connection_string(admin_url, database, role, password)
