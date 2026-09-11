"""Local admin web UI — entry point (ROADMAP.md Phase 16).

Operator-only tenant management dashboard. Binds to 127.0.0.1 by default,
unlike api_server.py's 0.0.0.0 — this surface is never meant to be reachable
from another machine directly; see src/admin/app.py's own module docstring.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is importable — mirrors app.py's/api_server.py's own sys.path setup.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    import uvicorn

    host = os.getenv("ADMIN_HOST", "127.0.0.1")
    port = int(os.getenv("ADMIN_PORT", "8090"))

    uvicorn.run("admin.app:app", host=host, port=port, server_header=False)


if __name__ == "__main__":
    main()
