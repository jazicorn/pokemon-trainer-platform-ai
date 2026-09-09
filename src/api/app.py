"""FastAPI application — HTTP surface for the Pokemon Trade Advisor.

See ROADMAP.md for the phased build-out plan. This module currently covers
Phase 1 (app instance, startup lifecycle, health check), Phase 3 (the
protected router every route mounts onto), and Phase 4 (the core trade
endpoints).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query

from agents.trade_advisor_api import evaluate_trade, get_trade_suggestions
from api.auth import require_api_key
from api.models import ApiResponse, ChatRequest, EvaluateTradeRequest
from startup import startup
from utils import is_chromadb_running


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Run the same infrastructure startup the CLI uses, once, at process start.

    Both phoenix and telemetry are off here — the API is meant to run
    unattended (e.g. in a container with no TTY), and startup()'s telemetry
    prompt is an interactive CLI flow (`Confirm.ask`) with no place in that
    context. It's now defensively skipped there too when stdin isn't a real
    terminal (see telemetry_start.prompt_and_setup), but the API shouldn't
    rely on that fallback when it can just not ask for something it doesn't
    use yet — Phase 6 wires the API's own real request tracing through
    Logfire directly, superseding this CLI-oriented flow entirely.
    """
    startup(phoenix=False, chromadb=True, telemetry=False, database=True)
    yield


app = FastAPI(title="Pokemon Trade Advisor API", lifespan=lifespan)

# Every route Phase 4/5 add mounts onto this router, not `app` directly, so
# they automatically require a valid X-API-Key — `/health` is the one route
# that stays on `app` itself, deliberately outside this dependency.
protected_router = APIRouter(dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health() -> dict[str, object]:
    """Unauthenticated liveness/readiness check."""
    return {"status": "ok", "chromadb": is_chromadb_running()}


@protected_router.post("/chat")
async def chat(request: ChatRequest) -> ApiResponse:
    """Free-text natural language agent query."""
    try:
        result = await evaluate_trade(
            raw_query=request.message,
            user_id=request.user_id,
            conversation_context=request.conversation_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ApiResponse(result=result)


@protected_router.post("/trade/evaluate")
async def trade_evaluate(request: EvaluateTradeRequest) -> ApiResponse:
    """Structured trade evaluation: named offered/requested Pokemon."""
    try:
        result = await evaluate_trade(
            offered_pokemon=request.offered_pokemon,
            requested_pokemon=request.requested_pokemon,
            user_id=request.user_id,
            conversation_context=request.conversation_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ApiResponse(result=result)


@protected_router.get("/trade/suggestions")
async def trade_suggestions(user_id: str = Query(default="user_001")) -> ApiResponse:
    """Proactive trade suggestions based on the caller's collection and goals."""
    try:
        result = await get_trade_suggestions(user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ApiResponse(result=result)


app.include_router(protected_router)
