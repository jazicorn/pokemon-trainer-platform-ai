"""Command parsing for CLI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple


class CommandType(Enum):
    """Types of CLI commands."""

    TRADE = auto()
    SUGGEST = auto()
    POKEDEX = auto()
    MARKET = auto()
    PREFS = auto()
    STATUS = auto()
    HISTORY = auto()
    INDEX = auto()
    ABOUT = auto()
    CLEAR = auto()
    HELP = auto()
    QUIT = auto()
    OFFERS = auto()
    OFFER_SEND = auto()
    OFFER_ACCEPT = auto()
    OFFER_DECLINE = auto()
    UNKNOWN = auto()


class TradeParams(NamedTuple):
    """Parameters for a trade command."""

    offered: str
    requested: str


class OfferParams(NamedTuple):
    """Parameters for a send-offer command."""

    recipient: str
    offered: str
    requested: str


@dataclass
class ParsedCommand:
    """Result of parsing user input."""

    command_type: CommandType
    args: str = ""
    trade_params: TradeParams | None = None
    offer_params: OfferParams | None = None


# Pre-defined command mappings
_QUIT_COMMANDS: frozenset[str] = frozenset({"quit", "exit", "q"})
_HELP_COMMANDS: frozenset[str] = frozenset({"help", "h", "?"})
_SIMPLE_COMMANDS: dict[str, CommandType] = {
    "suggest": CommandType.SUGGEST,
    "prefs": CommandType.PREFS,
    "status": CommandType.STATUS,
    "history": CommandType.HISTORY,
    "index": CommandType.INDEX,
    "about": CommandType.ABOUT,
    "clear": CommandType.CLEAR,
    "offers": CommandType.OFFERS,
}
_PREFIX_COMMANDS: tuple[tuple[str, CommandType, int], ...] = (
    ("pokedex", CommandType.POKEDEX, 7),
    ("market", CommandType.MARKET, 6),
    ("offers", CommandType.OFFERS, 6),  # "offers sent" → args="sent"
)
# accept/decline require a numeric ID or "all" — anything else goes to the LLM
_ACCEPT_ARGS: frozenset[str] = frozenset({"all"})


def parse_command(user_input: str) -> ParsedCommand:
    """Parse user input into a command."""
    text = user_input.strip()
    if not text:
        return ParsedCommand(CommandType.UNKNOWN)

    lower = text.lower()

    if lower in _QUIT_COMMANDS:
        return ParsedCommand(CommandType.QUIT)

    if lower in _HELP_COMMANDS:
        return ParsedCommand(CommandType.HELP)

    if lower in _SIMPLE_COMMANDS:
        return ParsedCommand(_SIMPLE_COMMANDS[lower])

    for prefix, cmd_type, prefix_len in _PREFIX_COMMANDS:
        if lower.startswith(prefix):
            args = text[prefix_len:].strip()
            return ParsedCommand(cmd_type, args=args)

    # accept / decline: only route as commands when arg is a number, "all", or absent
    if lower == "accept" or lower.startswith("accept "):
        args = text[6:].strip()
        if not args or args.lower() in _ACCEPT_ARGS or args.isdigit():
            return ParsedCommand(CommandType.OFFER_ACCEPT, args=args)

    if lower == "decline" or lower.startswith("decline "):
        args = text[7:].strip()
        if not args or args.isdigit():
            return ParsedCommand(CommandType.OFFER_DECLINE, args=args)

    if lower.startswith("offer ") and " to " in lower and " for " in lower:
        offer_params = _parse_offer(lower)
        if offer_params:
            return ParsedCommand(
                CommandType.OFFER_SEND,
                args=text,
                offer_params=offer_params,
            )

    if lower.startswith("trade "):
        trade_params = _parse_trade(lower)
        if trade_params:
            return ParsedCommand(
                CommandType.TRADE,
                args=text,
                trade_params=trade_params,
            )

    return ParsedCommand(CommandType.UNKNOWN, args=text)


def _parse_trade(text: str) -> TradeParams | None:
    """Parse trade command parameters."""
    if " for " not in text:
        return None

    clean = text.replace("trade ", "").replace("my ", "")
    parts = clean.split(" for ", maxsplit=1)

    if len(parts) != 2:
        return None

    offered = parts[0].strip()
    requested = parts[1].replace("their ", "").strip()

    if not offered or not requested:
        return None

    return TradeParams(offered=offered, requested=requested)


def _parse_offer(text: str) -> OfferParams | None:
    """Parse 'offer <pokemon> to <user> for <their_pokemon>' into OfferParams."""
    # Strip leading "offer " keyword
    body = text[len("offer ") :].strip()

    if " to " not in body or " for " not in body:
        return None

    # Split on " to " first
    to_parts = body.split(" to ", maxsplit=1)
    if len(to_parts) != 2:
        return None

    offered = to_parts[0].strip()
    remainder = to_parts[1]  # "<user> for <their_pokemon>"

    if " for " not in remainder:
        return None

    for_parts = remainder.split(" for ", maxsplit=1)
    if len(for_parts) != 2:
        return None

    recipient = for_parts[0].strip()
    requested = for_parts[1].strip()

    if not offered or not recipient or not requested:
        return None

    return OfferParams(recipient=recipient, offered=offered, requested=requested)
