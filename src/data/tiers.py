"""Smogon competitive tier constants shared by the fetcher and the value scorer."""

from __future__ import annotations

# (tier name, pkmn.github.io/smogon data path) pairs, in priority order.
# `smogon_fetcher.get_tier_map()` walks these top to bottom and assigns each
# Pokemon the first (highest) tier it appears in.
TIER_FORMATS: list[tuple[str, str]] = [
    ("Uber", "formats-data/gen9ubers"),
    ("OU", "formats-data/gen9ou"),
    ("UU", "formats-data/gen9uu"),
    ("RU", "formats-data/gen9ru"),
    ("NU", "formats-data/gen9nu"),
    ("PU", "formats-data/gen9pu"),
]

# Battle-score points awarded per competitive tier, used by
# `data.value_scoring.score_summary()`. Higher tier = stronger competitively
# = higher score. "Unknown" is the fallback for Pokemon with no Smogon data.
TIER_SCORES: dict[str, int] = {
    "Uber": 100,
    "OU": 85,
    "UU": 65,
    "RU": 50,
    "NU": 35,
    "PU": 20,
    "Unknown": 10,
}
