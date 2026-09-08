"""Dual value scoring for trade evaluation: collector score and battle score.

Collector score is driven by rarity (Mythical > Legendary > Standard). Battle
score is driven by competitive Smogon tier. The two are intentionally kept
separate and context-free — interpreting which one matters more for a given
trade is the Trade Advisor's job (it looks at the user's trading_style/goal).
"""

from __future__ import annotations

from typing import Any

from agents.legitimacy_guard import LEGENDARIES, MYTHICALS
from data.tiers import TIER_SCORES

# Collector-score points per rarity tier.
_RARITY_SCORES: dict[str, int] = {
    "mythical": 100,
    "legendary": 80,
    "standard": 40,
}


def get_collector_score(pokemon: str) -> int:
    """Score a Pokemon's collector value by rarity tier (Mythical > Legendary > Standard)."""
    name = pokemon.lower()
    if name in MYTHICALS:
        return _RARITY_SCORES["mythical"]
    if name in LEGENDARIES:
        return _RARITY_SCORES["legendary"]
    return _RARITY_SCORES["standard"]


def get_battle_score(pokemon: str, tier_map: dict[str, str]) -> tuple[int, str]:
    """Score a Pokemon's competitive value from its Smogon tier.

    Returns (score, tier_name). Pokemon absent from tier_map score as "Unknown".
    """
    tier = tier_map.get(pokemon.lower(), "Unknown")
    return TIER_SCORES.get(tier, TIER_SCORES["Unknown"]), tier


def score_summary(pokemon: str, tier_map: dict[str, str]) -> dict[str, Any]:
    """Return collector_score, battle_score, and smogon_tier for one Pokemon."""
    battle_score, tier = get_battle_score(pokemon, tier_map)
    return {
        "collector_score": get_collector_score(pokemon),
        "battle_score": battle_score,
        "smogon_tier": tier,
    }
