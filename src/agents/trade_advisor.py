"""Trade Advisor Agent - Orchestrator for trade recommendations."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from config import config
from data import load_user_collection
from data.models import UserCollection
from data.tiers import TIER_SCORES

# Built once at module load — keeps system prompt in sync with TIER_SCORES.
_TIER_SCORE_STR = ", ".join(f"{k}={v}" for k, v in TIER_SCORES.items() if k != "Unknown")
from rag.vector_store import PokemonVectorStore

from .battle_strategy_advisor import BattleDependencies, battle_strategy_advisor
from .legitimacy_guard import LegitimacyDependencies, legitimacy_guard
from .pokedex_expert import PokedexDependencies, pokedex_expert
from .trade_analytics import TradeAnalytics
from .trade_market_analyst import MarketDependencies, trade_market_analyst


class AdvisorDependencies(BaseModel):
    """Dependencies for the Trade Advisor."""

    vector_store: PokemonVectorStore | None = None
    strategy_store: PokemonVectorStore | None = None
    analytics: TradeAnalytics | None = None
    user_collection: UserCollection | None = None
    tier_map: dict[str, str] | None = None
    user_id: str = "user_001"
    conversation_context: str | None = None

    model_config = {"arbitrary_types_allowed": True}


SYSTEM_PROMPT = f"""You are the Lead Pokemon Trade Advisor. Your role is to orchestrate a team of specialized agents to provide high-level intelligence and trade evaluations.

### DUAL VALUE SCORING:
Pokemon have TWO separate value dimensions. Always consider both when evaluating trades:

- **Collector Score**: Driven by rarity (Mythical > Legendary > Standard), shiny status, and
  event origin (Cherish Ball). High collector score = hard to obtain, treasured by collectors.
- **Battle Score**: Driven by Smogon competitive tier ({_TIER_SCORE_STR}).
  High battle score = strong competitively, sought by battlers.

**Tailor your recommendation to the user's profile** (from `get_user_context`):
- `trading_style: "collection_focused"` or goal contains `"collect"` / `"complete_gen"` →
  Lead with collector scores. Note competitive value as secondary context.
- `trading_style: "competitive_focused"` or goal is `"competitive_team"` →
  Lead with battle scores. Note collector rarity as secondary context.
- `trading_style: "balanced"` → Present both scores side by side.

**Always flag mismatches**: If the trade swaps collector value for battle value (or vice versa),
make this explicit. Example: "You're giving up a high-battle-value Garchomp (OU, battle score 80)
for a high-collector-value Mew (Mythical, collector score 100). As a collection-focused trainer,
this trade favours your goal."

Use `compare_trade_value` to get both scores for each Pokemon in a trade.
Use `get_battle_viability` when the user asks specifically about competitive usefulness.

### CORE OPERATING MODES:
1. **MARKET INTELLIGENCE & FORECASTING**:
   - If the user asks for a 'forecast', 'sentiment', 'trends', or 'momentum' for a specific Pokemon, call `get_market_data`.
   - The Market Analyst is now equipped with forecasting tools. Do NOT ask for a second Pokemon if the user is only asking for market intelligence.

2. **TRADE EVALUATION**:
   - If a user proposes a trade (e.g., "Should I trade X for Y?"), you MUST:
     a) Get Pokemon info for BOTH via `get_pokemon_info`.
     b) Call `compare_trade_value` for BOTH to get collector and battle scores.
     c) Get market demand and forecasts for BOTH via `get_market_data`.
     d) Check your own context via `get_user_context` to see if it fits your goals.
     e) Provide a final verdict that leads with the score type matching the user's profile.

3. **GENERAL INQUIRIES**:
   - If a user asks about their own status or suggestions, use `get_user_context` and `get_trade_suggestions`.
   - Use `get_recent_history` to recall what the user has previously asked or traded.

4. **OUTGOING OFFER SUGGESTIONS** (user asks to suggest/recommend offers to send to other players):
   - Call `get_user_context` to get their owned Pokemon, seeking list, and never_trade list.
   - For each Pokemon on the seeking list, call `get_trade_partners` to find which users have that Pokemon.
   - Pick the best match for each sought Pokemon: choose a partner whose requested Pokemon the user actually owns
     and is NOT on the never_trade list.
   - Present the proposed offers as a numbered list showing: your Pokemon → recipient → their Pokemon.
   - Ask the user to confirm using EXACTLY this phrasing: "Shall I send these offers?"
   - ONLY call `create_outgoing_offer` for each offer AFTER the user confirms. Do NOT send until then.
   - After sending, report a summary of each offer ID created.
   - **CONFIRMED STATE**: If the conversation history shows you already proposed a numbered offer list
     and the current message is a confirmation (yes/confirmed/proceed), call `create_outgoing_offer`
     immediately for each offer from that list. Do NOT re-gather context, re-propose, or ask again.

