"""Pydantic models — the canonical data contracts used across the whole system.

Every field here is typed and validated at load time. If the underlying JSON
(or a row from the platform Postgres database) has a malformed timestamp or an
unrecognized status string, Pydantic raises ``ValidationError`` immediately —
the error never propagates silently into an agent.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TradeStatus(StrEnum):
    """Lifecycle status of a platform trade or trade offer."""

    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Trade(BaseModel):
    """A single platform-wide trade record."""

    trade_id: str
    timestamp: datetime
    offered_pokemon: str
    requested_pokemon: str
    status: TradeStatus
    user_a_id: str
    user_b_id: str


class PlatformTrades(BaseModel):
    """Platform-wide trade history — the shape returned by the loader."""

    trades: list[Trade] = Field(default_factory=list)


class OwnedPokemon(BaseModel):
    """A single Pokemon in a user's collection."""

    pokemon_id: str
    nickname: str | None = None
    acquired_date: date
    acquired_via: str  # "trade" | "catch" | "gift" | "evolution"
    tradeable: bool = True
    is_shiny: bool = False
    ball_type: str | None = None  # e.g. "cherish", "master"; None if unknown


class UserPreferences(BaseModel):
    """A user's trading goals and preferences."""

    favorite_types: list[str] = Field(default_factory=list)
    goal: str = ""
    trading_style: str = "balanced"
    never_trade: list[str] = Field(default_factory=list)
    seeking: list[str] = Field(default_factory=list)


class UserTradeHistory(BaseModel):
    """A single completed trade from a user's personal history."""

    trade_id: str
    traded_at: date
    gave: str
    received: str
    satisfied: bool = True


class UserCollection(BaseModel):
    """A single user's Pokemon inventory, preferences, and trade history."""

    user_id: str
    pokemon: list[OwnedPokemon] = Field(default_factory=list)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    trade_history: list[UserTradeHistory] = Field(default_factory=list)
