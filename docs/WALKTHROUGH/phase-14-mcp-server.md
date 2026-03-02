# Phase 14: MCP Server (Optional)

## Overview

Phase 14 exposes the Trade Advisor as an **MCP (Model Context Protocol) server**, allowing external
AI assistants such as Claude Desktop to call the advisor's capabilities as structured tools. This is
an optional integration layer — the core CLI system works without it.

Four tools are exposed: evaluate a specific trade, get proactive trade suggestions, query the
Pokedex, and query the market. The server communicates over stdio using the MCP JSON-RPC protocol.
An external client starts the server as a subprocess and sends requests over the stdio pipe.

## Where It Fits

```text
Phase 5: Pokedex Expert      (query_pokedex exposed as tool)
Phase 6+7: Market Analyst    (query_market exposed as tool)
Phase 9: Trade Advisor       (evaluate_trade + get_trade_suggestions exposed as tools)
        ↓
Phase 14: MCP Server (optional external interface — wraps all four agent functions)
```

## Key Files

- `src/mcp_server/tools.py` — Defines the three JSON Schema objects (`EVALUATE_TRADE_SCHEMA`,
  `SUGGESTIONS_SCHEMA`, `QUERY_SCHEMA`), `get_tools()` (returns a tuple of four `mcp.types.Tool`
  objects), four string constants for tool names, and `VALID_TOOLS` frozenset.
- `src/mcp_server/server.py` — Creates the `mcp_server = Server("pokemon-trade-advisor")` instance,
  registers `list_tools` and `call_tool` handlers, implements `_dispatch_tool()` using a `match`
  statement, and defines `run_server()` / `main()` entry points.
- `src/mcp_server/__init__.py` — Re-exports `mcp_server`, `run_server`, `main`, `get_tools`, the
  four tool name constants, and `VALID_TOOLS` for clean external imports.
- `tests/mcp/test_mcp_server.py` — Verifies tool definitions and schema structure. No live agent calls.

## Key Concepts

**MCP tool schema**: Each tool is an `mcp.types.Tool` with three required fields: `name` (string
identifier), `description` (human-readable purpose), and `inputSchema` (JSON Schema object). The
schema defines which arguments are required vs. optional. The MCP client reads these schemas to know
what arguments to supply when calling a tool.

**Four tools, one agent function each**:

| MCP Tool | Agent Function | Required Args | Optional Args |
| --- | --- | --- | --- |
| `evaluate_trade` | `agents.evaluate_trade()` | `offered_pokemon`, `requested_pokemon` | `user_id` |
| `get_trade_suggestions` | `agents.get_trade_suggestions()` | _(none)_ | `user_id` |
| `query_pokedex` | `agents.query_pokedex()` | `question` | _(none)_ |
| `query_market` | `agents.trade_market_analyst.query_market()` | `question` | _(none)_ |

**Shared `QUERY_SCHEMA`**: `query_pokedex` and `query_market` both accept a single `question`
string. Rather than defining two identical schemas, `tools.py` defines one `QUERY_SCHEMA` dict and
reuses it for both tools. This is a deliberate de-duplication choice.

**`VALID_TOOLS` frozenset**: Tool names are validated against a module-level `frozenset` before
dispatch. This gives O(1) membership testing and a single source of truth for which tools are valid.
The `call_tool` handler returns an error `CallToolResult` immediately if the name is not in
`VALID_TOOLS`, before the `match` statement in `_dispatch_tool()` is reached.

