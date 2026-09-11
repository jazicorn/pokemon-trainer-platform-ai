"""FastAPI application — HTTP surface for the Pokemon Trade Advisor.

See ROADMAP.md for the phased build-out plan. This module currently covers
Phase 1 (app instance, startup lifecycle, health check), Phase 3 (the
protected router every route mounts onto), Phase 4 (request tracing,
logging, and error reporting), Phase 5 (the core trade endpoints), and
Phase 6 (offers + query endpoints).
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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from agents import query_pokedex
from agents.trade_advisor_api import evaluate_trade, get_pending_offers, get_trade_suggestions, send_trade_offer
from agents.trade_market_analyst import query_market
from api.auth import require_api_key
from api.models import ApiResponse, ChatRequest, EvaluateTradeRequest, QueryRequest, SendOfferRequest
from config import config
from startup import startup
from utils import is_vector_store_running

logger = logging.getLogger(__name__)

# As early as possible, per Sentry's own recommendation — dsn=None (the
# default when SENTRY_DSN isn't set) is documented as a safe no-op, so this
# is fine unconfigured for local dev. Free "Developer" tier: see ROADMAP.md
# Phase 4.
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

    Phase 4's own tracing is opted into separately via ENABLE_PHOENIX — the
    same Phoenix/OTEL pipeline the CLI uses (init_telemetry()), but through
    setup(auto_start_phoenix=False): never auto-starting Phoenix via Docker/
    Colima the way the CLI's interactive startup can. If Phoenix isn't
    already reachable, tracing is silently skipped rather than trying to
    launch infrastructure from an unattended server process.

    chromadb=False for the same reason: start_chromadb() shells out to
    `docker run` when ChromaDB isn't already reachable, which has no chance
    of working in a container with no Docker daemon of its own (e.g. a Fly
    Machine) — and a failed start there calls `raise SystemExit(0)`, killing
    this whole process before it serves a single request. /health's own
    is_vector_store_running() check already reports reachability truthfully
    for whichever backend is actually active (self-hosted ChromaDB or
    Chroma Cloud — see ROADMAP.md Phase 14); production ChromaDB,
    when used, is a separately deployed, already-running service.
    """
    startup(phoenix=False, chromadb=False, telemetry=False, database=True)
    if config.enable_phoenix:
        from observability.observability import setup as setup_observability

        setup_observability(auto_start_phoenix=False)
    yield


app = FastAPI(title="Pokemon Trade Advisor API", lifespan=lifespan)

# Rate limiting (Phase 14 security checklist) — required regardless of host:
# Fly's edge is a load balancer, not a WAF, so it does no rate limiting of
# its own. Keyed by client IP so it also covers /health and Phase 15's
# future no-key registration endpoint, not just authenticated routes.
# default_limits applies to every route automatically — no per-endpoint
# decorator needed.
#
# storage_uri=None (rate_limit_storage_uri unset) falls back to slowapi's
# default in-memory counter, correct for local dev. In production this
# should be a redis://, e.g. Upstash — a shared counter across however many
# instances are running, and one that survives a redeploy (an in-memory
# counter doesn't). in_memory_fallback_enabled=True is deliberate, not the
# library default: without it, a Redis outage makes every single rate-limit
# check raise, which would 500 the whole API rather than just skip limiting
# during the outage — verified by reading slowapi's own source
# (_check_request_limit's fallback branch only triggers when this is set).
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=config.rate_limit_storage_uri,
    in_memory_fallback_enabled=True,
)
app.state.limiter = limiter
# slowapi's handler is typed for RateLimitExceeded specifically, narrower than
# add_exception_handler's own Exception-based signature — Starlette dispatches by the exact
# type registered here, so this is safe at runtime despite the static mismatch.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
app.add_middleware(SlowAPIMiddleware)

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


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Set the Phase 14 security checklist's HTTP response headers.

    App-level, not reverse-proxy config: Fly gives no proxy layer of our own
    to configure, so these have to live here regardless. The Server: uvicorn
    header is dropped separately, in api_server.py (uvicorn.run's own
    server_header=False), since it's set before any middleware sees the
    response.
    """
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# Every route Phase 5/6 add mounts onto this router, not `app` directly, so
# they automatically require a valid X-API-Key — `/health` is the one route
# that stays on `app` itself, deliberately outside this dependency.
protected_router = APIRouter(dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health() -> dict[str, object]:
    """Unauthenticated liveness/readiness check."""
    return {"status": "ok", "chromadb": is_vector_store_running()}


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
