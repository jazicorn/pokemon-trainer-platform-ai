"""Pokemon Trainer's Second Brain - Web API Entry Point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure src/ is importable (so imports like `from agents import ...` work) —
# mirrors app.py's own sys.path setup for the CLI entry point.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    import uvicorn

    # Without this, api.app's request-logging middleware (Phase 6) silently
    # produces no output at all: Python's logging module only prints WARNING
    # and above via its "no handlers configured" fallback, dropping INFO
    # (verified — the middleware's own tests pass regardless, since pytest's
    # caplog installs its own capturing handler that ignores this default).
    #
    # Root stays at WARNING — INFO is only raised for our own logger.
    # Verified live that setting root itself to INFO also surfaces
    # unrelated third-party INFO logging (httpx's own per-request lines),
    # which isn't what this middleware is for.
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("api.app").setLevel(logging.INFO)

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))

    # Import string (not the app object) so uvicorn can still find the app
    # if --reload ever gets added — it needs to re-import the module itself.
    uvicorn.run("api.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
