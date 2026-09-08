"""MCP tool definitions for Pokemon Trade Advisor."""

from __future__ import annotations

from typing import Any

from mcp.types import Tool

# Tool schemas defined once at module level
EVALUATE_TRADE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "offered_pokemon": {
            "type": "string",
            "description": "The Pokemon being offered",
        },
        "requested_pokemon": {
            "type": "string",
            "description": "The Pokemon being requested",
        },
        "user_id": {
            "type": "string",
            "description": "User ID for personalization",
            "default": "user_001",
        },
    },
    "required": ["offered_pokemon", "requested_pokemon"],
}

SUGGESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {
            "type": "string",
            "description": "User ID",
            "default": "user_001",
        },
    },
}

QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "Question to ask",
        },
    },
    "required": ["question"],
}

POKEDEX_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "Question to ask the Pokedex Expert",
        },
        "user_id": {
            "type": "string",
            "description": "User ID for personalizing collection lookups",
            "default": "user_001",
        },
    },
    "required": ["question"],
}


def get_tools() -> tuple[Tool, ...]:
    """Return all available MCP tools."""
    return (
        Tool(
            name="evaluate_trade",
            description=(
                "Evaluate a proposed Pokemon trade. Analyzes the trade "
                "considering Pokemon stats, market demand, and user goals."
            ),
            inputSchema=EVALUATE_TRADE_SCHEMA,
        ),
        Tool(
            name="get_trade_suggestions",
            description=("Get proactive trade suggestions based on the user's collection and goals."),
            inputSchema=SUGGESTIONS_SCHEMA,
        ),
        Tool(
            name="query_pokedex",
            description=("Query Pokemon information including stats, types, abilities, and competitive analysis."),
            inputSchema=POKEDEX_QUERY_SCHEMA,
        ),
        Tool(
            name="query_market",
            description=("Get market information including demand ratios, trending Pokemon, and trade success rates."),
            inputSchema=QUERY_SCHEMA,
        ),
    )


# Tool name constants for type-safe dispatch
TOOL_EVALUATE_TRADE = "evaluate_trade"
TOOL_SUGGESTIONS = "get_trade_suggestions"
TOOL_POKEDEX = "query_pokedex"
TOOL_MARKET = "query_market"

VALID_TOOLS: frozenset[str] = frozenset(
    {
        TOOL_EVALUATE_TRADE,
        TOOL_SUGGESTIONS,
        TOOL_POKEDEX,
        TOOL_MARKET,
    }
)
