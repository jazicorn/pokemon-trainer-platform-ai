"""Mock data generators — produce realistic platform trade history and user
collections to develop and test against.

Run directly to (re)write both JSON files under ``data/``:

    uv run python -m src.data.generator
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Pokemon rarity pools
# ---------------------------------------------------------------------------

_COMMON: frozenset[str] = frozenset(
    {
        "pikachu",
        "eevee",
        "bulbasaur",
        "charmander",
        "squirtle",
        "caterpie",
        "pidgey",
        "rattata",
        "jigglypuff",
        "meowth",
        "psyduck",
        "growlithe",
        "poliwag",
        "abra",
        "machop",
        "geodude",
        "magnemite",
        "gastly",
        "onix",
        "voltorb",
        "koffing",
        "rhyhorn",
        "horsea",
        "goldeen",
        "staryu",
        "magikarp",
        "vulpix",
        "oddish",
        "bellsprout",
        "tentacool",
        "shellder",
        "drowzee",
        "krabby",
        "spearow",
        "ekans",
        "sandshrew",
        "nidoran-f",
        "nidoran-m",
        "diglett",
        "grimer",
        "cubone",
        "lickitung",
        "chansey",
        "tangela",
        "kangaskhan",
        "mr-mime",
        "scyther",
        "jynx",
        "electabuzz",
        "magmar",
        "pinsir",
        "tauros",
        "gyarados",
        "lapras",
        "ditto",
        "snorlax",
        "charizard",
        "blastoise",
        "venusaur",
        "alakazam",
        "machamp",
        "golem",
        "gengar",
        "dragonite",
    }
)

_PSEUDO_LEGENDARY: frozenset[str] = frozenset(
    {
        "dragonite",
        "tyranitar",
        "salamence",
        "metagross",
        "garchomp",
        "hydreigon",
        "goodra",
        "kommo-o",
        "dragapult",
        "baxcalibur",
    }
)

_MYTHICAL: frozenset[str] = frozenset(
    {
        "mew",
        "celebi",
        "jirachi",
        "deoxys",
        "darkrai",
        "shaymin",
        "arceus",
        "victini",
        "genesect",
        "hoopa",
        "marshadow",
        "zeraora",
    }
)

_LEGENDARY: frozenset[str] = frozenset(
    {
        "articuno",
        "zapdos",
        "moltres",
        "mewtwo",
        "raikou",
        "entei",
        "suicune",
        "lugia",
        "ho-oh",
        "regirock",
        "regice",
        "registeel",
        "latias",
        "latios",
        "kyogre",
        "groudon",
        "rayquaza",
        "dialga",
        "palkia",
        "giratina",
        "reshiram",
        "zekrom",
        "kyurem",
        "xerneas",
        "yveltal",
        "zygarde",
        "solgaleo",
        "lunala",
        "necrozma",
        "zacian",
        "zamazenta",
        "eternatus",
        "calyrex",
        "koraidon",
        "miraidon",
    }
)

# Extra named Pokemon that round out the "all_pokemon" pool but aren't
# rarity-tiered (treated as common for trade-outcome weighting).
_EXTRA_NAMED: frozenset[str] = frozenset(
    {
        "umbreon",
        "espeon",
        "sylveon",
        "glaceon",
        "leafeon",
        "vaporeon",
        "jolteon",
        "flareon",
        "mimikyu",
        "toxapex",
        "ferrothorn",
        "corviknight",
        "greninja",
        "lucario",
    }
)

_POKEMON_TYPES: tuple[str, ...] = (
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
)

_TRADING_STYLES: tuple[str, ...] = ("collection_focused", "competitive_focused", "balanced")

_GOALS: tuple[str, ...] = (
    "Complete my Dragon collection",
    "Build a competitive OU team",
    "Complete the national Pokedex",
    "Collect every starter evolution",
    "Complete_gen1",
)

_ACQUIRED_VIA: tuple[str, ...] = ("trade", "catch", "gift", "evolution")

_USER_IDS: tuple[str, ...] = tuple(f"user_{i:03d}" for i in range(1, 11))


@dataclass(frozen=True)
class PokemonRarity:
    """Rarity tiers used to generate believable, rarity-weighted trade outcomes."""

    legendary: frozenset[str] = _LEGENDARY
    mythical: frozenset[str] = _MYTHICAL
    pseudo_legendary: frozenset[str] = _PSEUDO_LEGENDARY
    common: frozenset[str] = _COMMON
    extra_named: frozenset[str] = _EXTRA_NAMED

    @property
    def all_pokemon(self) -> list[str]:
        """Every named Pokemon across all rarity tiers."""
        return list(self.legendary | self.mythical | self.pseudo_legendary | self.common | self.extra_named)

    def get_trade_success_rate(self, pokemon: str) -> tuple[list[str], list[float]]:
        """Return (statuses, weights) for ``random.choices`` based on rarity.

        Legendaries and Mythicals are rejected 80% of the time, pseudo-legendaries
        60%, and common Pokemon are completed 70% of the time.
        """
        name = pokemon.lower()
        statuses = ["completed", "pending", "rejected", "cancelled"]

        if name in self.legendary or name in self.mythical:
            weights = [0.10, 0.05, 0.80, 0.05]
        elif name in self.pseudo_legendary:
            weights = [0.25, 0.10, 0.60, 0.05]
        else:
            weights = [0.70, 0.15, 0.10, 0.05]

        return statuses, weights


RARITY = PokemonRarity()


# ---------------------------------------------------------------------------
# Platform trade generation
# ---------------------------------------------------------------------------


def _create_trade(trade_index: int, timestamp: datetime) -> dict[str, Any]:
    """Build a single trade record with a rarity-weighted outcome."""
    pool = RARITY.all_pokemon
    offered, requested = random.sample(pool, 2)

    user_a_id, user_b_id = random.sample(_USER_IDS, 2)

    statuses, weights = RARITY.get_trade_success_rate(offered)
    status = random.choices(statuses, weights=weights, k=1)[0]

    return {
        "trade_id": f"t{trade_index:04d}",
        "timestamp": timestamp.isoformat(),
        "offered_pokemon": offered,
        "requested_pokemon": requested,
        "status": status,
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
    }


def generate_platform_trades(num_trades: int = 200) -> dict[str, Any]:
    """Generate ``num_trades`` mock platform trades, sorted chronologically."""
    now = datetime.now()
    timestamps = sorted(now - timedelta(minutes=random.randint(0, 60 * 24 * 90)) for _ in range(num_trades))

    trades = [_create_trade(i, ts) for i, ts in enumerate(timestamps, start=1)]

    return {"trades": trades}


# ---------------------------------------------------------------------------
# User collection generation
# ---------------------------------------------------------------------------


def generate_user_collection(user_id: str = "user_001") -> dict[str, Any]:
    """Generate a mock collection + preferences for a single user.

    The seeking list is computed as a set difference against owned Pokemon so
    the two are always disjoint.
    """
    pool = RARITY.all_pokemon
    owned_count = random.randint(8, 15)
    owned_names = random.sample(pool, owned_count)

    pokemon: list[dict[str, Any]] = []
    for name in owned_names:
        is_legendary_or_mythical = name in RARITY.legendary or name in RARITY.mythical
        acquired_date = datetime.now() - timedelta(days=random.randint(1, 700))
        pokemon.append(
            {
                "pokemon_id": name,
                "nickname": None,
                "acquired_date": acquired_date.date().isoformat(),
                "acquired_via": random.choice(_ACQUIRED_VIA),
                "tradeable": not is_legendary_or_mythical or random.random() < 0.2,
                "is_shiny": random.random() < 0.05,
                "ball_type": "cherish" if is_legendary_or_mythical and random.random() < 0.3 else None,
            }
        )

    remaining_pool = [p for p in pool if p not in owned_names]
    seeking = random.sample(remaining_pool, min(3, len(remaining_pool)))

    never_trade = random.sample(owned_names, min(1, len(owned_names))) if random.random() < 0.5 else []

    preferences = {
        "favorite_types": random.sample(_POKEMON_TYPES, 2),
        "goal": random.choice(_GOALS),
        "trading_style": random.choice(_TRADING_STYLES),
        "never_trade": never_trade,
        "seeking": seeking,
    }

    return {
        "user_id": user_id,
        "pokemon": pokemon,
        "preferences": preferences,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_mock_data(data_dir: Path, user_id: str = "user_001", num_trades: int = 200) -> None:
    """Generate both mock data files and write them under ``data_dir``."""
    data_dir.mkdir(parents=True, exist_ok=True)

    platform_trades = generate_platform_trades(num_trades=num_trades)
    (data_dir / "platform_trades.json").write_text(json.dumps(platform_trades, indent=2))

    user_collection = generate_user_collection(user_id=user_id)
    (data_dir / "user_collection.json").write_text(json.dumps(user_collection, indent=2))


if __name__ == "__main__":
    _project_root = Path(__file__).resolve().parent.parent.parent
    save_mock_data(_project_root / "data")
    print(f"Wrote platform_trades.json and user_collection.json to {_project_root / 'data'}")
