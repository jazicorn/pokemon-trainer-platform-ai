"""Pokemon Trainer's Second Brain - Main Entry Point."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure src/ is importable (so imports like `from agents import ...` work)
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    print("Pokemon Trainer's Second Brain", flush=True)
    print("=" * 40, flush=True)
    print("Starting infrastructure...", flush=True)

    # Import after sys.path update
    from startup import startup

    startup()

    print("Starting CLI...", flush=True)

    # Import after sys.path update
    from cli.app import main as cli_main

    asyncio.run(cli_main())


if __name__ == "__main__":
    main()
