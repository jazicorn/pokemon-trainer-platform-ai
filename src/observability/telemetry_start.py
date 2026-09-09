"""Optional telemetry startup with user prompt."""

import sys

from rich.console import Console
from rich.prompt import Confirm

from config import config
from observability.observability import is_phoenix_running, setup

_console: Console = Console(force_terminal=True)


def prompt_and_setup(auto_start_phoenix: bool = True) -> bool:
    """Ask the user whether to enable telemetry, then start it if confirmed.

    If Phoenix is already running the prompt is skipped and telemetry starts
    automatically — avoids interrupting users who deliberately started it.

    Also skipped (defaulting to disabled, matching the prompt's own
    ``default=False``) when stdin isn't a real terminal — e.g. a container
    with no TTY, CI, or a service manager. `Confirm.ask` has no such check
    on its own and would otherwise block on `input()` forever waiting for a
    human who's never there to answer.

    Args:
        auto_start_phoenix: Passed through to observability.setup().

    Returns:
        True if telemetry was started, False if skipped.
    """
    if is_phoenix_running():
        # Already up — wire OTEL without asking
        setup(auto_start_phoenix=False)
        return True

    if not sys.stdin.isatty():
        _console.print("[dim]Telemetry skipped (non-interactive).[/]")
        return False

    enabled = Confirm.ask(
        f"[bold cyan]Enable telemetry?[/] (Phoenix tracing at [dim]{config.phoenix_url}[/])",
        default=False,
    )

    if not enabled:
        _console.print("[dim]Telemetry skipped.[/]")
        return False

    setup(auto_start_phoenix=auto_start_phoenix)
    return True
