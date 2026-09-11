"""Optional PostgreSQL client for the sister Pokemon Trainer Platform web API.

Only active when ``PLATFORM_DB_URL`` is set. ``get_platform_db()`` is a
module-level singleton that returns ``None`` silently when the env var is
unset (or the optional ``psycopg`` driver isn't installed, or the connection
fails), so every caller falls back to mock data without any extra logic.

See docs/REFERENCE/PLATFORM_DB.md for the full schema contract and the
fallback-behaviour table this module implements.
"""

from __future__ import annotations

import importlib.util
import os
import warnings
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from data.models import (
    OwnedPokemon,
    PlatformTrades,
    Trade,
    TradeStatus,
    UserCollection,
    UserPreferences,
    UserTradeHistory,
)

# psycopg is an optional dependency (`uv sync --group platform-db`). Checked
# by name rather than imported here so this module still loads cleanly (and
# pyright stays happy) when it isn't installed; the real import happens in
# connect() below, only once we know PLATFORM_DB_URL is actually set.
_PSYCOPG_AVAILABLE = importlib.util.find_spec("psycopg") is not None

if TYPE_CHECKING:
    # TYPE_CHECKING-only — never executed, so this doesn't affect the
    # optional-dependency behaviour above. `from __future__ import
    # annotations` (top of file) makes every annotation a lazy string, so
    # connect()'s return type below can reference these names safely even
    # when psycopg isn't installed at runtime. The ignore comment covers
    # pyright runs that also lack the `platform-db` group synced (CI's own
    # `ci-quality.yml` now syncs it — see that file's own note).
    import psycopg  # pyright: ignore[reportMissingImports]
    from psycopg.rows import DictRow  # pyright: ignore[reportMissingImports]


class PlatformDBClient:
    """Thin wrapper around psycopg3 exposing the same interface as
    ``TradeOffersManager``'s SQLite methods, plus read-only fetchers for the
    platform's own tables.

    This project is read-only for ``trades``, ``user_pokemon``,
    ``user_preferences``, and ``user_trade_history``. ``trade_offers`` is
    shared read-write: the web API inserts offers, this project writes back
    ``status``, ``ai_analysis``, and ``responded_at``.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def connect(self) -> psycopg.Connection[DictRow]:
        """Open a new connection with dict-shaped rows. Caller is responsible for closing it."""
        import psycopg  # pyright: ignore[reportMissingImports]
        from psycopg.rows import dict_row  # pyright: ignore[reportMissingImports]

        # Calling Connection[DictRow].connect(...) directly, rather than the
        # psycopg.connect(...) alias, is required for pyright to bind the
        # Row type parameter to DictRow instead of defaulting it to
        # TupleRow — a known pyright/psycopg stub interaction (psycopg#865),
        # not a runtime distinction; both call the same classmethod.
        return psycopg.Connection[DictRow].connect(self._dsn, row_factory=dict_row)

    def fetch_trades(self, days: int = 90) -> PlatformTrades:
        """Platform-wide trade history from the last ``days`` days."""
        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT trade_id, traded_at, offered_pokemon, requested_pokemon,
                              status, user_a_id, user_b_id
                       FROM trades
                       WHERE traded_at >= NOW() - (%s || ' days')::interval
                       ORDER BY traded_at DESC""",
                    (days,),
                )
                rows = cur.fetchall()
        except Exception as e:  # noqa: BLE001 - any DB failure falls back to empty, not a crash
            warnings.warn(f"platform_db.fetch_trades failed: {e}", stacklevel=2)
            return PlatformTrades(trades=[])

        trades = [
            Trade(
                trade_id=row["trade_id"],
                timestamp=row["traded_at"],
                offered_pokemon=row["offered_pokemon"],
                requested_pokemon=row["requested_pokemon"],
                status=TradeStatus(row["status"]),
                user_a_id=row["user_a_id"],
                user_b_id=row["user_b_id"],
            )
            for row in rows
        ]
        return PlatformTrades(trades=trades)

    def fetch_user_collection(self, user_id: str) -> UserCollection:
        """A user's owned Pokemon, preferences, and trade history."""
        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT pokemon_id, nickname, acquired_date, acquired_via,
                              tradeable, is_shiny, ball_type
                       FROM user_pokemon WHERE user_id = %s""",
                    (user_id,),
                )
                pokemon_rows = cur.fetchall()

                cur.execute(
                    """SELECT favorite_types, goal, trading_style, never_trade, seeking
                       FROM user_preferences WHERE user_id = %s""",
                    (user_id,),
                )
                pref_row = cur.fetchone()

                cur.execute(
                    """SELECT trade_id, traded_at, gave, received, satisfied
                       FROM user_trade_history WHERE user_id = %s""",
                    (user_id,),
                )
                history_rows = cur.fetchall()
        except Exception as e:  # noqa: BLE001 - any DB failure falls back to an empty collection
            warnings.warn(f"platform_db.fetch_user_collection failed: {e}", stacklevel=2)
            return UserCollection(user_id=user_id)

        preferences = (
            UserPreferences(
                favorite_types=list(pref_row["favorite_types"] or []),
                goal=pref_row["goal"] or "",
                trading_style=pref_row["trading_style"] or "balanced",
                never_trade=list(pref_row["never_trade"] or []),
                seeking=list(pref_row["seeking"] or []),
            )
            if pref_row
            else UserPreferences()
        )

        return UserCollection(
            user_id=user_id,
            pokemon=[
                OwnedPokemon(
                    pokemon_id=row["pokemon_id"],
                    nickname=row["nickname"],
                    acquired_date=row["acquired_date"],
                    acquired_via=row["acquired_via"],
                    tradeable=row["tradeable"],
                    is_shiny=row["is_shiny"],
                    ball_type=row["ball_type"],
                )
                for row in pokemon_rows
            ],
            preferences=preferences,
            trade_history=[
                UserTradeHistory(
                    trade_id=row["trade_id"],
                    traded_at=row["traded_at"] if isinstance(row["traded_at"], date) else row["traded_at"].date(),
                    gave=row["gave"],
                    received=row["received"],
                    satisfied=row["satisfied"],
                )
                for row in history_rows
            ],
        )

    def fetch_trade_offers(self, user_id: str) -> list[dict[str, Any]]:
        """Pending offers addressed to ``user_id``."""
        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT id, sender_id, offered_pokemon, requested_pokemon,
                              status, ai_analysis, created_at
                       FROM trade_offers
                       WHERE recipient_id = %s AND status = 'pending'
                       ORDER BY created_at DESC""",
                    (user_id,),
                )
                return list(cur.fetchall())
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"platform_db.fetch_trade_offers failed: {e}", stacklevel=2)
            return []

    def fetch_sent_offers(self, user_id: str) -> list[dict[str, Any]]:
        """All offers sent by ``user_id``, regardless of status."""
        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT id, recipient_id, offered_pokemon, requested_pokemon,
                              status, ai_analysis, created_at, responded_at
                       FROM trade_offers
                       WHERE sender_id = %s
                       ORDER BY created_at DESC""",
                    (user_id,),
                )
                return list(cur.fetchall())
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"platform_db.fetch_sent_offers failed: {e}", stacklevel=2)
            return []

    def update_offer_status(self, offer_id: int, user_id: str, status: str) -> bool:
        """Accept or decline an offer. Returns True if a row was changed."""
        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """UPDATE trade_offers
                       SET status = %s, responded_at = NOW()
                       WHERE id = %s AND recipient_id = %s AND status = 'pending'""",
                    (status, offer_id, user_id),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"platform_db.update_offer_status failed: {e}", stacklevel=2)
            return False

    def save_offer_analysis(self, offer_id: int, analysis: str) -> None:
        """Persist AI evaluation text for an offer."""
        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE trade_offers SET ai_analysis = %s WHERE id = %s",
                    (analysis, offer_id),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"platform_db.save_offer_analysis failed: {e}", stacklevel=2)

    def create_offer(self, sender_id: str, recipient_id: str, offered_pokemon: str, requested_pokemon: str) -> int:
        """Insert a new pending offer and return its ID."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO trade_offers (sender_id, recipient_id, offered_pokemon, requested_pokemon)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (sender_id, recipient_id, offered_pokemon, requested_pokemon),
            )
            row = cur.fetchone()
            conn.commit()
            assert row is not None
            return row["id"]


