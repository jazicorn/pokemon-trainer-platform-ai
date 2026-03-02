"""Optional telemetry startup with user prompt."""

from rich.console import Console
from rich.prompt import Confirm

from observability.observability import is_phoenix_running, setup
from config import config

_console: Console = Console(force_terminal=True)


def prompt_and_setup(auto_start_phoenix: bool = True) -> bool:
    """Ask the user whether to enable telemetry, then start it if confirmed.

    If Phoenix is already running the prompt is skipped and telemetry starts
    automatically — avoids interrupting users who deliberately started it.

    Args:
        auto_start_phoenix: Passed through to observability.setup().

    Returns:
        True if telemetry was started, False if skipped.
    """
    if is_phoenix_running():
        # Already up — wire OTEL without asking
        setup(auto_start_phoenix=False)
        return True

    enabled = Confirm.ask(
        "[bold cyan]Enable telemetry?[/] "
        f"(Phoenix tracing at [dim]{config.phoenix_url}[/])",
        default=False,
    )

    if not enabled:
        _console.print("[dim]Telemetry skipped.[/]")
        return False

    setup(auto_start_phoenix=auto_start_phoenix)
    return True
