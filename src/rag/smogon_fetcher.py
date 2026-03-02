"""Fetch and cache Pokemon competitive data from pkmn.github.io/smogon (Smogon mirror)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from typing import Any

from config import config
from data.tiers import TIER_FORMATS

SMOGON_BASE: str = config.smogon_url
SMOGON_FETCH_TIMEOUT_S: float = 15.0

ANALYSES_FORMATS: list[str] = ["gen9ou", "gen9uu", "gen9nu"]


def get_smogon_cache_dir() -> Path:
    """Get (or create) the Smogon cache directory."""
    cache_dir = Path(__file__).parent.parent.parent / "data" / "smogon_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _read_cache(cache_file: Path) -> Any | None:
    """Return parsed JSON from cache file, or None if missing."""
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    return None


def _write_cache(cache_file: Path, data: Any) -> None:
    """Write data as JSON to cache file."""
    with open(cache_file, "w") as f:
        json.dump(data, f)


def _fetch_json(path: str) -> Any | None:
    """Fetch JSON from data.pkmn.cc. Returns None on any error."""
    url = f"{SMOGON_BASE}/{path}.json"
    try:
        response = httpx.get(url, timeout=SMOGON_FETCH_TIMEOUT_S)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning("Error fetching %s: %s", url, e)
        return None


def get_tier_map() -> dict[str, str]:
    """Return a mapping of lowercase Pokemon name → Smogon tier string.

    Tiers are assigned by checking each format in priority order (Uber → OU →
    UU → RU → NU → PU). The first format a Pokemon appears in wins.
    Results are cached to smogon_cache/tiers.json.
    """
    cache_file = get_smogon_cache_dir() / "tiers.json"
    if cached := _read_cache(cache_file):
        return cached

    logger.info("Building tier map from pkmn.github.io/smogon...")
    tier_map: dict[str, str] = {}

    for tier_name, path in TIER_FORMATS:
        data = _fetch_json(path)
        if not data:
            continue
        for pokemon_name in data:
            key = pokemon_name.lower()
            if key not in tier_map:  # highest tier already assigned
                tier_map[key] = tier_name

    if tier_map:
        _write_cache(cache_file, tier_map)
        logger.info("Cached tiers for %d Pokemon.", len(tier_map))

    return tier_map


def get_sets(format_id: str = "gen9ou") -> dict[str, Any]:
    """Return the full sets dict for a given format, using cache.

    Keys are Pokemon names (may be capitalised). Values are dicts of
    set-name → moveset details (moves, ability, item, EVs, nature).
    """
    cache_file = get_smogon_cache_dir() / f"{format_id}_sets.json"
    if cached := _read_cache(cache_file):
        return cached

    logger.info("Fetching sets for %s...", format_id)
    data = _fetch_json(f"sets/{format_id}")
    if data:
        _write_cache(cache_file, data)
    return data or {}


def get_analyses(format_id: str = "gen9ou") -> dict[str, Any]:
    """Return strategy analyses for a given format, using cache.

    Keys are Pokemon names. Values contain overview text and move/set comments.
    """
    cache_file = get_smogon_cache_dir() / f"{format_id}_analyses.json"
    if cached := _read_cache(cache_file):
        return cached

    logger.info("Fetching analyses for %s...", format_id)
    data = _fetch_json(f"analyses/{format_id}")
    if data:
        _write_cache(cache_file, data)
    return data or {}
