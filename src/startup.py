"""Startup infrastructure for the Pokemon Trainer Platform - AI."""

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from rich.console import Console as _Console

from config import config
from memory.database import init_database
from observability.telemetry_start import prompt_and_setup as prompt_and_start_telemetry
from utils import is_chromadb_running

_console = _Console(force_terminal=True)

# Map each model provider to its required API key env var.
# None means no key is required (e.g. Ollama running locally).
PROVIDER_ENV_VARS: dict[str, str | None] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "ollama": None,
}


def validate_environment() -> None:
    """Validate that required environment variables are set for the configured model provider.

    Detects 1Password CLI (``op``) and tailors the error message accordingly —
    an empty-string value usually means the shell's ``op read`` integration ran
    but 1Password was not authenticated at the time.

    Raises:
        EnvironmentError: If the required API key env var for the active provider is missing
            or is set to an empty string.
    """
    # Local import so tests that reload the config module see the updated instance.
    from config import config as _config

    provider = _config.get_model().provider.value
    required_var = PROVIDER_ENV_VARS.get(provider)

    # Ollama's direct Cloud API transport (OLLAMA_URL=https://ollama.com) needs
    # an API key — the local daemon and local-proxy-to-cloud transports don't
    # (no auth, and `ollama signin` respectively). This can't be a static
    # per-provider entry in PROVIDER_ENV_VARS like the other providers, since
    # it depends on ollama_url, not just the selected provider.
    if provider == "ollama" and "ollama.com" in _config.ollama_url:
        required_var = "OLLAMA_API_KEY"

    if not required_var:
        return  # Provider needs no API key (e.g. Ollama)

    value = os.environ.get(required_var)
    if value and not value.startswith("op://"):
        return  # Key is present, non-empty, and already resolved — all good

    op_available = shutil.which("op") is not None

    if value and value.startswith("op://"):
        # Env var holds an op:// URI that was never resolved — the command
        # was not run via `op run`. Offer the correct invocation.
        raise OSError(
            f"Environment variable {required_var} contains a 1Password URI,\n"
            f"not an actual key. Run your command via op run so it is resolved:\n"
            f"  op run --env-file .env.op -- uv run python app.py\n"
            f"Or authenticate with the shell approach:\n"
            f"  eval $(op signin) && source ~/.zshrc"
        )
    elif value == "" and op_available:
        # The shell ran `op read ...` but got an empty result — 1Password is
        # probably not signed in, so the variable was exported as an empty string.
        raise OSError(
            f"Environment variable {required_var} is set but empty.\n"
            f"The configured model provider '{provider}' requires this key.\n"
            f"Your 1Password CLI integration may not be authenticated.\n"
            f"\n"
            f"Option A — use the project .env.op file (avoids this issue):\n"
            f"  op run --env-file .env.op -- uv run python app.py\n"
            f"\n"
            f"Option B — sign in and reload your shell:\n"
            f"  eval $(op signin) && source ~/.zshrc"
        )
    elif op_available:
        # op is installed but the variable isn't set at all — the shell
        # integration may not be configured for this key yet.
        raise OSError(
            f"Missing required environment variable: {required_var}\n"
            f"The configured model provider '{provider}' requires this key.\n"
            f"Your 1Password CLI is available. If the key is stored in 1Password,\n"
            f"add this to your ~/.zshrc:\n"
            f'  export {required_var}=$(op read "op://Private/{required_var}/credential")\n'
            f"Then authenticate with: eval $(op signin)"
        )
    else:
        raise OSError(
            f"Missing required environment variable: {required_var}\n"
            f"The configured model provider '{provider}' requires this key.\n"
            f"Set it with: export {required_var}=<your-key>"
        )


def _try_colima_qemu_recovery() -> bool:
    """Recover a broken Colima VZ VM by recreating it with the QEMU driver.

    Safe to call automatically: only VM metadata is deleted.
    Pokemon data lives in the host-mounted chroma_data/ volume and is preserved.
    Returns True if Colima is running afterward.
    """
    if platform.system() != "Darwin" or not shutil.which("colima"):
        return False

    _console.print(
        "\n[yellow]ℹ[/] Colima VZ driver appears to be in a broken state. "
        "Recovering by switching to the QEMU driver "
        "([dim]chroma_data/ volume is preserved[/])..."
    )

    delete = subprocess.run(["colima", "delete"], capture_output=True, text=True)
    if delete.returncode != 0:
        _console.print(f"[red]✗[/] colima delete failed: {delete.stderr.strip()}")
        return False

    start = subprocess.run(
        ["colima", "start", "--vm-type", "qemu"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if start.returncode != 0:
        _console.print(f"[red]✗[/] colima start --vm-type qemu failed: {start.stderr.strip()}")
        return False

    _console.print("[green]✓[/] Colima recovered with QEMU driver.")
    return True


def start_chromadb() -> bool:
    """Start ChromaDB using the shared chromadb_setup script."""
    _console.print("[bold]Starting ChromaDB...[/]")
    repo_root = Path(__file__).parent.parent
    script = repo_root / "chromadb_setup" / "chromadb-docker.sh"

    # stdout: permission prompts the user must see and respond to.
    # stderr: verbose Colima/Lima boot logs — suppress so they don't flood output.
    proc = subprocess.run([str(script), "start"], stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        _console.print(
            "\n[yellow]ChromaDB is required to run this program.[/]\n"
            "Start it with [bold]make chromadb-start[/] and then re-run [bold]make run[/]."
        )
        raise SystemExit(0)

    with _console.status("[bold green]Waiting for ChromaDB to respond...[/]", spinner="dots"):
        for _ in range(20):
            time.sleep(0.5)
            if is_chromadb_running():
                _console.print(f"[green]✓[/] ChromaDB running at {config.chromadb_url}")
                return True

    # Docker/Colima may be in a broken VZ state — attempt one automatic recovery.
    if _try_colima_qemu_recovery():
        _console.print("[bold]Retrying ChromaDB startup after Colima recovery...[/]")
        subprocess.run([str(script), "start"], stderr=subprocess.DEVNULL)
        with _console.status("[bold green]Waiting for ChromaDB to respond...[/]", spinner="dots"):
            for _ in range(20):
                time.sleep(0.5)
                if is_chromadb_running():
                    _console.print(f"[green]✓[/] ChromaDB running at {config.chromadb_url}")
                    return True

    _console.print("[yellow]⚠[/] Warning: ChromaDB may not have started properly")
    return False


def startup(
    phoenix: bool = True,
    chromadb: bool = True,
    telemetry: bool = True,
    database: bool = True,
) -> None:
    """Start all infrastructure and initialize local state for the Pokemon Trade Advisor.

    Args:
        phoenix: Start Phoenix if not running (default: True)
        chromadb: Start ChromaDB if not running (default: True)
        telemetry: Initialize OTEL telemetry (default: True)
        database: Initialize local SQLite database schema (default: True)
    """
    # 0. Validate environment variables before touching any infrastructure
    validate_environment()

    # 1. Initialize local database schema
    if database:
        _console.print("Initializing local database...")
        init_database()

    # 2. Setup observability (Phoenix + telemetry)
    if phoenix or telemetry:
        prompt_and_start_telemetry(auto_start_phoenix=phoenix)

    # 3. Start ChromaDB
    if chromadb:
        if is_chromadb_running():
            _console.print(f"ChromaDB already running at {config.chromadb_url}")
        else:
            start_chromadb()
