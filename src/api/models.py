"""Request/response Pydantic models for the HTTP API.

Defined up front, before any routes are wired (ROADMAP.md Phase 2), so every
handler's contract is typed and validated at the boundary — a malformed
request body is rejected by FastAPI/Pydantic before it ever reaches agent
code, the same principle `data/models.py` applies to the CLI's own data.
"""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Body for `POST /chat` — free-text natural language agent query."""

    message: str
    user_id: str = "user_001"
    conversation_context: str | None = None


class EvaluateTradeRequest(BaseModel):
    """Body for `POST /trade/evaluate` — structured trade evaluation."""

    offered_pokemon: str
    requested_pokemon: str
    user_id: str = "user_001"
    conversation_context: str | None = None


class SendOfferRequest(BaseModel):
    """Body for `POST /offers/send` — propose a trade to another user."""

    sender_id: str
    recipient_id: str
    offered_pokemon: str
    requested_pokemon: str


class QueryRequest(BaseModel):
    """Body for `POST /pokedex/query` and `POST /market/query`.

    `user_id` is used by the Pokedex query (personalizes against the
    caller's collection) but ignored by the Market query, which has no
    per-user state — see `agents.trade_market_analyst.query_market`.
    """

    question: str
    user_id: str = "user_001"


class ApiResponse(BaseModel):
    """Common response envelope for every agent-backed endpoint."""

    result: str
    status: str = "ok"