**`match` statement dispatch**: `_dispatch_tool()` uses Python's structural pattern matching (`match
name: case "evaluate_trade":`) instead of an `if/elif` chain. The `case _:` fallback raises
`ValueError` — this branch should be unreachable because `VALID_TOOLS` already guards entry, but it
makes the exhaustiveness explicit.

**Error result helpers**: `_success_result()` and `_error_result()` both return `CallToolResult`
objects containing a single `TextContent`. The difference is that `_error_result()` sets
`isError=True`. This is the MCP protocol's way of signaling tool failure to the client without
raising a Python exception across the stdio boundary.

**Stdio transport**: `run_server()` uses `mcp.server.stdio.stdio_server()` as an async context
manager, which sets up the read/write stream pair on stdin/stdout. The server process is meant to be
started as a subprocess by the MCP host; running it interactively in a terminal produces no visible
output because there is no client sending requests.

## Exploring the Code

Read `tools.py` top to bottom. The three schema dicts are defined at module level (not inside
`get_tools()`) so they are constructed once. Notice that `EVALUATE_TRADE_SCHEMA` has `user_id` in
`properties` but not in `required` — this is what `test_suggestions_has_optional_user_id` verifies
(though the same optional pattern applies to `evaluate_trade`). The `get_tools()` function assembles
the four `Tool` objects from these schemas each time it is called; the returned tuple is immutable.

In `server.py`, read `call_tool()` to understand the error handling layers: `VALID_TOOLS` check
first, then `_dispatch_tool()` inside a `try/except` that catches `KeyError` (missing required arg
from the client) separately from generic `Exception`. Then read `_dispatch_tool()` to see how args
are extracted — required args use direct key access (`args["offered_pokemon"]`), while optional args
use `.get()` with a default (`args.get("user_id", "user_001")`).

In `test_mcp_server.py`, read `TestToolSchemas.test_evaluate_trade_requires_pokemon` to see the
exact assertion pattern: it retrieves the `required` list from `inputSchema` and checks membership.
This is how you would write schema tests for any new tool you add.

## Running the Code

```bash
# Verify the module loads and reports the correct tool count
uv run python -c "
import sys
sys.path.insert(0, 'src')
from mcp_server import get_tools
print(f'{len(get_tools())} tools available')
for t in get_tools():
    print(f'  - {t.name}')
"

# Start the MCP server (blocks waiting for stdin — Ctrl-C to exit)
uv run python -m src.mcp_server.server

# With 1Password secret resolution
op run --env-file .env.op -- uv run python -m src.mcp_server.server
```

To connect via Claude Desktop, add an entry to your MCP configuration file (typically
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "pokemon-trade-advisor": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp_server.server"],
      "cwd": "/path/to/pokemon-trainer-platform-ai",
      "env": {
        "ANTHROPIC_API_KEY": "your-key-here"
      }
    }
  }
}
```

After adding the config, restart Claude Desktop. The four tools will appear in Claude's tool panel
and can be called during a conversation.

## Running the Tests

```bash
# MCP tool definitions and schema structure (no LLM calls, no API key needed)
uv run pytest tests/mcp/test_mcp_server.py -v
```

### `TestMCPTools` covers

- `get_tools()` returns a `tuple` (not a list)
- `get_tools()` returns exactly 4 tools
- Every tool has a non-empty string `name`
- Every tool has a `description` longer than 10 characters
- Every tool has an `inputSchema` with `"type": "object"` at the top level
- All four tool name constants (`TOOL_EVALUATE_TRADE`, `TOOL_SUGGESTIONS`, `TOOL_POKEDEX`,
  `TOOL_MARKET`) appear in the set of tool names returned by `get_tools()`
- `VALID_TOOLS` is a `frozenset` with exactly 4 members

### `TestToolSchemas` covers

- `evaluate_trade` schema has both `offered_pokemon` and `requested_pokemon` in its `required` list
- `query_pokedex` and `query_market` schemas both have `question` in their `required` list
- `get_trade_suggestions` schema has `user_id` in `properties` but NOT in `required` (it is optional
  with a default)

No live agent calls are made in any of these tests — they only import from `mcp_server.tools` and
inspect the returned data structures.

## Common Gotchas

**Running the server interactively shows nothing**: When you run `uv run python -m
src.mcp_server.server` in a terminal, the process blocks waiting for MCP JSON-RPC messages on stdin.
There is no startup banner. If you want to verify the server starts cleanly, check the exit code or
import the module and call `get_tools()` instead.

**`query_market` is imported differently from the other agents**: In `server.py`, `evaluate_trade`,
`get_trade_suggestions`, and `query_pokedex` are imported from `agents` (the package `__init__.py`),
but `query_market` is imported directly from `agents.trade_market_analyst`. This is because
`query_market` is not re-exported from `agents/__init__.py`. If you add new agent functions and need
to expose them as MCP tools, check `src/agents/__init__.py` to see whether the function is already
re-exported.

**`user_id` default is `"user_001"`**: Both `evaluate_trade` and `get_trade_suggestions` default to
`"user_001"` when `user_id` is not supplied by the MCP client. This matches the seeded data in
`data/user_collection.json`. If a client sends a different `user_id` that has no seeded data,
`evaluate_trade()` may raise `ValueError`. See the Trade Advisor phase docs for details on user data
requirements.
