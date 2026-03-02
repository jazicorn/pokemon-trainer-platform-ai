"""Middleware for applying guardrails to agent interactions."""

from __future__ import annotations

from dataclasses import dataclass

from .pii_filter import filter_pii, get_pii_report, has_pii


@dataclass
class ProcessedInput:
    """Result of processing user input."""

    text: str
    had_pii: bool
    warning: str


class GuardrailMiddleware:
    """Apply guardrails before and after agent processing."""

    def __init__(
        self,
        filter_input: bool = True,
        filter_output: bool = False,
    ) -> None:
        """Initialize middleware settings."""
        self.filter_input = filter_input
        self.filter_output = filter_output

    def process_input(self, text: str) -> tuple[str, dict]:
        """Process user input before sending to agent.

        Returns:
            Tuple of (filtered_text, pii_report)
        """
        if not self.filter_input:
            return text, {}

        if not has_pii(text):
            return text, {}

        report = get_pii_report(text)
        filtered = filter_pii(text)
        return filtered, report

    def process_output(self, text: str) -> str:
        """Process agent output before returning to user."""
        if self.filter_output:
            return filter_pii(text)
        return text


def create_safe_input(user_input: str) -> ProcessedInput:
    """Create a safe version of user input.

    Returns:
        ProcessedInput with filtered text and metadata.
    """
    if not has_pii(user_input):
        return ProcessedInput(text=user_input, had_pii=False, warning="")

    safe_input = filter_pii(user_input)
    warning = (
        "Note: Some personal information was detected and filtered "
        "for your privacy."
    )

    return ProcessedInput(text=safe_input, had_pii=True, warning=warning)
