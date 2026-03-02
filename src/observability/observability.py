"""Observability setup for the capstone project."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from rich.console import Console as _Console
from rich.prompt import Confirm

# Add repo root to path for shared telemetry_setup
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from telemetry_setup import init_telemetry  # noqa: E402

from config import config  # noqa: E402

PHOENIX_CONTAINER = "phoenix-capstone"

_console = _Console(force_terminal=True)


def is_phoenix_running() -> bool:
    """Check if Phoenix server is running."""
    try:
        response = httpx.get(config.phoenix_url, timeout=2.0)
        return response.status_code == 200
    except httpx.RequestError:
        return False


def _is_docker_running() -> bool:
    """Return True if the Docker daemon is reachable."""
    return subprocess.run(
        ["docker", "info"],
        capture_output=True,
    ).returncode == 0


def _start_colima() -> bool:
    """Prompt the user to start Colima and do so if they agree.

    Returns True if Docker is reachable afterward, False otherwise.
    """
    if not shutil.which("colima"):
        _console.print(
            "[yellow]⚠[/] Colima is not installed. "
            "Install it with [dim]brew install colima[/] to use Docker."
        )
        return False

    if not Confirm.ask(
        "\nDocker is not running. Start Colima now?", default=False
    ):
        _console.print(
            "[yellow]⚠[/] Skipping Phoenix startup. "
            "Run [dim]make phoenix-start[/] after starting Colima."
        )
        return False

    with _console.status("[bold green]Starting Colima...[/]", spinner="dots"):
        proc = subprocess.run(
            ["colima", "start"],
            capture_output=True,
            text=True,
        )

    if proc.returncode != 0:
        _console.print(f"[red]✗[/] colima start failed: {proc.stderr.strip()}")
        return False

    _console.print("[green]✓[/] Colima started.")
    return _is_docker_running()


def start_phoenix_docker() -> bool:
    """Start Phoenix server via Docker."""
    if not _is_docker_running():
        if not _start_colima():
            return False

    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={PHOENIX_CONTAINER}",
         "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )

    if PHOENIX_CONTAINER in result.stdout:
        _console.print("Starting existing Phoenix container...")
        proc = subprocess.run(
            ["docker", "start", PHOENIX_CONTAINER],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            _console.print(f"[red]✗[/] docker start failed: {proc.stderr.strip()}")
            return False
    else:
        _console.print("[bold]Starting Phoenix in Docker...[/]")
        proc = subprocess.run([
            "docker", "run", "-d",
            "--name", PHOENIX_CONTAINER,
            "-p", "6006:6006",
            "arizephoenix/phoenix:latest",
        ], capture_output=True, text=True)
        if proc.returncode != 0:
            _console.print(f"[red]✗[/] docker run failed: {proc.stderr.strip()}")
            return False

    with _console.status(
        "[bold green]Waiting for Phoenix to respond...[/]", spinner="dots"
    ):
        for _ in range(60):
            time.sleep(0.5)
            if is_phoenix_running():
                _console.print(f"[green]✓[/] Phoenix running at {config.phoenix_url}")
                return True

    _console.print("[yellow]⚠[/] Warning: Phoenix may not have started properly")
    return False


def setup(auto_start_phoenix: bool = True) -> None:
    """Initialize observability for the Pokemon Trade Advisor.

    Args:
        auto_start_phoenix: Start Phoenix if not running (default: True)
    """
    if is_phoenix_running():
        _console.print(f"Phoenix already running at {config.phoenix_url}")
    elif auto_start_phoenix:
        start_phoenix_docker()

    # Only register the OTLP exporter when Phoenix is actually reachable.
    # If we wire it up while Phoenix is down, every agent span fires a connection
    # error and floods the terminal with tracebacks.
    if is_phoenix_running():
        init_telemetry(project_name=config.project_name)
    else:
        _console.print("[yellow]Skipping telemetry — Phoenix is not running[/]")
    