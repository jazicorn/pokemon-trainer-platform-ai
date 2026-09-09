"""Pokemon Trainer's Second Brain - Web API Entry Point."""

from __future__ import annotations

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

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))

    # Import string (not the app object) so uvicorn can still find the app
    # if --reload ever gets added — it needs to re-import the module itself.
    uvicorn.run("api.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
