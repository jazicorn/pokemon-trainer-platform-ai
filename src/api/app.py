"""FastAPI application — HTTP surface for the Pokemon Trade Advisor.

See ROADMAP.md for the phased build-out plan.
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
from api.paths import CHAT, HEALTH, MARKET_QUERY, OFFERS, OFFERS_SEND, POKEDEX_QUERY, TRADE_EVALUATE, TRADE_SUGGESTIONS
from config import config
from startup import startup
from utils import is_vector_store_running

logger = logging.getLogger(__name__)

# dsn=None (SENTRY_DSN unset) is a documented safe no-op, so this is fine for
# local dev. enable_logs=True also forwards stdlib `logging` calls to Sentry's
# Logs product via the same LoggingIntegration.
sentry_sdk.init(dsn=config.sentry_dsn, enable_logs=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Run the same infrastructure startup the CLI uses, once, at process start.

    telemetry=False: startup()'s telemetry prompt is an interactive CLI flow
    with no place in an unattended API process. chromadb=False: start_chromadb()
    shells out to `docker run` and exits the process on failure, which can't
    work in a container with no Docker daemon (e.g. a Fly Machine); /health's
    is_vector_store_running() reports reachability for whichever backend is
    actually active instead. Tracing is opted into separately via
    ENABLE_PHOENIX, through setup(auto_start_phoenix=False) so it never tries
    to launch Phoenix itself — just skips tracing if it isn't already reachable.
    """
    startup(phoenix=False, chromadb=False, telemetry=False, database=True)
    if config.enable_phoenix:
        from observability.observability import setup as setup_observability

        setup_observability(auto_start_phoenix=False)
    yield


app = FastAPI(title="Pokemon Trade Advisor API", lifespan=lifespan)

# Fly's edge does no rate limiting of its own. Keyed by client IP so it also
# covers /health and unauthenticated routes, not just protected ones.
# storage_uri: redis:// in production (a shared, redeploy-durable counter);
# defaults to slowapi's in-memory counter locally. in_memory_fallback_enabled
# is deliberate (not the library default) so a Redis outage just skips
# limiting instead of 500ing every request.
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

# Uses standard OpenTelemetry FastAPI instrumentation — spans flow through
# whichever TracerProvider is globally registered (Phoenix, if ENABLE_PHOENIX
# is set), not a Logfire-specific pipeline. Safe to call even when tracing is
# never enabled. We never call logfire.configure() (Phoenix is the real
# backend), which would otherwise make this emit a harmless
# LogfireNotConfiguredWarning every time — suppressed below.
os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")
logfire.instrument_fastapi(app)


def _handle_agent_error(e: Exception) -> HTTPException:
    """Report an agent-call failure to Sentry, then convert it to a clean 500.

    HTTPException is a controlled response, not a crash, so it never reaches
    Sentry's automatic capture on its own — this fills that gap.
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
    """Set standard security-related HTTP response headers.

    App-level, not reverse-proxy config: Fly gives no proxy layer of our own.
    The Server: uvicorn header is dropped separately in api_server.py
    (server_header=False), since it's set before middleware sees the response.
    """
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# Every route below mounts here, not on `app` directly, so it requires a
# valid X-API-Key. Their paths (imported from api.paths) already include the
# version prefix. /health is the exception, staying on `app` itself.
protected_router = APIRouter(dependencies=[Depends(require_api_key)])


@app.get(HEALTH)
async def health() -> dict[str, object]:
    """Unauthenticated liveness/readiness check."""
    return {"status": "ok", "chromadb": is_vector_store_running()}


@protected_router.post(CHAT)
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


@protected_router.post(TRADE_EVALUATE)
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


@protected_router.get(TRADE_SUGGESTIONS)
async def trade_suggestions(user_id: str = Query(default="user_001")) -> ApiResponse:
    """Proactive trade suggestions based on the caller's collection and goals."""
    try:
        result = await get_trade_suggestions(user_id=user_id)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.get(OFFERS)
async def offers(user_id: str = Query(default="user_001")) -> ApiResponse:
    """Pending trade offer inbox, each with an AI evaluation."""
    try:
        result = await get_pending_offers(user_id=user_id)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.post(OFFERS_SEND)
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


@protected_router.post(POKEDEX_QUERY)
async def pokedex_query(request: QueryRequest) -> ApiResponse:
    """Pokedex knowledge question, personalized against the caller's collection."""
    try:
        result = await query_pokedex(question=request.question, user_id=request.user_id)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


@protected_router.post(MARKET_QUERY)
async def market_query(request: QueryRequest) -> ApiResponse:
    """Market demand & trend query — no per-user state, user_id is ignored."""
    try:
        result = await query_market(question=request.question)
    except Exception as e:
        raise _handle_agent_error(e) from e
    return ApiResponse(result=result)


app.include_router(protected_router)
