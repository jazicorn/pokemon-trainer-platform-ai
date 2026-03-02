"""Legitimacy & Rarity Guard Agent - Compliance and provenance specialist."""

from __future__ import annotations
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from config import config


# Pokemon that can only exist in specific balls due to their event/game origins.
# Cherish Ball = official event distribution. Master Ball = in-game legendary catch.
_LEGAL_BALL_MAP: dict[str, list[str]] = {
    # Gen 1 Mythicals — event-only, Cherish or classic Poké Ball
    "mew": ["cherish", "poke"],
    # Gen 2 Mythicals
    "celebi": ["cherish", "poke", "luxury"],
    # Gen 3 Mythicals — event-only
    "jirachi": ["cherish", "poke"],
    "deoxys": ["cherish", "poke", "master"],
    "phione": ["poke", "cherish"],
    "manaphy": ["cherish", "poke"],
    # Gen 4 Mythicals
    "darkrai": ["cherish", "poke"],
    "shaymin": ["cherish", "poke"],
    "arceus": ["cherish", "poke", "master"],
    # Gen 5 Mythicals
    "victini": ["cherish", "poke"],
    "keldeo": ["cherish", "poke"],
    "meloetta": ["cherish", "poke"],
    "genesect": ["cherish", "poke"],
    # Gen 6 Mythicals
    "diancie": ["cherish", "poke"],
    "hoopa": ["cherish", "poke"],
    "volcanion": ["cherish", "poke"],
    # Gen 7 Mythicals
    "magearna": ["cherish", "poke"],
    "marshadow": ["cherish", "poke"],
    "zeraora": ["cherish", "poke"],
    "meltan": ["poke"],        # GO exclusive — only catchable in Pokémon GO
    "melmetal": ["poke", "master"],
    # Gen 8 Mythicals
    "zarude": ["cherish", "poke"],
    # Gen 9 Mythicals
    "pecharunt": ["cherish", "poke"],
    # Box legendaries that can only be caught in Master Ball or via event Cherish Ball
    "mewtwo": ["master", "cherish", "poke", "ultra"],
    "lugia": ["master", "cherish", "poke", "ultra"],
    "ho-oh": ["master", "cherish", "poke", "ultra"],
    "kyogre": ["master", "cherish", "poke", "ultra"],
    "groudon": ["master", "cherish", "poke", "ultra"],
    "rayquaza": ["master", "cherish", "poke", "ultra"],
    "dialga": ["master", "cherish", "poke", "ultra"],
    "palkia": ["master", "cherish", "poke", "ultra"],
    "giratina": ["master", "cherish", "poke", "ultra"],
    "reshiram": ["master", "cherish", "poke", "ultra"],
    "zekrom": ["master", "cherish", "poke", "ultra"],
    "kyurem": ["master", "cherish", "poke", "ultra"],
    "xerneas": ["master", "cherish", "poke", "ultra"],
    "yveltal": ["master", "cherish", "poke", "ultra"],
    "zygarde": ["master", "cherish", "poke", "ultra"],
    "cosmog": ["poke"],        # gifted, no catching
    "cosmoem": ["poke"],
    "solgaleo": ["master", "cherish", "poke"],
    "lunala": ["master", "cherish", "poke"],
    "necrozma": ["master", "cherish", "poke", "ultra"],
    "zacian": ["master", "cherish", "poke"],
    "zamazenta": ["master", "cherish", "poke"],
    "eternatus": ["master", "cherish", "poke"],
    "calyrex": ["master", "cherish", "poke"],
    "koraidon": ["master", "cherish", "poke"],
    "miraidon": ["master", "cherish", "poke"],
}

