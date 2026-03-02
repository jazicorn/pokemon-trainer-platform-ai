"""Observability setup for the capstone project."""

import subprocess
import sys
import time
from pathlib import Path

import httpx

# Add repo root to path for shared telemetry_setup
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from telemetry_setup import init_telemetry  # noqa: E402

from config import config  # noqa: E402

PHOENIX_CONTAINER = "phoenix-capstone"


def is_phoenix_running() -> bool:
    """Check if Phoenix server is running."""
    try:
        response = httpx.get(config.phoenix_url, timeout=2.0)
        return response.status_code == 200
    except httpx.RequestError:
        return False


def start_phoenix_docker() -> bool:
    """Start Phoenix server via Docker."""
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={PHOENIX_CONTAINER}",
         "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )

    if PHOENIX_CONTAINER in result.stdout:
        print("Starting existing Phoenix container...")
        subprocess.run(["docker", "start", PHOENIX_CONTAINER],
                       capture_output=True)
    else:
        print("Starting Phoenix in Docker...")
        subprocess.run([
            "docker", "run", "-d",
            "--name", PHOENIX_CONTAINER,
            "-p", "6006:6006",
            "arizephoenix/phoenix:latest",
        ], capture_output=True)

    for _ in range(20):
        time.sleep(0.5)
        if is_phoenix_running():
            print(f"Phoenix running at {config.phoenix_url}")
            return True

    print("Warning: Phoenix may not have started properly")
    return False


def setup(auto_start_phoenix: bool = True) -> None:
    """Initialize observability for the Pokemon Trade Advisor.

    Args:
        auto_start_phoenix: Start Phoenix if not running (default: True)
    """
    if is_phoenix_running():
        print(f"Phoenix already running at {config.phoenix_url}")
    elif auto_start_phoenix:
        start_phoenix_docker()

    # Only register the OTLP exporter when Phoenix is actually reachable.
    # If we wire it up while Phoenix is down, every agent span fires a connection
    # error and floods the terminal with tracebacks.
    if is_phoenix_running():
        init_telemetry(project_name=config.project_name)
    else:
        print("Skipping telemetry — Phoenix is not running")
    