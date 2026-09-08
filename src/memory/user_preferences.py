"""Manage user preferences in persistent storage."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .database import get_connection


class UserPreferencesManager:
    """Manage persistent user preferences."""

    def __init__(self, user_id: str):
        """Initialize for a specific user."""
        self.user_id = user_id

    def save_preferences(
        self,
        favorite_types: list[str] | None = None,
        goal: str | None = None,
        trading_style: str | None = None,
        never_trade: list[str] | None = None,
        seeking: list[str] | None = None,
    ) -> None:
        """Save or update user preferences."""
        existing = self.get_preferences()

        data: dict[str, Any] = {
            "favorite_types": favorite_types if favorite_types is not None else existing.get("favorite_types", []),
            "goal": goal if goal is not None else existing.get("goal", ""),
            "trading_style": trading_style if trading_style is not None else existing.get("trading_style", "balanced"),
            "never_trade": never_trade if never_trade is not None else existing.get("never_trade", []),
            "seeking": seeking if seeking is not None else existing.get("seeking", []),
        }

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO user_preferences
                (user_id, favorite_types, goal, trading_style, never_trade,
                 seeking, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.user_id,
                    json.dumps(data["favorite_types"]),
                    data["goal"],
                    data["trading_style"],
                    json.dumps(data["never_trade"]),
                    json.dumps(data["seeking"]),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    def get_preferences(self) -> dict[str, Any]:
        """Get user preferences."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?",
                (self.user_id,),
            )
            row = cursor.fetchone()

        if not row:
            return {}

        return {
            "favorite_types": json.loads(row["favorite_types"] or "[]"),
            "goal": row["goal"],
            "trading_style": row["trading_style"],
            "never_trade": json.loads(row["never_trade"] or "[]"),
            "seeking": json.loads(row["seeking"] or "[]"),
        }

    def update_seeking(self, pokemon: str, add: bool = True) -> None:
        """Add or remove a Pokemon from the seeking list."""
        prefs = self.get_preferences()
        seeking = set(prefs.get("seeking", []))

        if add:
            seeking.add(pokemon)
        else:
            seeking.discard(pokemon)

        self.save_preferences(seeking=list(seeking))

    def update_never_trade(self, pokemon: str, add: bool = True) -> None:
        """Add or remove a Pokemon from the never-trade list."""
        prefs = self.get_preferences()
        never_trade = set(prefs.get("never_trade", []))

        if add:
            never_trade.add(pokemon)
        else:
            never_trade.discard(pokemon)

        self.save_preferences(never_trade=list(never_trade))