# Pokemon that cannot legitimately be shiny (shiny-locked in all mainstream games).
_SHINY_LOCKED: frozenset[str] = frozenset({
    # Most Mythicals are shiny-locked in their primary distributions
    "mew", "celebi", "jirachi", "deoxys", "phione", "manaphy",
    "darkrai", "shaymin", "arceus", "victini", "keldeo", "meloetta",
    "genesect", "diancie", "hoopa", "volcanion", "magearna", "marshadow",
    "zeraora", "meltan", "melmetal", "zarude", "pecharunt",
    # Box legendaries that are shiny-locked in their native games
    "cosmog", "cosmoem", "solgaleo", "lunala",
    "zacian", "zamazenta", "eternatus", "calyrex",
    "koraidon", "miraidon",
    # Starters gifted at the start of a game (shiny-locked)
    "kubfu", "urshifu",
})

# Valid origin marks by game region (region name → origin mark label).
_ORIGIN_MARKS: dict[str, str] = {
    "kanto": "None / Classic",
    "johto": "None / Classic",
    "hoenn": "None / Classic",
    "sinnoh": "None / Classic",
    "unova": "None / Classic",
    "kalos": "Kalos (Gen VI)",
    "alola": "Alola (Gen VII)",
    "galar": "Galar / Crown Mark",
    "hisui": "Hisui Mark",
    "paldea": "Paldea Mark",
    "go": "GO Mark",
    "home": "HOME",
    "colosseum": "None / Classic",
    "xd": "None / Classic",
}

# Rarity tiers for classification.
_MYTHICALS: frozenset[str] = frozenset({
    "mew", "celebi", "jirachi", "deoxys", "phione", "manaphy",
    "darkrai", "shaymin", "arceus", "victini", "keldeo", "meloetta",
    "genesect", "diancie", "hoopa", "volcanion", "magearna", "marshadow",
    "zeraora", "meltan", "melmetal", "zarude", "pecharunt",
})

_LEGENDARIES: frozenset[str] = frozenset({
    "articuno", "zapdos", "moltres", "mewtwo", "lugia", "ho-oh",
    "raikou", "entei", "suicune", "regirock", "regice", "registeel",
    "latias", "latios", "kyogre", "groudon", "rayquaza",
    "uxie", "mesprit", "azelf", "dialga", "palkia", "heatran",
    "regigigas", "giratina", "cresselia",
    "cobalion", "terrakion", "virizion", "tornadus", "thundurus",
    "reshiram", "zekrom", "landorus", "kyurem",
    "xerneas", "yveltal", "zygarde",
    "tapu-koko", "tapu-lele", "tapu-bulu", "tapu-fini",
    "cosmog", "cosmoem", "solgaleo", "lunala", "necrozma",
    "zacian", "zamazenta", "eternatus", "kubfu", "urshifu",
    "regieleki", "regidrago", "glastrier", "spectrier", "calyrex",
    "wo-chien", "chien-pao", "ting-lu", "chi-yu",
    "koraidon", "miraidon", "walking-wake", "iron-leaves",
    "okidogi", "munkidori", "fezandipiti", "ogerpon", "terapagos",
})

# Public aliases for use by other modules (e.g. value_scoring).
MYTHICALS: frozenset[str] = _MYTHICALS
LEGENDARIES: frozenset[str] = _LEGENDARIES


class LegitimacyDependencies(BaseModel):
    """Dependencies for the Legitimacy Guard."""

    legal_ball_map: dict[str, list[str]] = _LEGAL_BALL_MAP
    shiny_locked: frozenset[str] = _SHINY_LOCKED
    origin_marks: dict[str, str] = _ORIGIN_MARKS

    model_config = {"arbitrary_types_allowed": True}


