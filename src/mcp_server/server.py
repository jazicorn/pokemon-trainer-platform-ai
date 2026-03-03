"""MCP Server for Pokemon Trade Advisor."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from agents import evaluate_trade, get_trade_suggestions, query_pokedex
from agents.trade_market_analyst import query_market

from .tools import (
    VALID_TOOLS,
    get_tools,
)

# Create the MCP server instance
mcp_server = Server("pokemon-trade-advisor")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return list(get_tools())


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Handle tool calls."""
    if name not in VALID_TOOLS:
        return _error_result(f"Unknown tool: {name}")

    try:
        result = await _dispatch_tool(name, arguments)
        return _success_result(result)
    except KeyError as e:
        return _error_result(f"Missing required argument: {e}")
    except Exception as e:
        return _error_result(f"Error: {e}")


async def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
    """Dispatch to appropriate tool handler."""
    match name:
        case "evaluate_trade":
            return await evaluate_trade(
                offered_pokemon=args["offered_pokemon"],
                requested_pokemon=args["requested_pokemon"],
                user_id=args.get("user_id", "user_001"),
            )
        case "get_trade_suggestions":
            return await get_trade_suggestions(
                user_id=args.get("user_id", "user_001"),
            )
        case "query_pokedex":
            return await query_pokedex(
                args["question"],
                user_id=args.get("user_id", "user_001"),
            )
        case "query_market":
            return await query_market(args["question"])
        case _:
            raise ValueError(f"Unhandled tool: {name}")


def _success_result(text: str) -> CallToolResult:
    """Create a successful tool result."""
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _error_result(message: str) -> CallToolResult:
    """Create an error tool result."""
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        isError=True,
    )


async def run_server() -> None:
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )


def main() -> None:
    """Entry point for MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
