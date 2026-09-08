"""Tool implementations registered on the Trade Advisor agent."""

from __future__ import annotations

from pydantic_ai import RunContext

from .battle_strategy_advisor import BattleDependencies, battle_strategy_advisor
from .legitimacy_guard import LegitimacyDependencies, legitimacy_guard
from .pokedex_expert import PokedexDependencies, pokedex_expert
from .trade_advisor_core import AdvisorDependencies, trade_advisor
from .trade_market_analyst import MarketDependencies, trade_market_analyst


@trade_advisor.tool
async def get_pokemon_info(
    ctx: RunContext[AdvisorDependencies],
    pokemon: str,
) -> str:
    """Get detailed Pokemon information (stats, types, abilities)."""
    if ctx.deps.vector_store is None:
        return "Pokemon data not available"

    pokedex_deps = PokedexDependencies(vector_store=ctx.deps.vector_store, user_id=ctx.deps.user_id)
    result = await pokedex_expert.run(
        f"Provide a technical breakdown of {pokemon}.",
        deps=pokedex_deps,
        usage=ctx.usage,
    )
    return str(result.output)


@trade_advisor.tool
async def get_market_data(
    ctx: RunContext[AdvisorDependencies],
    pokemon: str,
) -> str:
    """Get current market demand, sentiment, and forecasts."""
    if ctx.deps.analytics is None:
        return "Market data not available"

    market_deps = MarketDependencies(analytics=ctx.deps.analytics)
    result = await trade_market_analyst.run(
        f"Provide a full market analysis and forecast for {pokemon}.",
        deps=market_deps,
        usage=ctx.usage,
    )
    return str(result.output)


@trade_advisor.tool
async def get_user_context(
    ctx: RunContext[AdvisorDependencies],
) -> str:
    """Access user's collection, seeking list, and goals."""
    if ctx.deps.user_collection is None:
        return "User context not available"

    uc = ctx.deps.user_collection
    owned = [p.pokemon_id for p in uc.pokemon]
    seeking = uc.preferences.seeking

    return f"User Goal: {uc.preferences.goal}\nOwned Pokemon: {', '.join(owned)}\nSeeking: {', '.join(seeking)}"


@trade_advisor.tool
async def compare_trade_value(
    ctx: RunContext[AdvisorDependencies],
    offered_pokemon: str,
    requested_pokemon: str,
) -> str:
    """Return collector and battle scores for both sides of a proposed trade.

    Use this alongside get_pokemon_info and get_market_data to build a complete
    trade evaluation. Scores are context-free numbers — interpretation (which
    score matters more) depends on the user's trading_style and goal.
    """
    from data.value_scoring import score_summary
    from rag.smogon_fetcher import get_tier_map

    tier_map = ctx.deps.tier_map or get_tier_map()

    offered_scores = score_summary(offered_pokemon, tier_map)
    requested_scores = score_summary(requested_pokemon, tier_map)

    return (
        f"Value scores for proposed trade:\n"
        f"  {offered_pokemon} (you give):\n"
        f"    Collector score: {offered_scores['collector_score']}\n"
        f"    Battle score:    {offered_scores['battle_score']} (Tier: {offered_scores['smogon_tier']})\n"
        f"  {requested_pokemon} (you receive):\n"
        f"    Collector score: {requested_scores['collector_score']}\n"
        f"    Battle score:    {requested_scores['battle_score']} (Tier: {requested_scores['smogon_tier']})"
    )


@trade_advisor.tool
async def get_battle_viability(
    ctx: RunContext[AdvisorDependencies],
    pokemon: str,
) -> str:
    """Get competitive battle viability, recommended movesets, and tier placement."""
    strategy_store = ctx.deps.strategy_store
    battle_deps = BattleDependencies(strategy_store=strategy_store)
    result = await battle_strategy_advisor.run(
        f"Give a competitive overview of {pokemon}: tier, best sets, and why it is or isn't valued.",
        deps=battle_deps,
        usage=ctx.usage,
    )
    return str(result.output)


@trade_advisor.tool
async def get_recent_history(ctx: RunContext[AdvisorDependencies]) -> str:
    """Retrieve recent conversation history to provide continuity across turns."""
    return ctx.deps.conversation_context or "No previous conversation."


