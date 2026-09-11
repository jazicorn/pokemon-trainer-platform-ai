"""Validates a submitted `platform_db_url` before it's ever stored — used by
self-serve registration (ROADMAP.md Phase 15).

`scripts/provision_tenant.py`'s admin path trusts you to hand it a working
DSN. A public registration endpoint can't make that assumption: reject a bad
one up front, naming what's wrong, rather than storing it and letting the
tenant discover it's broken on their first real request.
"""

from __future__ import annotations

import importlib.util

# See data/platform_db.py's own note on this pattern: checked by name so this
# module still imports cleanly when the optional `platform-db` group isn't
# installed; the real import happens in validate_platform_db_url() below.
_PSYCOPG_AVAILABLE = importlib.util.find_spec("psycopg") is not None

# Every table docs/REFERENCE/PLATFORM_DB.md's schema contract requires.
REQUIRED_TABLES = frozenset(
    {
        "trades",
        "user_pokemon",
        "user_preferences",
        "user_trade_history",
        "trade_offers",
    }
)


class PlatformDBValidationError(Exception):
    """A submitted `platform_db_url` failed validation — message is caller-safe."""


def validate_platform_db_url(dsn: str) -> None:
    """Connect to `dsn` and confirm every required table exists.

    Raises:
        PlatformDBValidationError: connection failed, or one or more required
            tables are missing — the message names exactly what's wrong,
            safe to return directly in a 4xx response.
        RuntimeError: the `platform-db` dependency group isn't installed on
            this server — an operator/deployment problem, not the caller's.
    """
    if not _PSYCOPG_AVAILABLE:
        raise RuntimeError(
            "platform_db_url validation requires the 'platform-db' dependency group "
            "(psycopg). Run `uv sync --group platform-db`."
        )

    import psycopg  # pyright: ignore[reportMissingImports]

    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            existing_tables = {row[0] for row in cur.fetchall()}
    except Exception as e:  # noqa: BLE001 - any connection failure is caller-facing here
        raise PlatformDBValidationError(f"Could not connect to platform_db_url: {e}") from e

    missing = sorted(REQUIRED_TABLES - existing_tables)
    if missing:
        raise PlatformDBValidationError(
            f"platform_db_url is missing required table(s): {', '.join(missing)}. "
            "See docs/REFERENCE/PLATFORM_DB.md for the schema contract."
        )
