"""Ingest Smogon competitive data into the smogon_strategy ChromaDB collection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from .smogon_fetcher import ANALYSES_FORMATS, get_analyses, get_sets, get_tier_map
from .vector_store import PokemonVectorStore, get_embedding

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

# Formats to ingest. OU is the primary competitive tier; uu/nu are included so
# Pokemon absent from OU still get strategy documents.
_INGEST_FORMATS = ANALYSES_FORMATS

# Maximum characters of the strategy overview to include per document.
STRATEGY_OVERVIEW_MAX_LEN: int = 500


@dataclass
class StrategyDocument:
    """A single competitive strategy document ready for ChromaDB ingestion."""

    id: str
    text: str
    metadata: dict[str, str]
    embedding: list[float]


def _build_strategy_document(
    pokemon_name: str,
    sets_data: dict[str, Any],
    analysis_data: dict[str, Any] | None,
    tier: str,
    format_id: str,
) -> str:
    """Build a searchable text document from Smogon sets and analysis."""
    parts = [
        f"Pokemon: {pokemon_name}",
        f"Format: {format_id}",
        f"Competitive Tier (Smogon): {tier}",
    ]

    # Sets — each named moveset becomes a section
    for set_name, moveset in sets_data.items():
        moves = moveset.get("moves", [])
        # moves can be lists of options (["move1", "move2"]) or plain strings
        move_strs: list[str] = []
        for m in moves:
            move_strs.append(m if isinstance(m, str) else "/".join(m))

        set_parts = [f"Set '{set_name}':"]
        if moveset.get("item"):
            item = moveset["item"]
            set_parts.append(f"Item: {item if isinstance(item, str) else '/'.join(item)}")
        if moveset.get("ability"):
            ability = moveset["ability"]
            set_parts.append(f"Ability: {ability if isinstance(ability, str) else '/'.join(ability)}")
        if moveset.get("nature"):
            nature = moveset["nature"]
            set_parts.append(f"Nature: {nature if isinstance(nature, str) else '/'.join(nature)}")
        if moveset.get("evs"):
            evs = moveset["evs"]
            ev_str = (
                ", ".join(f"{v} {k}" for k, v in cast(dict[str, int], evs).items())
                if isinstance(evs, dict)
                else str(evs)
            )
            set_parts.append(f"EVs: {ev_str}")
        if move_strs:
            set_parts.append(f"Moves: {', '.join(move_strs)}")

        parts.append(" | ".join(set_parts))

    # Analysis overview — trimmed to keep document size manageable
    if analysis_data:
        overview = analysis_data.get("overview", "")
        if overview and isinstance(overview, str):
            parts.append(f"Strategy overview: {overview[:STRATEGY_OVERVIEW_MAX_LEN]}")

    return "\n".join(parts)


def ingest_smogon_data(formats: list[str] | None = None) -> int:
    """Fetch Smogon sets and analyses and ingest into the smogon_strategy collection.

    Args:
        formats: List of format IDs to ingest (default: ANALYSES_FORMATS).

    Returns:
        Number of documents ingested.
    """
    formats = formats or _INGEST_FORMATS
    tier_map = get_tier_map()

    store = PokemonVectorStore(collection_name="smogon_strategy")
    docs: list[StrategyDocument] = []

    for format_id in formats:
        logger.info("Processing format %s...", format_id)
        sets_by_pokemon = get_sets(format_id)
        analyses_by_pokemon = get_analyses(format_id)

        if not sets_by_pokemon:
            logger.warning("No sets returned for format %s — skipping.", format_id)
            continue

        for pokemon_name, sets_data in sets_by_pokemon.items():
            name_lower = pokemon_name.lower()
            tier = tier_map.get(name_lower, "Unknown")
            analysis = analyses_by_pokemon.get(pokemon_name)

            doc_text = _build_strategy_document(pokemon_name, sets_data, analysis, tier, format_id)
            docs.append(
                StrategyDocument(
                    id=f"{name_lower}_{format_id}",
                    text=doc_text,
                    metadata={"name": name_lower, "format": format_id, "smogon_tier": tier},
                    embedding=get_embedding(doc_text),
                )
            )

    if not docs:
        logger.warning("No documents to ingest — Smogon data may be unavailable.")
        store.close()
        return 0

    try:
        store.add_documents(
            ids=[d.id for d in docs],
            documents=[d.text for d in docs],
            metadatas=[d.metadata for d in docs],
            embeddings=[d.embedding for d in docs],
        )
    finally:
        store.close()

    logger.info("Ingested %d strategy documents.", len(docs))
    return len(docs)
