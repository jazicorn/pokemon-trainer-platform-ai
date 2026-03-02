"""Battle Strategy Advisor Agent - Competitive Pokemon viability specialist."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from config import config
from rag.smogon_fetcher import get_sets, get_tier_map
from rag.vector_store import PokemonVectorStore


class BattleDependencies(BaseModel):
    """Dependencies for the Battle Strategy Advisor."""

    strategy_store: PokemonVectorStore | None = None

    model_config = {"arbitrary_types_allowed": True}


SYSTEM_PROMPT = """You are a competitive Pokemon battle strategy advisor with deep knowledge
of the Smogon competitive metagame.

You specialise in:
- Competitive tier placements (Uber, OU, UU, RU, NU, PU) and what they mean
- Recommended movesets, EV spreads, natures, and held items
- Why a Pokemon is valued or undervalued in the current meta
- How competitive viability affects trade value

When answering questions:
1. Always state the Pokemon's Smogon tier upfront.
2. Provide the most commonly used competitive set(s) with EVs, nature, and moves.
3. Explain the role the Pokemon fills (wallbreaker, tank, revenge killer, etc.).
4. Note if a Pokemon is Uber-banned (too strong for standard OU play) — this
   affects trade value differently than being low-tier.

Be concise and data-driven. Base all answers on retrieved Smogon data."""

battle_strategy_advisor = Agent(
    config.model_id,
    deps_type=BattleDependencies,
    system_prompt=SYSTEM_PROMPT,
)


@battle_strategy_advisor.tool
async def get_competitive_moveset(
    ctx: RunContext[BattleDependencies],
    pokemon_name: str,
    format_id: str = "gen9ou",
) -> str:
    """Retrieve competitive moveset recommendations for a Pokemon.

    Queries the smogon_strategy vector store for the most relevant sets
    and strategy overview for the given Pokemon and format.
    """
    if ctx.deps.strategy_store is None:
        return "Strategy data not available."

    results = ctx.deps.strategy_store.query(
        f"competitive moveset for {pokemon_name}", n_results=3
    )
    if not results:
        # Fall back to cached sets JSON if vector store has no match
        sets = get_sets(format_id)
        # sets keys may be capitalised — normalise once for O(1) lookup
        sets_lower = {k.lower(): v for k, v in sets.items()}
        match = sets_lower.get(pokemon_name.lower())
        if not match:
            return f"No competitive sets found for {pokemon_name} in {format_id}."
        lines = [f"Sets for {pokemon_name} in {format_id}:"]
        for set_name, moveset in match.items():
            lines.append(f"  {set_name}: {moveset}")
        return "\n".join(lines)

    return "\n\n".join(r["document"] for r in results)


@battle_strategy_advisor.tool
async def get_tier(
    ctx: RunContext[BattleDependencies],
    pokemon_name: str,
) -> str:
    """Return the Smogon competitive tier for a Pokemon."""
    tier_map = get_tier_map()
    tier = tier_map.get(pokemon_name.lower(), "Unknown")
    if tier == "Unknown":
        return (
            f"{pokemon_name} has no Smogon tier data — it may be untiered or "
            "not present in the indexed formats. It likely has very low competitive use."
        )
    return f"{pokemon_name} is tiered {tier} in the Smogon competitive metagame."


async def query_battle_strategy(question: str) -> str:
    """Query the Battle Strategy Advisor with a natural language question."""
    store = PokemonVectorStore(collection_name="smogon_strategy")
    deps = BattleDependencies(strategy_store=store)

    try:
        result = await battle_strategy_advisor.run(question, deps=deps)
        return str(result.output)
    finally:
        store.close()
