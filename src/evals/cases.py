"""Evaluation test cases for the Pokemon Trade Advisor."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TradeCase:
    """A trade evaluation case."""

    id: str
    offered: str
    requested: str
    description: str
    expected_keywords: tuple[str, ...]
    is_good_trade: bool | None = None  # None = depends on context


@dataclass(frozen=True)
class KnowledgeCase:
    """A Pokemon knowledge evaluation case."""

    id: str
    question: str
    expected_keywords: tuple[str, ...]
    pokemon: str


# Trade evaluation cases
TRADE_CASES: tuple[TradeCase, ...] = (
    TradeCase(
        id="obvious_good_trade",
        offered="geodude",
        requested="dragonite",
        description="Trading common for pseudo-legendary",
        expected_keywords=("accept", "recommend", "dragonite", "valuable"),
        is_good_trade=True,
    ),
    TradeCase(
        id="obvious_bad_trade",
        offered="dragonite",
        requested="geodude",
        description="Trading pseudo-legendary for common",
        expected_keywords=("decline", "against", "dragonite", "valuable"),
        is_good_trade=False,
    ),
    TradeCase(
        id="equal_value_trade",
        offered="alakazam",
        requested="gengar",
        description="Trading similar power Pokemon",
        expected_keywords=("similar", "equal", "preference", "both"),
        is_good_trade=None,
    ),
    TradeCase(
        id="legendary_request",
        offered="pikachu",
        requested="mewtwo",
        description="Requesting legendary for common",
        expected_keywords=("legendary", "rare", "unlikely", "mewtwo"),
        is_good_trade=False,
    ),
)

# Pokemon knowledge cases
KNOWLEDGE_CASES: tuple[KnowledgeCase, ...] = (
    KnowledgeCase(
        id="charizard_types",
        question="What are Charizard's types?",
        expected_keywords=("fire", "flying"),
        pokemon="charizard",
    ),
    KnowledgeCase(
        id="mewtwo_legendary",
        question="Is Mewtwo a legendary Pokemon?",
        expected_keywords=("legendary", "yes", "psychic"),
        pokemon="mewtwo",
    ),
    KnowledgeCase(
        id="pikachu_evolution",
        question="What does Pikachu evolve from?",
        expected_keywords=("pichu", "electric"),
        pokemon="pikachu",
    ),
    KnowledgeCase(
        id="dragonite_stats",
        question="What are Dragonite's best stats?",
        expected_keywords=("attack", "dragon", "flying"),
        pokemon="dragonite",
    ),
)
