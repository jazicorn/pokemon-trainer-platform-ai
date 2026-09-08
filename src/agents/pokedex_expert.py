"""Pokedex Expert Agent - Pokemon knowledge specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from data.loader import load_user_collection
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from config import config
from rag.vector_store import PokemonVectorStore

if TYPE_CHECKING:
    pass


class PokedexDependencies(BaseModel):
    """Dependencies for the Pokedex Expert."""

    vector_store: PokemonVectorStore | None = None
    user_id: str = "user_001"

    model_config = {"arbitrary_types_allowed": True}


# Type effectiveness chart (simplified)
TYPE_CHART: dict[tuple[str, str], str] = {
    ("fire", "grass"): "super effective (2x)",
    ("fire", "water"): "not very effective (0.5x)",
    ("water", "fire"): "super effective (2x)",
    ("water", "grass"): "not very effective (0.5x)",
    ("grass", "water"): "super effective (2x)",
    ("grass", "fire"): "not very effective (0.5x)",
    ("electric", "water"): "super effective (2x)",
    ("electric", "grass"): "not very effective (0.5x)",
    ("psychic", "fighting"): "super effective (2x)",
    ("psychic", "psychic"): "not very effective (0.5x)",
    ("fighting", "psychic"): "not very effective (0.5x)",
    ("ghost", "psychic"): "super effective (2x)",
    ("ghost", "ghost"): "super effective (2x)",
    ("dragon", "dragon"): "super effective (2x)",
    ("ice", "dragon"): "super effective (2x)",
    ("fairy", "dragon"): "super effective (2x)",
    ("dark", "psychic"): "super effective (2x)",
    ("steel", "fairy"): "super effective (2x)",
}

SYSTEM_PROMPT = """You are a Pokemon expert with deep knowledge of all Pokemon
species, their stats, types, abilities, and competitive viability.

You also have access to the user's personal collection. When asked about "my pokemon"
or "what I have", use the get_my_collection tool.

When answering questions:
1. Use the retrieved Pokemon data to provide accurate information.
2. Compare stats objectively when asked to compare Pokemon.
3. Explain type matchups and their implications.
4. Consider competitive viability when relevant.

Be concise but thorough. Always base your answers on the retrieved data."""

pokedex_expert = Agent(
    config.model_id,
    deps_type=PokedexDependencies,
    system_prompt=SYSTEM_PROMPT,
)


@pokedex_expert.tool
async def search_pokemon(
    ctx: RunContext[PokedexDependencies],
    query: str,
) -> str:
    """Search for Pokemon information in the knowledge base."""
    if ctx.deps.vector_store is None:
        return "Vector store not available"

    results = ctx.deps.vector_store.query(query, n_results=3)

    if not results:
        return "No Pokemon found matching that query."

    return "\n\n".join(r["document"] for r in results)


@pokedex_expert.tool
async def get_type_effectiveness(
    ctx: RunContext[PokedexDependencies],
    attacking_type: str,
    defending_type: str,
) -> str:
    """Get type effectiveness for a matchup."""
    key = (attacking_type.lower(), defending_type.lower())
    effectiveness = TYPE_CHART.get(key, "normal effectiveness (1x)")
    return f"{attacking_type} vs {defending_type}: {effectiveness}"


@pokedex_expert.tool
async def get_my_collection(ctx: RunContext[PokedexDependencies]) -> str:
    """Get information about the user's personal Pokemon collection and their goals."""
    collection = load_user_collection(ctx.deps.user_id)

    pkmn_strings: list[str] = []
    for p in collection.pokemon:
        display_name = f"{p.nickname} ({p.pokemon_id})" if p.nickname else p.pokemon_id
        trade_status = "Tradeable" if p.tradeable else "NFT (Not for trade)"
        pkmn_strings.append(f"- {display_name} [{trade_status}]")

    prefs = collection.preferences
    goal = getattr(prefs, "goal", "No specific goal set")
    seeking_list = getattr(prefs, "seeking", [])
    seeking = ", ".join(seeking_list) if seeking_list else "Nothing specific"

    return (
        f"User '{ctx.deps.user_id}' has {len(pkmn_strings)} Pokemon in their collection:\n"
        + "\n".join(pkmn_strings)
        + f"\n\nCurrent Goal: {goal}"
        f"\nCurrently Seeking: {seeking}"
    )


async def query_pokedex(question: str, user_id: str = "user_001") -> str:
    """Query the Pokedex Expert."""
    store = PokemonVectorStore()
    deps = PokedexDependencies(vector_store=store, user_id=user_id)

    try:
        result = await pokedex_expert.run(question, deps=deps)
        return str(result.output)
    finally:
        store.close()
