"""FastAPI application — HTTP surface for the Pokemon Trade Advisor.

See ROADMAP.md for the phased build-out plan. This module currently covers
Phase 1 (app instance, startup lifecycle, health check), Phase 3 (the
protected router every route mounts onto), Phase 4 (the core trade
endpoints), Phase 5 (offers + query endpoints), and Phase 6 (request
tracing, logging, and error reporting).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import logfire
import sentry_sdk
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response

from agents import query_pokedex
from agents.trade_advisor_api import evaluate_trade, get_pending_offers, get_trade_suggestions, send_trade_offer
from agents.trade_market_analyst import query_market
from api.auth import require_api_key
from api.models import ApiResponse, ChatRequest, EvaluateTradeRequest, QueryRequest, SendOfferRequest
from config import config
from startup import startup
from utils import is_chromadb_running

logger = logging.getLogger(__name__)

# As early as possible, per Sentry's own recommendation — dsn=None (the
# default when SENTRY_DSN isn't set) is documented as a safe no-op, so this
# is fine unconfigured for local dev. Free "Developer" tier: see ROADMAP.md
# Phase 6.
#
# enable_logs=True forwards our existing stdlib `logging` calls (e.g. the
# request-logging middleware below) to Sentry's Logs product too, via the
# same LoggingIntegration that already turns them into error breadcrumbs —
# verified directly in the installed SDK (sentry_sdk/integrations/logging.py)
# rather than assumed. No other code changes needed for this.
sentry_sdk.init(dsn=config.sentry_dsn, enable_logs=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Run the same infrastructure startup the CLI uses, once, at process start.

    Telemetry is off in startup() itself — the API is meant to run unattended
    (e.g. in a container with no TTY), and startup()'s telemetry prompt is an
    interactive CLI flow (`Confirm.ask`) with no place in that context. It's
    now defensively skipped there too when stdin isn't a real terminal (see
    telemetry_start.prompt_and_setup), but the API shouldn't rely on that
    fallback when it can just not ask for something it doesn't use.

    Phase 6's own tracing is opted into separately via ENABLE_PHOENIX — the
    same Phoenix/OTEL pipeline the CLI uses (init_telemetry()), but through
    setup(auto_start_phoenix=False): never auto-starting Phoenix via Docker/
    Colima the way the CLI's interactive startup can. If Phoenix isn't
    already reachable, tracing is silently skipped rather than trying to
    launch infrastructure from an unattended server process.
    """
    startup(phoenix=False, chromadb=True, telemetry=False, database=True)
    if config.enable_phoenix:
        from observability.observability import setup as setup_observability

        setup_observability(auto_start_phoenix=False)
    yield


app = FastAPI(title="Pokemon Trade Advisor API", lifespan=lifespan)

# Uses standard OpenTelemetry FastAPI instrumentation under the hood — its
# spans flow through whichever TracerProvider ends up globally registered
# (by init_telemetry() above, if ENABLE_PHOENIX is set and Phoenix is
# reachable), not a separate Logfire-specific pipeline. Safe to call even
# when tracing is never enabled: spans are just created and go nowhere.
#
# We deliberately never call logfire.configure() — Phoenix (self-hosted, via
# raw OTEL) is the actual backend, not Logfire's own cloud service — which
# makes instrument_fastapi() emit a LogfireNotConfiguredWarning every time.
# Verified this is a false alarm for how this project uses it: reading
# logfire's own source (main.py's instrument_fastapi) confirms the warning
# fires but the real OpenTelemetry instrumentation still runs unconditionally
# right after — only Logfire's own cloud-specific extras are what's "not
# configured". Suppress the noise via Logfire's own documented mechanism.
os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")
logfire.instrument_fastapi(app)


def _handle_agent_error(e: Exception) -> HTTPException:
    """Report an agent-call failure to Sentry, then convert it to a clean 500.

    Every endpoint below catches Exception and converts it to HTTPException,
    which Starlette treats as a normal controlled response, not a crash — it
    never reaches Sentry's automatic exception capture on its own. Without
    this, Sentry would be running but blind to exactly the errors it's meant
    to catch (agent/LLM call failures), only ever seeing genuine unhandled
    crashes elsewhere (e.g. a bug in middleware itself).
    """
    sentry_sdk.capture_exception(e)
    return HTTPException(status_code=500, detail=str(e))


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Write one structured line per request: method, path, status, duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s %d %.0fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


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
        raise _handle_agent_error(e) from e
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
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.get("/trade/suggestions")
async def trade_suggestions(user_id: str = Query(default="user_001")) -> ApiResponse:
    """Proactive trade suggestions based on the caller's collection and goals."""
    try:
        result = await get_trade_suggestions(user_id=user_id)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.get("/offers")
async def offers(user_id: str = Query(default="user_001")) -> ApiResponse:
    """Pending trade offer inbox, each with an AI evaluation."""
    try:
        result = await get_pending_offers(user_id=user_id)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.post("/offers/send")
async def offers_send(request: SendOfferRequest) -> ApiResponse:
    """Propose a trade to another user, pre-screened by the AI."""
    try:
        result = await send_trade_offer(
            sender_id=request.sender_id,
            recipient_id=request.recipient_id,
            offered_pokemon=request.offered_pokemon,
            requested_pokemon=request.requested_pokemon,
        )
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.post("/pokedex/query")
async def pokedex_query(request: QueryRequest) -> ApiResponse:
    """Pokedex knowledge question, personalized against the caller's collection."""
    try:
        result = await query_pokedex(question=request.question, user_id=request.user_id)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.post("/market/query")
async def market_query(request: QueryRequest) -> ApiResponse:
    """Market demand & trend query — no per-user state, user_id is ignored."""
    try:
        result = await query_market(question=request.question)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


app.include_router(protected_router)
