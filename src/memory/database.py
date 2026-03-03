"""SQLite database for persistent memory."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from utils import is_chromadb_running

DB_NAME = "memory.db"


def get_db_path() -> Path:
    """Get the database file path."""
    db_dir = Path(__file__).parent.parent.parent / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / DB_NAME


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Get a database connection as context manager."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def ensure_services(chromadb: bool = True, phoenix: bool = False) -> None:
    """Ensure required services are running.

    Uses startup.py to start services if needed.

    Args:
        chromadb: Ensure ChromaDB is running (default: True)
        phoenix: Ensure Phoenix is running (default: False)
    """
    from startup import startup

    startup(phoenix=phoenix, chromadb=chromadb, telemetry=False)


def init_database() -> None:
    """Initialize the database schema."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                favorite_types TEXT,
                goal TEXT,
                trading_style TEXT,
                never_trade TEXT,
                seeking TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                offered_pokemon TEXT NOT NULL,
                requested_pokemon TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                reasoning TEXT,
                user_followed INTEGER,
                user_feedback TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                preference_type TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                offered_pokemon TEXT NOT NULL,
                requested_pokemon TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                ai_analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                responded_at TIMESTAMP
            )
        """)

        conn.commit()


# Fixed mock offers seeded on first inbox view
_MOCK_OFFERS: list[tuple[str, str, str]] = [
    ("user_002", "charizard", "pikachu"),
    ("user_003", "gengar", "eevee"),
    ("user_002", "snorlax", "mewtwo"),
    ("user_004", "lapras", "alakazam"),
    ("user_003", "dragonite", "magikarp"),
]


class TradeOffersManager:
    """Manages persistent trade offers in SQLite."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        init_database()

    def seed_offers(self) -> None:
        """Populate the inbox for this user.

        When ``PLATFORM_DB_URL`` is configured the trade offers live in
        PostgreSQL (the shared source of truth), so no local seeding is needed.
        Falls back to fixed mock data otherwise.
        """
        from data.platform_db import get_platform_db

        if get_platform_db() is not None:
            return  # PostgreSQL is the source of truth — nothing to seed locally

        self._seed_mock_offers()

    def _seed_mock_offers(self) -> None:
        """Seed demo incoming offers the first time a user views their inbox."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM trade_offers WHERE recipient_id = ?",
                (self.user_id,),
            )
            if cursor.fetchone()[0] > 0:
                # Clear stale AI analyses so they are re-evaluated with correct perspective
                cursor.execute(
                    "UPDATE trade_offers SET ai_analysis = NULL WHERE recipient_id = ?",
                    (self.user_id,),
                )
                conn.commit()
                return
            cursor.executemany(
                """INSERT INTO trade_offers
                   (sender_id, recipient_id, offered_pokemon, requested_pokemon)
                   VALUES (?, ?, ?, ?)""",
                [
                    (sender, self.user_id, offered, requested)
                    for sender, offered, requested in _MOCK_OFFERS
                ],
            )
            conn.commit()

    def create_offer(
        self,
        recipient_id: str,
        offered_pokemon: str,
        requested_pokemon: str,
    ) -> int:
        """Insert a new pending offer and return its ID."""
        from data.platform_db import get_platform_db

        db = get_platform_db()
        if db is not None:
            return db.create_offer(
                self.user_id, recipient_id, offered_pokemon, requested_pokemon
            )

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO trade_offers
                   (sender_id, recipient_id, offered_pokemon, requested_pokemon)
                   VALUES (?, ?, ?, ?)""",
                (self.user_id, recipient_id, offered_pokemon, requested_pokemon),
            )
            conn.commit()
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def get_inbox(self) -> list[dict[str, Any]]:
        """Return pending offers addressed to this user."""
        from data.platform_db import get_platform_db

        db = get_platform_db()
        if db is not None:
            return db.fetch_trade_offers(self.user_id)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sender_id, offered_pokemon, requested_pokemon,
                          status, ai_analysis, created_at
                   FROM trade_offers
                   WHERE recipient_id = ? AND status = 'pending'
                   ORDER BY created_at DESC""",
                (self.user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_sent(self) -> list[dict[str, Any]]:
        """Return all offers sent by this user."""
        from data.platform_db import get_platform_db

        db = get_platform_db()
        if db is not None:
            return db.fetch_sent_offers(self.user_id)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, recipient_id, offered_pokemon, requested_pokemon,
                          status, ai_analysis, created_at, responded_at
                   FROM trade_offers
                   WHERE sender_id = ?
                   ORDER BY created_at DESC""",
                (self.user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_status(self, offer_id: int, status: str) -> bool:
        """Set offer status to accepted or declined. Returns True if a row was updated."""
        from data.platform_db import get_platform_db

        db = get_platform_db()
        if db is not None:
            return db.update_offer_status(offer_id, self.user_id, status)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE trade_offers
                   SET status = ?, responded_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND recipient_id = ? AND status = 'pending'""",
                (status, offer_id, self.user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_ai_analysis(self, offer_id: int, analysis: str) -> None:
        """Persist AI evaluation text for an offer."""
        from data.platform_db import get_platform_db

        db = get_platform_db()
        if db is not None:
            db.save_offer_analysis(offer_id, analysis)
            return

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE trade_offers SET ai_analysis = ? WHERE id = ?",
                (analysis, offer_id),
            )
            conn.commit()
