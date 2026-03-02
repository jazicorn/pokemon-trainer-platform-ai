"""Ingest Pokemon data into the vector store."""

from .pokeapi_fetcher import fetch_and_process_pokemon
from .smogon_fetcher import get_tier_map
from .vector_store import PokemonVectorStore

POKEMON_TO_INDEX = [
    "pikachu", "charizard", "blastoise", "venusaur", "dragonite",
    "alakazam", "machamp", "gengar", "gyarados", "lapras",
    "snorlax", "eevee", "vaporeon", "jolteon", "flareon",
    "mewtwo", "mew", "articuno", "zapdos", "moltres",
    "tyranitar", "salamence", "metagross", "garchomp", "lucario",
    "absol", "gardevoir", "aggron", "flygon", "milotic",
    "geodude", "machop", "abra", "gastly", "magikarp",
    "dratini", "larvitar", "bagon", "beldum", "gible",
]


def ingest_pokemon_data() -> int:
    """Fetch Pokemon data and ingest into the pokemon vector store.

    Enriches each Pokemon document with its Smogon competitive tier before
    ingestion, and triggers the Smogon strategy ingest as a second pass.

    Returns:
        Number of Pokemon ingested.
    """
    from .smogon_ingest import ingest_smogon_data

    print("Fetching Pokemon data from PokeAPI...")
    pokemon_data = fetch_and_process_pokemon(POKEMON_TO_INDEX)
    print(f"Fetched {len(pokemon_data)} Pokemon")

    print("Fetching Smogon tier data...")
    tier_map = get_tier_map()

    # Enrich each Pokemon dict with its competitive tier before ingestion.
    for p in pokemon_data:
        p["smogon_tier"] = tier_map.get(p["name"].lower(), "Unknown")

    print("Ingesting into pokemon vector store...")
    store = PokemonVectorStore()
    try:
        store.add_pokemon(pokemon_data)
    finally:
        store.close()

    print("Ingesting Smogon strategy data...")
    ingest_smogon_data()

    print("Ingestion complete!")
    return len(pokemon_data)


if __name__ == "__main__":
    ingest_pokemon_data()
    