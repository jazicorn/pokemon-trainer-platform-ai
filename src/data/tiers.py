"""Smogon competitive tier constants shared by the fetcher and the value scorer."""

from __future__ import annotations

# (tier name, pkmn.github.io/smogon data path) pairs, in priority order.
# `smogon_fetcher.get_tier_map()` walks these top to bottom and assigns each
# Pokemon the first (highest) tier it appears in.
#
# Path is `sets/<format-id>` — the same `/sets` endpoint `get_sets()` already
# uses (data.pkmn.cc's API only exposes analyses/formats/imgs/sets/stats/teams;
# there is no separate "formats-data" endpoint). `sets/<format-id>.json` is
# keyed directly by Pokemon name for that single format, which is exactly the
# per-tier species list we need. Verified against the live API on 2026-09-08.
TIER_FORMATS: list[tuple[str, str]] = [
    ("Uber", "sets/gen9ubers"),
    ("OU", "sets/gen9ou"),
    ("UU", "sets/gen9uu"),
    ("RU", "sets/gen9ru"),
    ("NU", "sets/gen9nu"),
    ("PU", "sets/gen9pu"),
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
