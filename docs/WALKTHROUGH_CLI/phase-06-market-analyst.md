# Stage 6: Market Analyst

## Overview

Stage 6 introduces the **Trade Market Analyst** — a specialized agent that analyzes platform-wide
trade patterns to answer questions about supply, demand, and market value. Unlike the Pokedex Expert
(which knows about individual Pokemon), the Market Analyst understands collective behavior: which
Pokemon are being requested most, which are oversupplied, and what trade success rates look like.

The intelligence lives in `TradeAnalytics`, a pure Python class that computes metrics from the mock
trade history loaded from `data/platform_trades.json`. The agent wraps this analytics engine and
exposes it through a tool-calling interface.

## Where It Fits

```text
Stage 2: Mock Data (platform_trades.json as the data source)
        |
Stage 6: Market Analyst (base demand analytics)
        |
Stage 12: Market Forecasting (adds momentum / sentiment to TradeAnalytics)
Stage 11: Multi-Agent Orchestration (Trade Advisor calls Market Analyst via tool)
Stage 8:  Evaluations (market data accuracy is measured)
```

## Key Files

| File | Role |
| --- | --- |
| `src/agents/trade_analytics.py` | `TradeAnalytics` class and `DemandThresholds` dataclass — all market calculations |
| `src/agents/trade_market_analyst.py` | `trade_market_analyst` Pydantic AI agent, `MarketDependencies`, and `query_market()` public entry point |

## Key Concepts

### Demand ratio as the core market signal

```text
demand_ratio = times_requested / times_offered
```

A ratio above 1 means more people want the Pokemon than are offering it (high demand). A ratio below
1 means oversupply. Ratio of `inf` means the Pokemon has never been offered — it only appears in
trade requests.

`DemandThresholds` classifies ratios into five tiers:

| Tier | Threshold |
| --- | --- |
| very_high | ratio >= 3.0 |
| high | ratio >= 1.5 |
| balanced | ratio >= 0.8 |
| low | ratio >= 0.4 |
| very_low | ratio < 0.4 |

### O(1) index lookup

`TradeAnalytics._build_indexes()` runs once in `__init__` and builds three data structures from the
full trade list: a `Counter` of requested Pokemon names, a `Counter` of offered Pokemon names, and a
dict mapping each Pokemon name to all trades it appears in. Every public method is then an O(1) or
O(k) lookup against these indexes rather than a linear scan.

### Analytics are stateless and side-effect free

`TradeAnalytics` loads `platform_trades.json` once in `__init__` and never modifies it. Every method
computes from that snapshot. This makes testing straightforward: pass a `PlatformTrades` fixture
instead of relying on the real file.

### Agent as a thin orchestration layer

The `trade_market_analyst` agent has five tools:

- `get_market_forecast(pokemon)` — calls `analytics.get_market_forecast()` (Stage 12 adds this)
- `get_pokemon_demand(pokemon)` — calls `analytics.get_demand_ratio(pokemon)`
- `get_trade_success(pokemon)` — calls `analytics.get_trade_success_rate(pokemon)`
- `get_trending(days=30)` — calls `analytics.get_trending_pokemon(days, limit=10)`
- `compare_market_value(pokemon_a, pokemon_b)` — calls `analytics.compare_trade_value()`
- `get_high_demand_pokemon()` — calls `analytics.get_most_requested(limit=10)` and enriches with
  demand ratios

The LLM interprets the question and routes it to the right tool. The actual computation is in
`TradeAnalytics`, not in the model.

### `compare_trade_value` uses a 20% threshold

`_compare_values()` returns `"approximately equal value"` unless one ratio exceeds the other by more
than 20% (`threshold = 1.2`). This prevents noise from very small ratio differences being reported
as meaningful.

## Exploring the Code

Start with `src/agents/trade_analytics.py`. Read `DemandThresholds` first (the five classification
tiers and their boundary values). Then read `_build_indexes()` to understand the data structure.
Then read `get_demand_ratio()` — note the `days` parameter that optionally filters to recent trades.
Then read `compare_trade_value()` and see how it calls `get_demand_ratio()` twice and passes the
results to `_compare_values()`.

In `src/agents/trade_market_analyst.py`, read `MarketDependencies` — it holds only an `analytics:
TradeAnalytics | None`. Read the system prompt's numeric rules: `demand_ratio > 1` means high
demand, momentum above 15% is Bullish. Then read the `get_pokemon_demand` tool to see the full
output format the LLM receives.

## Running the Code

```bash
# Inspect market data directly without the agent
uv run python -c "
import sys; sys.path.insert(0, 'src')
from agents.trade_analytics import TradeAnalytics
analytics = TradeAnalytics()
print('Charizard demand:', analytics.get_demand_ratio('charizard'))
print('Pikachu demand:', analytics.get_demand_ratio('pikachu'))
print('Top requested:', analytics.get_most_requested(limit=5))
print('Charizard success rate:', analytics.get_trade_success_rate('charizard'))
print('Compare charizard vs pikachu:', analytics.compare_trade_value('charizard', 'pikachu'))
"

# Query the Market Analyst agent (requires API key)
uv run python -c "
import asyncio
from agents import query_market
result = asyncio.run(query_market('What Pokemon are in highest demand right now?'))
print(result)
"

# Check trending Pokemon over last 30 days
uv run python -c "
import sys; sys.path.insert(0, 'src')
from agents.trade_analytics import TradeAnalytics
analytics = TradeAnalytics()
for p in analytics.get_trending_pokemon(days=30, limit=5):
    print(p)
"
```

## Running the Tests

```bash
uv run pytest tests/agents/test_trade_analytics.py -v
```

### What the tests cover

`TestDemandThresholds` — verifies all five tiers with specific input values:

- `3.5` classifies as `very_high`
- `2.0` classifies as `high`
- `1.0` classifies as `balanced`
- `0.5` classifies as `low`
- `0.2` classifies as `very_low`

`TestTradeAnalytics` — uses a 3-trade `sample_trades` fixture (injected directly, not from disk):

- `test_demand_ratio_high_demand` — Charizard is requested twice and offered once: ratio 2.0, level
  "high"
- `test_demand_ratio_no_trades` — Bulbasaur has no trades: ratio "∞", times both zero
- `test_trade_success_rate` — Charizard appears in all 3 trades, 2 completed: success_rate 66.7
- `test_trade_success_rate_no_trades` — Bulbasaur has zero trades, success_rate 0.0
- `test_most_requested` — Charizard is the most requested with count 2
- `test_compare_trade_value` — returns dict with `pokemon_a`, `pokemon_b`, `value_comparison` keys

`TestMarketAnalystAgent` — checks agent configuration without a live LLM:

- Agent has a system prompt
- Agent has a configured model
- `MarketDependencies(analytics=None)` is accepted without error
