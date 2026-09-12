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


class RegisterRequest(BaseModel):
    """Body for `POST /accounts/register` — self-serve tenant signup.

    `use_managed_db` defaults `True` (ROADMAP_PLATFORM.md Phase 17) —
    bringing your own database is the opt-out, provisioning one
    automatically is the default. `platform_db_url` is required only when
    `use_managed_db=False`; ignored otherwise. `terms_accepted` must be
    `true` for a managed-DB signup — explicit disclosure that the tenant's
    data will live on infrastructure you control, not just a technical
    default (see `config.terms_url`).
    """

    name: str
    platform_db_url: str | None = None
    use_managed_db: bool = True
    analytics_opt_in: bool | None = None
    terms_accepted: bool = False


class ApiKeyResponse(BaseModel):
    """A newly issued or rotated API key — shown exactly once, never again."""

    tenant_id: str
    api_key: str


class RegisterResponse(ApiKeyResponse):
    """`POST /accounts/register`'s response — an ApiKeyResponse plus which
    hosting path this tenant ended up on.
    """

    database: str  # "managed" | "self_hosted"