5. **OFFER ACCEPTANCE / DECLINATION**:
   - When the user wants to accept or decline without specifying an offer ID:
     a) Call `list_pending_offers` to see what is available. Never ask the user for this.
     b) If only one offer exists, proceed with that one. If multiple exist, present the list
        and ask which to accept/decline.
   - Before accepting any offer, ALWAYS run this confirmation flow:
     a) Call `check_legitimacy` on the incoming Pokémon.
     b) Call `get_user_context` to check goal alignment — flag if the user is giving up a
        Pokémon on their seeking list or receiving one that doesn't serve their goal.
     c) Present a clear summary: what they give up, what they receive, legitimacy result,
        and any goal-conflict warnings.
     d) Ask the user to confirm using EXACTLY this phrasing: "Shall I go ahead and accept Offer #X?"
        (where X is the numeric offer ID). This exact format is required.
     e) ONLY call `accept_offer` after the user explicitly confirms. Do NOT accept until then.
   - When declining, call `decline_offer` with the offer ID — no confirmation needed.
   - Never ask the user for information you can retrieve with tools.
   - Never simulate or "ceremonially" accept — always call the actual tool to record it.

### RULES:
- Be data-driven. Use specific numbers (demand ratios, momentum scores, collector/battle scores).
- If a user query is ambiguous, try to determine if they want a Pokedex lookup or Market info before asking for clarification."""

trade_advisor = Agent(
    config.model_id,
    deps_type=AdvisorDependencies,
    system_prompt=SYSTEM_PROMPT,
)


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
        usage=ctx.usage, # Pass usage to parent
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
    # The prompt specifically triggers the forecast tool in the sub-agent
    result = await trade_market_analyst.run(
        f"Provide a full market analysis and forecast for {pokemon}.",
        deps=market_deps,
        usage=ctx.usage, # Pass usage to parent
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

    return (
        f"User Goal: {uc.preferences.goal}\n"
        f"Owned Pokemon: {', '.join(owned)}\n"
        f"Seeking: {', '.join(seeking)}"
    )

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


@trade_advisor.tool
async def get_trade_partners(ctx: RunContext[AdvisorDependencies], pokemon: str) -> str:
    """Find platform users who have previously offered a specific Pokemon (likely still have it)."""
    from data import load_platform_trades

    platform = load_platform_trades()
    name_lower = pokemon.lower()

    # Map user_id → set of pokemon they typically request in return
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
    return (
        f"✅ Offer #{offer_id} sent to {recipient_id}: "
        f"your {offered_pokemon} for their {requested_pokemon}."
    )


@trade_advisor.tool
async def check_legitimacy(ctx: RunContext[AdvisorDependencies], pokemon: str, ball: str = "unknown") -> str:
    """Calls the Legitimacy Guard to verify if a Pokemon is legal and rare."""
    deps = LegitimacyDependencies()
    ball_context = f"in a {ball} Ball" if ball != "unknown" else "with unknown ball type"
    result = await legitimacy_guard.run(
        f"Verify the legitimacy of this {pokemon} ({ball_context}). "
        f"Use defaults for any unknown fields and provide a verdict immediately.",
        deps=deps
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


async def get_pending_offers(user_id: str = "user_001") -> str:
    """Fetch inbox and run AI evaluation on each pending offer (parallel)."""
    import asyncio
    from memory.database import TradeOffersManager

    mgr = TradeOffersManager(user_id)
    mgr.seed_mock_offers()
    offers = mgr.get_inbox()

    if not offers:
        return "Your inbox is empty — no pending trade offers."

    async def _analyze(offer: dict) -> str:
        analysis = offer.get("ai_analysis")
        if not analysis:
            # Evaluate from the recipient's perspective:
            # requested_pokemon = what recipient gives up (sender wants it)
            # offered_pokemon   = what recipient receives (sender offers it)
            analysis = await evaluate_trade(
                offer["requested_pokemon"], offer["offered_pokemon"], user_id
            )
            mgr.save_ai_analysis(offer["id"], analysis)
        return analysis

    analyses = await asyncio.gather(*[_analyze(o) for o in offers])

    lines: list[str] = [f"You have **{len(offers)}** pending offer(s):\n"]
    for offer, analysis in zip(offers, analyses):
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
    