SYSTEM_PROMPT = """You are a Pokemon Legitimacy & Rarity Expert.
Your primary goal is to protect the user from 'genned' (hacked) or illegal Pokemon.

CHECKLIST:
1. BALL CHECK: Is the Pokemon in a ball that was actually available for its release?
   Use the verify_provenance tool to check against the legal ball map.
2. SHINY CHECK: Is this Pokemon shiny-locked? Many Mythicals and box legendaries
   cannot legitimately be shiny.
3. ORIGIN CHECK: Does the claimed origin region match a valid origin mark?
   Use verify_provenance with origin_region to validate.
4. RARITY TIERING: Classify the Pokemon:
   - Common / Uncommon
   - Rare (Legendaries)
   - Mythical (Event Only)
   - Ultra Rare (Shiny Legendaries / Specific Events)

If a combination is impossible (e.g., Mew in a Great Ball, shiny Zeraora), flag
it as ILLEGAL/SCAM. Always provide a Risk Level (Low, Medium, High).

CRITICAL RULE: Never ask the user for information. If ball type, shininess, or
origin region are not provided, call verify_provenance with 'unknown' for those
fields and produce a verdict based on what can be determined. The tool handles
unknowns gracefully — a result of Low risk with unknowns means no red flags were
found for this Pokemon."""

legitimacy_guard = Agent(
    config.model_id,
    deps_type=LegitimacyDependencies,
    system_prompt=SYSTEM_PROMPT,
)


@legitimacy_guard.tool
async def verify_provenance(
    ctx: RunContext[LegitimacyDependencies],
    pokemon: str,
    ball: str = "unknown",
    is_shiny: bool = False,
    origin_region: str = "unknown",
) -> str:
    """Check if a specific Pokemon/Ball/Shiny/Origin combo is legal.

    Args:
        pokemon: Pokemon name (e.g. "mew", "charizard").
        ball: Ball type the Pokemon is claimed to be in (e.g. "great", "cherish").
        is_shiny: Whether the Pokemon is claimed to be shiny.
        origin_region: Claimed origin region (e.g. "galar", "paldea", "go").
    """
    name = pokemon.lower()
    ball_type = ball.lower()
    region = origin_region.lower()
    flags: list[str] = []

    # ── Ball check ────────────────────────────────────────────────────────────
    allowed_balls = ctx.deps.legal_ball_map.get(name)
    if allowed_balls and ball_type not in ("unknown", "") and ball_type not in allowed_balls:
        flags.append(
            f"🚨 ILLEGAL BALL: {pokemon.title()} cannot legally be in a "
            f"{ball.title()} Ball. Legal balls: {', '.join(b.title() for b in allowed_balls)}."
        )

    # ── Shiny-lock check ──────────────────────────────────────────────────────
    if is_shiny and name in ctx.deps.shiny_locked:
        flags.append(
            f"🚨 SHINY LOCK: {pokemon.title()} is shiny-locked and cannot "
            f"legitimately be shiny outside of specific hacked distributions."
        )

    # ── Origin mark check ─────────────────────────────────────────────────────
    origin_mark: str | None = None
    if region not in ("unknown", ""):
        origin_mark = ctx.deps.origin_marks.get(region)
        if origin_mark is None:
            flags.append(
                f"⚠️  UNKNOWN ORIGIN: '{origin_region}' is not a recognised game region. "
                f"Valid regions: {', '.join(ctx.deps.origin_marks.keys())}."
            )

    # ── Rarity classification ─────────────────────────────────────────────────
    if name in _MYTHICALS:
        rarity = "Mythical (Event-Only)"
    elif name in _LEGENDARIES:
        rarity = "Legendary"
    else:
        rarity = "Standard"
    if is_shiny:
        rarity = f"Shiny {rarity}"

    # ── Risk assessment ───────────────────────────────────────────────────────
    risk = "High" if flags else ("Medium" if rarity.startswith("Shiny") else "Low")

    lines = [f"Provenance Check: {pokemon.title()} — {rarity}"]
    lines.append(f"  Ball: {ball.title() if ball_type != 'unknown' else 'Not specified'}")
    if origin_mark:
        lines.append(f"  Origin: {origin_region.title()} ({origin_mark})")
    lines.append(f"  Risk Level: {risk}")
    if flags:
        lines.append("")
        lines.extend(flags)

    return "\n".join(lines)
