# Phase 10: Multi-Agent Orchestration

## Overview

Phase 10 refines how the Trade Advisor coordinates with its specialist agents. The core principle:
the Trade Advisor should **never directly query ChromaDB, call external APIs, or run analytics** —
it delegates all data gathering to its specialists via tool calls. This is the hierarchical
delegation pattern (sometimes called Master-Worker).

This phase isn't a new feature — it's an architectural refinement that makes the system more
maintainable, testable, and scalable. Each specialist can be upgraded independently without touching
the orchestrator.

## Where It Fits

```text
Phase 9: Trade Advisor (basic orchestration)
        ↓
Phase 10: Multi-Agent Orchestration (strict delegation boundaries)
        ↓
Phase 11: CLI (calls the orchestrated system)
Phase 13: Evaluations (measures orchestration quality)
```

## Key Files

- `src/agents/trade_advisor.py` — The three sub-agent delegation tools (`get_pokemon_info`,
  `get_market_data`, `check_legitimacy`) form the delegation boundary. They call sub-agents; they
  never access ChromaDB or PokeAPI directly.
- `src/agents/__init__.py` — The public API surface. External code imports from here.
- `src/agents/pokedex_expert.py` — Worker agent: `pokedex_expert`, `PokedexDependencies`. Has its
  own tools (`search_pokemon`, `get_type_effectiveness`, `get_my_collection`).
- `src/agents/trade_market_analyst.py` — Worker agent: `trade_market_analyst`, `MarketDependencies`.
  Has tools for demand ratios, forecasts, trending, and value comparison.
- `src/agents/legitimacy_guard.py` — Worker agent: `legitimacy_guard`, `LegitimacyDependencies`. Has
  `verify_provenance` tool with ball-legality, shiny-lock, and origin checks.

## Key Concepts

**Tool calls as the delegation interface**: In Pydantic AI, tools are the mechanism for
agent-to-agent communication. When the Trade Advisor's `get_pokemon_info` tool runs, it constructs a
`PokedexDependencies` object, calls `pokedex_expert.run(...)`, and returns the result as a plain
string. The orchestrator never sees the Pokedex Expert's internal tools or system prompt.

```python
@trade_advisor.tool
async def get_pokemon_info(ctx: RunContext[AdvisorDependencies], pokemon: str) -> str:
    pokedex_deps = PokedexDependencies(
        vector_store=ctx.deps.vector_store, user_id=ctx.deps.user_id
    )
    result = await pokedex_expert.run(
        f"Provide a technical breakdown of {pokemon}.",
        deps=pokedex_deps,
        usage=ctx.usage,
    )
    return str(result.output)
```

**`get_user_context` is the exception**: This is the only Trade Advisor tool that does not call a
sub-agent. User memory (collection, preferences, seeking list) is owned directly by the orchestrator
layer and formatted in the tool body. There is no "User Memory Expert" sub-agent.

**Usage propagation with `usage=ctx.usage`**: All three sub-agent calls pass the parent's
`ctx.usage` object. Pydantic AI accumulates token counts from nested runs into this shared object,
so the top-level run's reported usage reflects the full cost of all delegated calls. Omitting this
parameter would under-report token use.

**Fewer tools = better reasoning**: A single flat agent with 20+ tools (one per data source)
degrades LLM reasoning quality — the model spends cognitive effort choosing among tools rather than
analyzing the trade. The hierarchical pattern keeps the Trade Advisor to 4 tools by hiding
complexity behind specialist agents. The Market Analyst alone has 5 tools (`get_market_forecast`,
`get_pokemon_demand`, `get_trade_success`, `get_trending`, `compare_market_value`,
`get_high_demand_pokemon`).

**Isolation for testability**: Each specialist agent has its own test file and can be tested
completely independently of the orchestrator using `monkeypatch` to replace the sub-agent's `.run()`
method with an `AsyncMock`. The orchestrator tests never need a live LLM or ChromaDB.

## Exploring the Code

In `trade_advisor.py`, read all four `@trade_advisor.tool` functions side by side:

