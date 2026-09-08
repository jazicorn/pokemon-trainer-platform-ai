"""Trade Market Analyst Agent - Market intelligence specialist with forecasting."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from config import config

from .trade_analytics import TradeAnalytics


class MarketDependencies(BaseModel):
    """Dependencies for the Market Analyst."""

    analytics: TradeAnalytics | None = None

    model_config = {"arbitrary_types_allowed": True}


SYSTEM_PROMPT = """You are a Pokemon trade market analyst who understands
supply and demand dynamics on the trading platform.

When answering questions:
1. Use the analytics tools to get accurate market data and forecasts.
2. Explain demand ratios and momentum—if momentum is high, the Pokemon is "Bullish".
3. Provide actionable insights: tell traders whether to Buy/Hold or Sell based on forecasts.
4. Consider trade success rates when evaluating value.

A demand ratio > 1 means high demand.
Positive momentum (> 15%) indicates a rising trend (Bullish).
Negative momentum (< -15%) indicates a declining trend (Bearish).

Be data-driven and provide specific numbers when available."""

trade_market_analyst = Agent(
    config.model_id,
    deps_type=MarketDependencies,
    system_prompt=SYSTEM_PROMPT,
)


@trade_market_analyst.tool
async def get_market_forecast(
    ctx: RunContext[MarketDependencies],
    pokemon: str,
) -> str:
    """Get a market forecast and momentum score for a Pokemon."""
    if ctx.deps.analytics is None:
        return "Analytics not available"

    forecast = ctx.deps.analytics.get_market_forecast(pokemon)

    return (
        f"Market Forecast for {pokemon.title()}:\n"
        f"- Sentiment: {forecast['sentiment']}\n"
        f"- Momentum Score: {forecast['momentum_score']}%\n"
        f"- Short-term Demand (7d): {forecast['short_term_ratio']}\n"
        f"- Long-term Demand (30d): {forecast['long_term_ratio']}\n"
        f"- Recommendation: {forecast['recommendation']}"
    )


@trade_market_analyst.tool
async def get_pokemon_demand(
    ctx: RunContext[MarketDependencies],
    pokemon: str,
) -> str:
    """Get current demand information for a Pokemon."""
    if ctx.deps.analytics is None:
        return "Analytics not available"

    demand = ctx.deps.analytics.get_demand_ratio(pokemon)

    return (
        f"{pokemon.title()} current demand analysis:\n"
        f"- Requested {demand['times_requested']} times\n"
        f"- Offered {demand['times_offered']} times\n"
        f"- Demand ratio: {demand['demand_ratio']}\n"
        f"- Demand level: {demand['demand_level']}"
    )


@trade_market_analyst.tool
async def get_trade_success(
    ctx: RunContext[MarketDependencies],
    pokemon: str,
) -> str:
    """Get trade success rate for a Pokemon."""
    if ctx.deps.analytics is None:
        return "Analytics not available"

    success = ctx.deps.analytics.get_trade_success_rate(pokemon)

    return (
        f"{pokemon.title()} trade success:\n"
        f"- Total trades: {success['total_trades']}\n"
        f"- Completed: {success['completed']}\n"
        f"- Success rate: {success['success_rate']}%"
    )


@trade_market_analyst.tool
async def get_trending(
    ctx: RunContext[MarketDependencies],
    days: int = 30,
) -> str:
    """Get trending Pokemon on the platform."""
    if ctx.deps.analytics is None:
        return "Analytics not available"

    trending = ctx.deps.analytics.get_trending_pokemon(days=days, limit=10)

    lines = [f"Trending Pokemon (last {days} days):"]
    for i, p in enumerate(trending, 1):
        lines.append(f"{i}. {p['pokemon'].title()} - {p['trade_mentions']} mentions, demand: {p['demand_level']}")

    return "\n".join(lines)


@trade_market_analyst.tool
async def compare_market_value(
    ctx: RunContext[MarketDependencies],
    pokemon_a: str,
    pokemon_b: str,
) -> str:
    """Compare market value of two Pokemon."""
    if ctx.deps.analytics is None:
        return "Analytics not available"

    cmp = ctx.deps.analytics.compare_trade_value(pokemon_a, pokemon_b)

    return (
        f"Market comparison: {pokemon_a.title()} vs {pokemon_b.title()}\n\n"
        f"{pokemon_a.title()}:\n"
        f"- Demand ratio: {cmp['pokemon_a']['demand_ratio']}\n"
        f"- Demand level: {cmp['pokemon_a']['demand_level']}\n"
        f"- Success rate: {cmp['pokemon_a']['success_rate']}%\n\n"
        f"{pokemon_b.title()}:\n"
        f"- Demand ratio: {cmp['pokemon_b']['demand_ratio']}\n"
        f"- Demand level: {cmp['pokemon_b']['demand_level']}\n"
        f"- Success rate: {cmp['pokemon_b']['success_rate']}%\n\n"
        f"Conclusion: {cmp['value_comparison']}"
    )


@trade_market_analyst.tool
async def get_high_demand_pokemon(
    ctx: RunContext[MarketDependencies],
) -> str:
    """Get Pokemon that are in high demand."""
    if ctx.deps.analytics is None:
        return "Analytics not available"

    most_requested = ctx.deps.analytics.get_most_requested(limit=10)

    lines = ["Most requested Pokemon:"]
    for i, p in enumerate(most_requested, 1):
        demand = ctx.deps.analytics.get_demand_ratio(p["pokemon"])
        lines.append(
            f"{i}. {p['pokemon'].title()} - {p['request_count']} requests, demand ratio: {demand['demand_ratio']}"
        )

    return "\n".join(lines)


async def query_market(question: str) -> str:
    """Query the Market Analyst."""
    analytics = TradeAnalytics()
    deps = MarketDependencies(analytics=analytics)

    result = await trade_market_analyst.run(question, deps=deps)
    return str(result.output)
