"""Fetch and cache Pokemon data from PokeAPI."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from typing import Any

POKEAPI_BASE = "https://pokeapi.co/api/v2"
RATE_LIMIT_DELAY = 0.5


def get_cache_dir() -> Path:
    """Get the Pokemon cache directory."""
    cache_dir = Path(__file__).parent.parent.parent / "data" / "pokemon_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _read_cache(cache_file: Path) -> dict[str, Any] | None:
    """Read data from cache file if it exists."""
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    return None


def _write_cache(cache_file: Path, data: dict[str, Any]) -> None:
    """Write data to cache file."""
    with open(cache_file, "w") as f:
        json.dump(data, f)


def _fetch_from_api(url: str) -> dict[str, Any] | None:
    """Fetch data from PokeAPI with rate limiting."""
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        time.sleep(RATE_LIMIT_DELAY)
        return response.json()
    except httpx.HTTPError as e:
        print(f"Error fetching {url}: {e}")
        return None


def fetch_pokemon(name: str) -> dict[str, Any] | None:
    """Fetch Pokemon data from PokeAPI or cache."""
    cache_file = get_cache_dir() / f"{name.lower()}.json"

    if cached := _read_cache(cache_file):
        return cached

    if data := _fetch_from_api(f"{POKEAPI_BASE}/pokemon/{name.lower()}"):
        _write_cache(cache_file, data)
        return data

    return None


def fetch_pokemon_species(name: str) -> dict[str, Any] | None:
    """Fetch Pokemon species data for flavor text and evolution."""
    cache_file = get_cache_dir() / f"{name.lower()}_species.json"

    if cached := _read_cache(cache_file):
        return cached

    if data := _fetch_from_api(f"{POKEAPI_BASE}/pokemon-species/{name.lower()}"):
        _write_cache(cache_file, data)
        return data

    return None


def extract_pokemon_info(
    pokemon_data: dict[str, Any],
    species_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Extract relevant info for RAG indexing."""
    stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon_data["stats"]}
    types = [t["type"]["name"] for t in pokemon_data["types"]]
    abilities = [a["ability"]["name"] for a in pokemon_data["abilities"]]

    info: dict[str, Any] = {
        "name": pokemon_data["name"],
        "id": pokemon_data["id"],
        "types": types,
        "stats": stats,
        "abilities": abilities,
        "height": pokemon_data["height"],
        "weight": pokemon_data["weight"],
        "base_experience": pokemon_data.get("base_experience", 0),
    }

    if species_data:
        flavor_texts = [
            ft["flavor_text"]
            for ft in species_data.get("flavor_text_entries", [])
            if ft["language"]["name"] == "en"
        ]
        if flavor_texts:
            info["description"] = flavor_texts[0].replace("\n", " ")

        info["is_legendary"] = species_data.get("is_legendary", False)
        info["is_mythical"] = species_data.get("is_mythical", False)
        info["generation"] = species_data.get("generation", {}).get("name", "")

    return info


def fetch_and_process_pokemon(names: list[str]) -> list[dict[str, Any]]:
    """Fetch and process multiple Pokemon."""
    results = []
    for name in names:
        print(f"Fetching {name}...")
        if pokemon_data := fetch_pokemon(name):
            species_data = fetch_pokemon_species(name)
            results.append(extract_pokemon_info(pokemon_data, species_data))
    return results
