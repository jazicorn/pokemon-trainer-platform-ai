# Phase 7: Market Forecasting

## Overview

Phase 7 adds **predictive intelligence** to the Market Analyst. Rather than only reporting current
demand, the system now computes a **momentum score** that compares short-term (7-day) and long-term
(30-day) demand ratios to forecast whether a Pokemon's trade value is rising, stable, or falling.

This enhancement lives entirely within `trade_analytics.py` — no new files are introduced. The
`get_market_forecast()` method returns a structured dict that includes a sentiment classification
(Bullish, Stable, or Bearish) and a trading recommendation. The `trade_market_analyst` agent
surfaces this via its `get_market_forecast` tool.

## Where It Fits

```text
Phase 6: Market Analyst (base analytics — demand ratio, success rate, trending)
        |
Phase 7: Market Forecasting (momentum layer added to TradeAnalytics)
        |
Phase 11: Multi-Agent Orchestration (Trade Advisor uses forecast in trade evaluation)
Phase 8:  Evaluations (forecast quality is measured)
```

## Key Files

| File | Role |
| --- | --- |
| `src/agents/trade_analytics.py` | `TradeAnalytics.get_market_forecast(pokemon)` — the only new method |
| `src/agents/trade_market_analyst.py` | `get_market_forecast` tool that calls `analytics.get_market_forecast()` and formats the result |

No new files are introduced in this phase.

## Key Concepts

### Momentum formula

```text
momentum = ((7d_demand_ratio - 30d_demand_ratio) / 30d_demand_ratio) * 100
```

A positive momentum score means demand is accelerating recently compared to the longer baseline. A
negative score means demand is cooling. The result is rounded to one decimal place.

### Sentiment classification

| Sentiment | Condition |
| --- | --- |
| Bullish (Rapidly Rising) | momentum > +15% |
| Bearish (Declining) | momentum < -15% |
| Stable | -15% <= momentum <= +15% |

### Recommendation mapping

The `recommendation` field is derived directly from sentiment:

```python
"Hold/Buy"        if sentiment == "Bullish"
"Sell/Trade Away" if sentiment == "Bearish"
"Neutral"         otherwise (Stable)
```

Note: the recommendation only checks for exact string `"Bullish"`, but the actual sentiment string
is `"Bullish (Rapidly Rising)"` — so Bullish trades always map to `"Neutral"` in the current code.
This is a known quirk worth noticing when reading the source.

### Time-windowed demand ratios

`get_demand_ratio(pokemon, days=7)` filters `_trades_by_pokemon[name]` to only trades where
`timestamp > now - timedelta(days=7)`, then recomputes requested/offered counts from that subset.
The 30-day window works the same way. In the mock data (which uses fixed historical timestamps),
these windows may include zero or few trades, producing `inf` ratios; `_to_float("∞")` converts
those to `float("inf")`. When `lt_ratio` is 0 or inf, momentum defaults to 0.0 to avoid division by
zero.

### Business analog

This is a simplified Moving Average Crossover — the same signal used in equity markets to detect
momentum shifts. Short-term ratio above long-term ratio = accelerating demand = Bullish.

## Exploring the Code

Read `get_market_forecast()` in `src/agents/trade_analytics.py` in full — it is about 30 lines. It
calls `get_demand_ratio()` twice (once with `days=7`, once with `days=30`), extracts the
`demand_ratio` values, converts them to floats via `_to_float()`, computes momentum, classifies
sentiment, and returns the structured dict.

Then look at the `get_market_forecast` tool in `src/agents/trade_market_analyst.py`. It formats the
returned dict into a multi-line string with explicit labels (Sentiment, Momentum Score, Short-term
Demand, Long-term Demand, Recommendation). This is what the LLM sees as the tool result.

Check `_to_float()` — it handles the `"∞"` string that `get_demand_ratio()` returns when a Pokemon
has never been offered.

## Running the Code

```bash
# Get a forecast directly from the analytics layer
cd /Users/jasmineanderson/Code/TW-Beach/katas-exercises/capstone
uv run python -c "
import sys; sys.path.insert(0, 'src')
from agents.trade_analytics import TradeAnalytics
analytics = TradeAnalytics()

for name in ['charizard', 'pikachu', 'mewtwo']:
    f = analytics.get_market_forecast(name)
    print(f'{name}: {f[\"sentiment\"]} | momentum={f[\"momentum_score\"]}% | rec={f[\"recommendation\"]}')
"

# Get short-term vs long-term ratios directly
uv run python -c "
import sys; sys.path.insert(0, 'src')
from agents.trade_analytics import TradeAnalytics
analytics = TradeAnalytics()
short = analytics.get_demand_ratio('charizard', days=7)
long  = analytics.get_demand_ratio('charizard', days=30)
print('7-day ratio:', short['demand_ratio'])
print('30-day ratio:', long['demand_ratio'])
"

# In the CLI app, ask the market analyst for a forecast:
# > market What is the forecast for Charizard?
```

Expected output from `get_market_forecast`:

```python
{
    'pokemon': 'charizard',
    'momentum_score': 0.0,       # depends on trade timestamps in the mock data
    'sentiment': 'Stable',
    'short_term_ratio': '∞',     # no trades in the last 7 days (mock data is historical)
    'long_term_ratio': '∞',
    'recommendation': 'Neutral'
}
```

## Running the Tests

Forecasting tests are in the same file as Phase 6's analytics tests:

```bash
cd /Users/jasmineanderson/Code/TW-Beach/katas-exercises/capstone
uv run pytest tests/test_trade_analytics.py -v
```

The `TestTradeAnalytics` class uses a `sample_trades` fixture with `timestamp=datetime.now()`, which
means all three trades fall within both the 7-day and 30-day windows. This allows time-windowed
tests to produce non-trivial results. You can verify the forecast behavior by constructing a
`TradeAnalytics` with the fixture directly.

To run only forecasting-adjacent tests, use `-k` to filter by keyword:

```bash
uv run pytest tests/test_trade_analytics.py -v -k "forecast or demand or sentiment"
```

## Common Gotchas

### Mock data timestamps are fixed in the past

`data/platform_trades.json` uses historical timestamps, so `get_demand_ratio(pokemon, days=7)` will
often return `"∞"` (no trades in the last 7 days). The forecast is technically correct — momentum is
0.0 when both windows have no trades — but the output may look flat for all Pokemon when using real
data. The `sample_trades` fixture in tests uses `datetime.now()`, which is why test assertions can
rely on non-trivial ratios.

### Sentiment string does not match recommendation check

The recommendation logic checks `if sentiment == "Bullish"`, but the actual sentiment string is
`"Bullish (Rapidly Rising)"`. As a result, the "Hold/Buy" recommendation is never returned — Bullish
trades produce "Neutral". This is a bug worth exploring in the source code at `trade_analytics.py`
line 120.

### `_to_float("∞")` returns `float("inf")`

When `demand_ratio` is the string `"∞"` (no offers), `_to_float` converts it to Python's
`float("inf")`. The momentum calculation guards against this with `if lt_ratio == 0 or lt_ratio ==
float("inf"): momentum = 0.0`.
