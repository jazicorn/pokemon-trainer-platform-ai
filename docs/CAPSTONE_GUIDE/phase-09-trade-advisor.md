# Phase 9: Trade Advisor

## Overview

Phase 9 introduces the **Trade Advisor** — the orchestrating agent at the center of the system.
Given a trade proposal ("Should I give my Alakazam for their Machamp?"), the Trade Advisor gathers
Pokemon stats from the Pokedex Expert, market data from the Market Analyst, legitimacy info from the
Legitimacy Guard, and the user's personal context from memory, then synthesizes all four into an
explainable recommendation.

The Trade Advisor is the agent the user interacts with. Every other specialized agent exists to
serve it.

## Where It Fits

```text
Phase 5: Pokedex Expert    ─┐
Phase 7: Market Forecasting ─┤
Phase 8: Legitimacy Guard   ─┼→ Phase 9: Trade Advisor (Orchestrator)
Phase 3: Memory System      ─┘         ↓
                                Phase 10: Multi-Agent (refines delegation)
                                Phase 11: CLI (user-facing interface)
```

## Key Files

- `src/agents/trade_advisor.py` — The core file. Defines `AdvisorDependencies`, the `trade_advisor`
  Pydantic AI agent, four tool functions (`get_pokemon_info`, `get_market_data`, `get_user_context`,
  `check_legitimacy`), and top-level public functions `evaluate_trade()`, `get_trade_suggestions()`,
  `get_pending_offers()`, and `send_trade_offer()`.
- `src/agents/__init__.py` — Re-exports all public agent functions for clean imports elsewhere.
  External code always imports from here, never from individual agent modules.

## Key Concepts

**AdvisorDependencies**: The agent receives a `deps` object at runtime containing `vector_store`,
`analytics`, `user_collection`, and `user_id`. This is dependency injection — the agent never
constructs these itself. Each field accepts `None`, which causes the corresponding tool to return a
graceful "not available" string instead of raising. This makes testing straightforward: pass `None`
for deps you don't need, or pass mocks.

```python
class AdvisorDependencies(BaseModel):
    vector_store: PokemonVectorStore | None = None
    analytics: TradeAnalytics | None = None
    user_collection: UserCollection | None = None
    user_id: str = "user_001"
```

**Four tools, single agent**: The Trade Advisor has exactly four tools:

| Tool | Delegates to |
| --- | --- |
| `get_pokemon_info` | Pokedex Expert |
| `get_market_data` | Market Analyst |
| `check_legitimacy` | Legitimacy Guard |
| `get_user_context` | Reads from `ctx.deps` directly |

The LLM decides which tools to call and in what order based on the user's question. For a trade
evaluation it typically calls all four; for a market query it calls only `get_market_data`.

**`evaluate_trade()` vs `get_trade_suggestions()`**: `evaluate_trade(offered, requested, user_id)`
evaluates a specific proposed trade. It also accepts a `raw_query` string so natural-language
questions typed at the CLI prompt ("What's the market sentiment?") can be routed through the same
agent without constructing artificial trade parameters. `get_trade_suggestions(user_id)` asks the
agent to look at the user's seeking list and cross-reference with trending bullish Pokemon,
producing proactive recommendations without any specific trade proposal.

**The system prompt defines three operating modes**: MARKET INTELLIGENCE (forecasts and sentiment
for one Pokemon), TRADE EVALUATION (get info on both sides, check market and personal fit, give
verdict), and GENERAL INQUIRIES (use user context and suggestions). The prompt instructs the agent
to be data-driven and use specific numbers from specialists.

**`store.close()` in a `finally` block**: `evaluate_trade()` and `get_trade_suggestions()` open a
`PokemonVectorStore` (ChromaDB client) and must close it even if the agent raises. The `try/finally`
pattern ensures the connection is always released.

## Exploring the Code