| Tool | What it constructs | What it calls |
| --- | --- | --- |
| `get_pokemon_info` | `PokedexDependencies(vector_store, user_id)` | `pokedex_expert.run(...)` |
| `get_market_data` | `MarketDependencies(analytics)` | `trade_market_analyst.run(...)` |
| `check_legitimacy` | `LegitimacyDependencies()` (uses module defaults) | `legitimacy_guard.run(...)` |
| `get_user_context` | nothing — reads `ctx.deps` directly | no sub-agent |

Notice that `check_legitimacy` constructs `LegitimacyDependencies()` with no arguments — the ball
legality map, shiny-lock set, and origin marks are module-level constants used as Pydantic defaults.
The orchestrator never needs to know about them.

Then read each worker agent's file to see what tools it exposes to its own LLM call — the Pokedex
Expert has 3, the Market Analyst has 6, the Legitimacy Guard has 1.

In `test_multi_agent.py`, read `TestMultiAgentOrchestration`. The tests call the tool functions
directly (bypassing the LLM) with a mock `ctx` object and a `monkeypatched` sub-agent `.run()`. This
is the cleanest way to verify the delegation wiring without any network I/O.

## Running the Code

```bash
# See the full delegation chain in action
op run --env-file .env.op -- uv run python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from agents import evaluate_trade
# This triggers:
#   Trade Advisor -> get_pokemon_info -> Pokedex Expert (search_pokemon tool)
#   Trade Advisor -> get_market_data  -> Market Analyst (get_market_forecast, get_pokemon_demand)
#   Trade Advisor -> check_legitimacy -> Legitimacy Guard (verify_provenance)
#   Trade Advisor -> get_user_context -> reads ctx.deps directly
result = asyncio.run(evaluate_trade('gengar', 'alakazam', 'user_001'))
print(result)
"

# View agent traces in Phoenix (if running at http://localhost:6006)
# Each sub-agent call appears as a nested span under the parent Trade Advisor run.
```

## Running the Tests

```bash
# Multi-agent delegation wiring tests
uv run pytest tests/test_multi_agent.py -v

# Combined with trade advisor structure tests
uv run pytest tests/test_multi_agent.py tests/test_trade_advisor.py -v

# Specialist agents tested independently
uv run pytest tests/test_pokedex_agent.py -v
uv run pytest tests/test_legitimacy_guard.py -v
```

`test_multi_agent.py` covers:

- `test_advisor_tools_defined` — verifies `get_pokemon_info` and `get_market_data` are callable and
  decorated as tools
- `test_delegation_to_pokedex` — calls `get_pokemon_info(ctx, "pikachu")` directly with a
  monkeypatched `pokedex_expert.run`; asserts the mock was called once and the result string passed
  through
- `test_delegation_to_market` — same pattern for `get_market_data` and `trade_market_analyst.run`

These tests never make a live LLM call. They use a mock `ctx` object and `AsyncMock` to verify the
wiring layer only.

## Common Gotchas

**Monkeypatching the module namespace, not the import**: In `test_multi_agent.py` and
`test_trade_advisor.py`, the tests patch both the sub-agent's `.run` method and the
`PokedexDependencies` / `MarketDependencies` constructor in the `agents.trade_advisor` module
namespace. This is necessary because the tools in `trade_advisor.py` construct the deps objects
locally — if you only patch the class in its original module, the local reference in
`trade_advisor.py` still points to the real class and Pydantic validation fails on the `MagicMock`
vector_store.

```python
# Correct pattern — patch both the sub-agent run AND the deps class in trade_advisor's namespace
monkeypatch.setattr(pokedex_expert_agent, "run", mock_run)
ta_mod = sys.modules["agents.trade_advisor"]
monkeypatch.setattr(ta_mod, "PokedexDependencies", lambda **kwargs: MagicMock())
```

**`check_legitimacy` does not guard on deps**: Unlike `get_pokemon_info` and `get_market_data`,
`check_legitimacy` constructs `LegitimacyDependencies()` unconditionally and always calls
`legitimacy_guard.run()`. There is no `if ctx.deps.something is None` guard because the Legitimacy
Guard's deps have no external dependencies — all data is embedded in module-level constants.

**Worker agents are independently runnable**: You can call `query_pokedex("What type is Gengar?")`
or `query_market("What's trending?")` directly without going through the Trade Advisor. The CLI's
`pokedex` and `market` commands do exactly this for fast, direct lookups that don't need full
orchestration.
