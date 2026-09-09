"""FastAPI application — HTTP surface for the Pokemon Trade Advisor.

See ROADMAP.md for the phased build-out plan. This module currently covers
Phase 1: app instance, startup lifecycle, and an unauthenticated health check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from startup import startup
from utils import is_chromadb_running


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the same infrastructure startup the CLI uses, once, at process start.

    Phoenix is off by default here — the API is meant to run unattended (e.g.
    in a container), where startup()'s interactive Phoenix/telemetry prompts
    don't apply. Set ENABLE_PHOENIX=true and re-enable it explicitly once
    Phase 6 wires request tracing through, if you want traces during dev.
    """
    startup(phoenix=False, chromadb=True, telemetry=True, database=True)
    yield


app = FastAPI(title="Pokemon Trade Advisor API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, object]:
    """Unauthenticated liveness/readiness check."""
    return {"status": "ok", "chromadb": is_chromadb_running()}