Start by reading `AdvisorDependencies` and the four `@trade_advisor.tool` functions in
`trade_advisor.py`. Each tool is a thin wrapper — the real intelligence lives in the specialists.
Notice the consistent guard at the top of each tool:

```python
@trade_advisor.tool
async def get_pokemon_info(ctx: RunContext[AdvisorDependencies], pokemon: str) -> str:
    if ctx.deps.vector_store is None:
        return "Pokemon data not available"
    # ... delegate to pokedex_expert
```

Then read `evaluate_trade()` to see how `AdvisorDependencies` is assembled before the agent run: it
loads the vector store, analytics engine, and user collection, constructs `deps`, passes `raw_query`
or a formatted prompt, and returns the agent's output string.

In `test_trade_advisor.py`, read `TestAdvisorDependencies` to see how the dependency model is
validated, `TestTradeAdvisorAgent` for system prompt assertions, and `TestTradeAdvisorIntegration`
for the `FunctionModel` pattern that exercises real tool dispatch without a live LLM.

## Running the Code

```bash
# Evaluate a specific trade (requires API key + ChromaDB running)
uv run python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from agents import evaluate_trade
result = asyncio.run(evaluate_trade('pikachu', 'charizard', 'user_001'))
print(result)
"

# Get personalized suggestions
uv run python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from agents import get_trade_suggestions
result = asyncio.run(get_trade_suggestions('user_001'))
print(result)
"

# Use the CLI (easiest path — handles sys.path automatically)
op run --env-file .env.op -- uv run python app.py
# Then type:  trade pikachu for charizard
# Or type:    suggest
```

## Running the Tests

```bash
# Trade advisor structure, deps, and tool integration
uv run pytest tests/test_trade_advisor.py -v

# Multi-agent tool definitions (also covers the advisor's tool list)
uv run pytest tests/test_multi_agent.py -v

# Run both together
uv run pytest tests/test_trade_advisor.py tests/test_multi_agent.py -v
```

`test_trade_advisor.py` covers:

- `TestAdvisorDependencies` — accepts `None` values, accepts a real `UserCollection`
- `TestTradeAdvisorAgent` — system prompt is set and mentions key concepts, model is configured
- `TestUserContextHelpers` — `UserCollection` fixture: tradeable flag, seeking list, never-trade
  list
- `TestTradeAdvisorIntegration` — async tests using `FunctionModel` to verify each tool delegates
  correctly and returns graceful fallbacks when deps are `None`

`test_multi_agent.py` covers:

- `TestMultiAgentOrchestration` — `get_pokemon_info` and `get_market_data` are callable and
  decorated; direct async invocation of each tool with a mock sub-agent run verifies the delegation
  chain

## Common Gotchas

**ChromaDB must be running for `evaluate_trade()`**: `PokemonVectorStore()` in `evaluate_trade()`
connects to ChromaDB at startup. If ChromaDB is not running, the call fails before the agent even
runs. Start ChromaDB first (see `GETTING_STARTED.md`) or run `startup(chromadb=False)` to skip it
(the `get_pokemon_info` tool will then return "Pokemon data not available").

**User collection must exist for the user ID**: `evaluate_trade()` calls
`load_user_collection(user_id)`. If `data/user_collection.json` does not contain that user, it
raises `ValueError`. Generate data first with `uv run python -m src.data.generator` or use
`"user_001"` which is always seeded.

**`raw_query` bypasses the trade parameter format**: When the CLI routes an unrecognized
natural-language input through `evaluate_trade(raw_query=...)`, the `offered_pokemon` and
`requested_pokemon` parameters are empty strings. The agent still runs — it just responds to the
freeform question using whichever tools it decides to call.

**Usage propagation**: The tool calls pass `usage=ctx.usage` when running sub-agents. This
aggregates token counts from all nested agent calls into the parent run's usage object. If you call
sub-agents without passing usage, token accounting for the orchestrated run will be incomplete.