_platform_db: PlatformDBClient | None = None
_platform_db_checked: bool = False


def get_platform_db() -> PlatformDBClient | None:
    """Return the singleton platform DB client, or None if not configured/available.

    - ``PLATFORM_DB_URL`` unset → returns None silently, no warning.
    - ``psycopg`` not installed → warns once, returns None.
    - Connection fails → warns once, returns None.
    """
    global _platform_db, _platform_db_checked

    if _platform_db_checked:
        return _platform_db

    _platform_db_checked = True

    dsn = os.environ.get("PLATFORM_DB_URL")
    if not dsn:
        return None

    if not _PSYCOPG_AVAILABLE:
        warnings.warn(
            "PLATFORM_DB_URL is set but the 'psycopg' driver is not installed. "
            "Run `uv sync --group platform-db` to enable it. Falling back to mock data.",
            stacklevel=2,
        )
        return None

    client = PlatformDBClient(dsn)
    try:
        with client.connect():
            pass
    except Exception as e:  # noqa: BLE001 - any connection failure falls back to mock data
        warnings.warn(f"Could not connect to PLATFORM_DB_URL: {e}. Falling back to mock data.", stacklevel=2)
        return None

    _platform_db = client
    return _platform_db


@lru_cache(maxsize=128)
def get_platform_db_for(dsn: str) -> PlatformDBClient:
    """Return a cached PlatformDBClient for an explicit DSN.

    The per-request, multi-tenant counterpart to ``get_platform_db()``'s
    single env-var-configured singleton. Used by the HTTP API (Phase 3+),
    which routes each request to *that tenant's own* ``platform_db_url``
    (resolved by ``api.auth.require_api_key``) rather than one process-wide
    database — the CLI's global ``PLATFORM_DB_URL`` singleton above is
    untouched and keeps working exactly as it does today.

    Unlike ``get_platform_db()``, this does not verify connectivity up front
    or fall back to ``None`` on failure: a bad DSN here should surface as a
    real error to that one tenant's request, not silently degrade to shared
    mock data — which would be actively misleading for a paying tenant
    reasoning about their own real collection, unlike the CLI's single-user
    fallback where mock data is a reasonable degraded experience.
    """
    return PlatformDBClient(dsn)
