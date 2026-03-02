"""Trade Advisor Agent — public facade.

Implementation is split across three modules:
  - trade_advisor_core.py   — AdvisorDependencies, SYSTEM_PROMPT, agent instance
  - trade_advisor_tools.py  — @trade_advisor.tool implementations
  - trade_advisor_api.py    — public async entry points

Import from this module for full backward compatibility.
"""

from __future__ import annotations

from .trade_advisor_core import AdvisorDependencies, SYSTEM_PROMPT, trade_advisor
from .trade_advisor_api import (
    _build_advisor_deps,
    evaluate_trade,
    get_pending_offers,
    get_trade_suggestions,
    send_trade_offer,
)

# Re-export tool functions so agents/__init__.py can import them directly.
from .trade_advisor_tools import get_pokemon_info, get_market_data

__all__ = [
    "AdvisorDependencies",
    "SYSTEM_PROMPT",
    "trade_advisor",
    "_build_advisor_deps",
    "evaluate_trade",
    "get_trade_suggestions",
    "get_pending_offers",
    "send_trade_offer",
    "get_pokemon_info",
    "get_market_data",
]