@trade_advisor.tool
async def list_pending_offers(ctx: RunContext[AdvisorDependencies]) -> str:
    """List all pending incoming trade offers with their IDs and Pokémon details."""
    from memory.database import TradeOffersManager

    mgr = TradeOffersManager(ctx.deps.user_id)
    offers = mgr.get_inbox()
    if not offers:
        return "No pending offers in your inbox."
    lines: list[str] = [f"{len(offers)} pending offer(s):"]
    for o in offers:
        lines.append(
            f"  Offer #{o['id']} from {o['sender_id']}: "
            f"they offer {o['offered_pokemon']}, they want your {o['requested_pokemon']}"
        )
    return "\n".join(lines)


@trade_advisor.tool
async def get_trade_partners(ctx: RunContext[AdvisorDependencies], pokemon: str) -> str:
    """Find platform users who have previously offered a specific Pokemon (likely still have it)."""
    from data.loader import load_platform_trades

    platform = load_platform_trades()
    name_lower = pokemon.lower()

    partners: dict[str, list[str]] = {}
    for trade in platform.trades:
        if trade.offered_pokemon.lower() == name_lower and trade.user_a_id != ctx.deps.user_id:
            user_id = trade.user_a_id
            if user_id not in partners:
                partners[user_id] = []
            partners[user_id].append(trade.requested_pokemon)

    if not partners:
        return f"No platform users found who have recently traded {pokemon}."

    lines: list[str] = [f"Platform users who have offered {pokemon} (likely still have it):"]
    for uid, requested in list(partners.items())[:5]:
        deduped = list(dict.fromkeys(requested))
        lines.append(f"  {uid} — has asked for: {', '.join(deduped[:3])}")

    return "\n".join(lines)


@trade_advisor.tool
async def create_outgoing_offer(
    ctx: RunContext[AdvisorDependencies],
    recipient_id: str,
    offered_pokemon: str,
    requested_pokemon: str,
) -> str:
    """Send a trade offer to another user. Call this to actually dispatch an offer."""
    from memory.database import TradeOffersManager

    mgr = TradeOffersManager(ctx.deps.user_id)
    offer_id = mgr.create_offer(recipient_id, offered_pokemon, requested_pokemon)
    return f"✅ Offer #{offer_id} sent to {recipient_id}: your {offered_pokemon} for their {requested_pokemon}."


@trade_advisor.tool
async def check_legitimacy(ctx: RunContext[AdvisorDependencies], pokemon: str, ball: str = "unknown") -> str:
    """Calls the Legitimacy Guard to verify if a Pokemon is legal and rare."""
    deps = LegitimacyDependencies()
    ball_context = f"in a {ball} Ball" if ball != "unknown" else "with unknown ball type"
    result = await legitimacy_guard.run(
        f"Verify the legitimacy of this {pokemon} ({ball_context}). "
        f"Use defaults for any unknown fields and provide a verdict immediately.",
        deps=deps,
    )
    return str(result.output)


@trade_advisor.tool
async def accept_offer(ctx: RunContext[AdvisorDependencies], offer_id: int) -> str:
    """Accept a pending trade offer by ID. Updates the database and records the timestamp."""
    from memory.database import TradeOffersManager

    mgr = TradeOffersManager(ctx.deps.user_id)
    success = mgr.update_status(offer_id, "accepted")
    if success:
        return (
            f"✅ Offer #{offer_id} has been formally accepted. "
            f"Status updated to 'accepted' and timestamp recorded. "
            f"The sender has been notified via the shared trade ledger."
        )
    return (
        f"❌ Could not accept Offer #{offer_id} — it may not exist, "
        f"already be responded to, or not be addressed to you."
    )


@trade_advisor.tool
async def decline_offer(ctx: RunContext[AdvisorDependencies], offer_id: int) -> str:
    """Decline a pending trade offer by ID. Updates the database and records the timestamp."""
    from memory.database import TradeOffersManager

    mgr = TradeOffersManager(ctx.deps.user_id)
    success = mgr.update_status(offer_id, "declined")
    if success:
        return f"Offer #{offer_id} has been declined and the sender has been notified."
    return f"Could not decline Offer #{offer_id} — it may not exist or already be responded to."
