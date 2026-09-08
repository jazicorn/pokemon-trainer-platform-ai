"""Public API functions for the Trade Advisor."""

from __future__ import annotations

import asyncio
from typing import Any

from data.loader import load_user_collection

from rag.vector_store import PokemonVectorStore

# Import tools module to ensure all @trade_advisor.tool decorators are executed.
from . import trade_advisor_tools  # noqa: F401  # pyright: ignore[reportUnusedImport]
from .trade_advisor_core import AdvisorDependencies, trade_advisor
from .trade_analytics import TradeAnalytics


def _build_advisor_deps(
    user_id: str,
    conversation_context: str | None = None,
) -> AdvisorDependencies:
    """Create a fully-populated AdvisorDependencies for a single request.

    Fetches the tier map once so all tools within the same request share it
    without redundant disk I/O.
    """
    from rag.smogon_fetcher import get_tier_map

    return AdvisorDependencies(
        vector_store=PokemonVectorStore(),
        strategy_store=PokemonVectorStore(collection_name="smogon_strategy"),
        analytics=TradeAnalytics(),
        user_collection=load_user_collection(user_id),
        tier_map=get_tier_map(),
        user_id=user_id,
        conversation_context=conversation_context,
    )


async def evaluate_trade(
    offered_pokemon: str = "",
    requested_pokemon: str = "",
    user_id: str = "user_001",
    raw_query: str | None = None,
    conversation_context: str | None = None,
) -> str:
    """Handles both command-based trades and natural language intelligence queries."""
    deps = _build_advisor_deps(user_id, conversation_context)

    prompt = raw_query if raw_query else f"Evaluate: My {offered_pokemon} for their {requested_pokemon}."

    try:
        result = await trade_advisor.run(prompt, deps=deps)
        return str(result.output)
    finally:
        if deps.vector_store:
            deps.vector_store.close()
        if deps.strategy_store:
            deps.strategy_store.close()


async def get_trade_suggestions(user_id: str = "user_001", conversation_context: str | None = None) -> str:
    """Proactive suggestions based on current market bullish trends and user goals."""
    deps = _build_advisor_deps(user_id, conversation_context)
    prompt = "Look at my seeking list and cross-reference with trending bullish Pokemon for suggestions."

    try:
        result = await trade_advisor.run(prompt, deps=deps)
        return str(result.output)
    finally:
        if deps.vector_store:
            deps.vector_store.close()
        if deps.strategy_store:
            deps.strategy_store.close()


async def get_pending_offers(user_id: str = "user_001") -> str:
    """Fetch inbox and run AI evaluation on each pending offer (parallel)."""
    from memory.database import TradeOffersManager

    mgr = TradeOffersManager(user_id)
    mgr.seed_offers()
    offers = mgr.get_inbox()

    if not offers:
        return "Your inbox is empty — no pending trade offers."

    async def _analyze(offer: dict[str, Any]) -> str:
        analysis = offer.get("ai_analysis")
        if not analysis:
            analysis = await evaluate_trade(offer["requested_pokemon"], offer["offered_pokemon"], user_id)
            mgr.save_ai_analysis(offer["id"], analysis)
        return analysis

    analyses = await asyncio.gather(*[_analyze(o) for o in offers])

    lines: list[str] = [f"You have **{len(offers)}** pending offer(s):\n"]
    for offer, analysis in zip(offers, analyses, strict=True):
        lines.append(
            f"**Offer #{offer['id']}** from `{offer['sender_id']}`\n"
            f"  They offer: **{offer['offered_pokemon']}** → They want: **{offer['requested_pokemon']}**\n"
            f"  AI Verdict: {analysis}\n"
        )
    return "\n".join(lines)


async def send_trade_offer(
    sender_id: str,
    recipient_id: str,
    offered_pokemon: str,
    requested_pokemon: str,
) -> str:
    """Pre-screen offer fairness, then persist it."""
    from memory.database import TradeOffersManager

    analysis = await evaluate_trade(offered_pokemon, requested_pokemon, sender_id)

    mgr = TradeOffersManager(sender_id)
    offer_id = mgr.create_offer(recipient_id, offered_pokemon, requested_pokemon)
    mgr.save_ai_analysis(offer_id, analysis)

    return (
        f"**Offer #{offer_id} sent** to `{recipient_id}` "
        f"(your {offered_pokemon} for their {requested_pokemon}).\n\n"
        f"**AI Pre-screen:**\n{analysis}"
    )
