"""FastAPI application — HTTP surface for the Pokemon Trade Advisor.

See ROADMAP.md for the phased build-out plan. This module currently covers
Phase 1: app instance, startup lifecycle, and an unauthenticated health check.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@app.get("/health")
async def health() -> dict[str, object]:
    """Unauthenticated liveness/readiness check."""
    return {"status": "ok", "chromadb": is_chromadb_running()}
