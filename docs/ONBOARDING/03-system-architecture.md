# System Architecture

This file maps the concepts from [02-ai-concepts-explained.md](02-ai-concepts-explained.md)
onto the actual components of this project. Read that file first.

---

## The Four Agents at a Glance

```text
┌────────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                            │
│                         (CLI)                                  │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                 TRADE ADVISOR (Orchestrator)                   │
│  • Routes queries to specialized agents                        │
│  • Synthesizes multi-source information                        │
│  • Applies user context from memory                            │
│  • Generates explainable recommendations                       │
└───┬───────────────┬───────────────┬───────────────┬───────────┘
    │               │               │               │
    ▼               ▼               ▼               ▼
┌──────────┐ ┌────────────┐ ┌─────────────┐ ┌──────────────────┐
│ POKEDEX  │ │  MARKET    │ │ LEGITIMACY  │ │  MEMORY SYSTEM   │
│ EXPERT   │ │  ANALYST   │ │ GUARD       │ │                  │
│          │ │            │ │             │ │• User preferences│
│• RAG     │ │• Demand    │ │• Ball legal │ │• Conversation    │
│• Types   │ │• Momentum  │ │• Provenance │ │  history         │
│• Stats   │ │• Forecasts │ │• Rarity     │ │• Recommendations │
└────┬─────┘ └─────┬──────┘ └─────────────┘ └────────┬─────────┘
     │             │                                  │
     ▼             ▼                                  ▼
┌──────────┐ ┌────────────┐                  ┌──────────────────┐
│ ChromaDB │ │  Trade     │                  │ SQLite           │
│ + PokeAPI│ │  History   │                  │                  │
└──────────┘ └────────────┘                  └──────────────────┘
```

---

## Agent 1: Trade Advisor (Orchestrator)

**File:** `src/agents/trade_advisor.py`

The Trade Advisor is the only agent the CLI talks to directly. Every user query starts
here.

**What it does:**

- Reads the user's query and decides what kind of question it is
- Delegates to specialist agents by calling their work through tools
- Applies user context (goals, collection, conversation history) to the final answer
- Generates an explainable, synthesized recommendation

**What it does NOT do:**

- Query ChromaDB directly
- Read the trade history file directly
- Check ball legality directly

All of that goes through specialists. The Trade Advisor's job is coordination and
synthesis, not raw data access.

**Key tools it can call:**

| Tool | What it does |
| --- | --- |
| `get_pokemon_info(pokemon)` | Delegates to Pokedex Expert |
| `get_market_data(pokemon)` | Delegates to Market Analyst |
| `check_legitimacy(pokemon, ball)` | Delegates to Legitimacy Guard |
| `get_user_context()` | Reads user's collection and goals |
| `get_recent_history()` | Reads conversation history from SQLite |
| `list_pending_offers()` | Shows incoming trade offers |
| `accept_offer(offer_id)` | Accepts an offer (with user confirmation) |
| `decline_offer(offer_id)` | Declines an offer |
| `create_outgoing_offer(...)` | Sends a new offer to another trainer |

**Why this design matters:** When the Market Analyst gets improved, the Trade
Advisor automatically benefits — it calls the same tool and gets better data back.
There is no coupling between agents except through the tool interfaces.

---

## Agent 2: Pokedex Expert

**File:** `src/agents/pokedex_expert.py`

The Pokemon knowledge specialist. The only agent with access to ChromaDB.

**What it does:**

- Answers factual questions about Pokemon using data retrieved from ChromaDB (RAG)
- Compares Pokemon objectively based on real stats
- Explains type matchups using a hardcoded effectiveness chart
- Returns the user's actual collection when asked

**Data sources:**

- ChromaDB (Pokemon stats, types, abilities, evolutions — ingested from PokeAPI)
- Hardcoded type effectiveness chart in the same file
- User collection JSON file

**Tools:**

```python
# src/agents/pokedex_expert.py

@pokedex_expert.tool
async def search_pokemon(ctx: RunContext[PokedexDependencies], query: str) -> str:
    """Search for Pokemon information in the knowledge base."""
    results = ctx.deps.vector_store.query(query, n_results=3)
    return "\n\n".join(r["document"] for r in results)

@pokedex_expert.tool
async def get_type_effectiveness(
    ctx: RunContext[PokedexDependencies],
    attacking_type: str,
    defending_type: str,
) -> str:
    """Get type effectiveness for a matchup."""
    ...

@pokedex_expert.tool
async def get_my_collection(ctx: RunContext[PokedexDependencies]) -> str:
    """Get the user's personal Pokemon collection and goals."""
    ...
```

**Why RAG matters here:** A plain LLM would guess Dragonite's stats from memory and
might be slightly wrong. The Pokedex Expert retrieves the actual data from ChromaDB
before answering. The data comes from the PokeAPI — the authoritative source.

---

## Agent 3: Trade Market Analyst

**File:** `src/agents/trade_market_analyst.py`

The supply-and-demand specialist. Thinks like a market analyst, not a Pokemon expert.

**What it does:**

- Calculates demand for any Pokemon based on real platform transaction history
- Identifies whether demand is rising or falling (momentum)
- Classifies sentiment: Bullish, Bearish, or Stable
- Finds trending Pokemon and compares market value between two Pokemon

**Data source:** `data/platform_trades.json` — thousands of mock trade records
representing the platform's transaction history.

**Key metrics explained:**

*Demand ratio* = (how many times a Pokemon was requested) ÷ (how many times it was
offered)

- Ratio > 1: more people want it than are giving it away → high demand
- Ratio < 1: more people offering it than wanting it → low demand
- Ratio ≈ 1: balanced market

*Momentum* = how the demand ratio has changed recently

The analyst compares the 7-day demand ratio to the 30-day demand ratio:

```text
Momentum = ((ratio_7day - ratio_30day) / ratio_30day) × 100

Momentum > +15%   → "Bullish"  (demand accelerating — consider holding)
Momentum < -15%   → "Bearish"  (demand cooling — good time to trade away)
Between -15%/+15% → "Stable"   (steady market)
```

This is the same pattern used in financial technical analysis, applied to Pokemon
trading volume.

**Tools:**

| Tool | What it returns |
| --- | --- |
| `get_market_forecast(pokemon)` | Full forecast: ratio, momentum score, sentiment, recommendation |
| `get_pokemon_demand(pokemon)` | Times requested, times offered, demand level |
| `get_trade_success(pokemon)` | Total trades, completed trades, success rate % |
| `get_trending(days=30)` | Top 10 most mentioned Pokemon in the time window |
| `compare_market_value(a, b)` | Side-by-side demand comparison of two Pokemon |
| `get_high_demand_pokemon()` | Top 10 most requested Pokemon overall |

---

## Agent 4: Legitimacy Guard

**File:** `src/agents/legitimacy_guard.py`

The fraud detection specialist. Protects you from accepting hacked Pokemon.

**What it does:**

- Checks whether a Pokemon/ball combination is legally obtainable in the games
- Identifies Pokemon that cannot legitimately be shiny (shiny-locked)
- Validates origin region markings
- Classifies rarity tier (Mythical, Legendary, Standard)
- Assesses overall trade risk level

**Why this agent exists:** In Pokemon games, certain Pokemon can only be obtained
in specific PokeBalls (e.g., Mew can only come in a Cherish Ball or Poke Ball —
never a Great Ball). Certain Pokemon are "shiny-locked," meaning legitimate shinies
of them do not exist. An AI language model is unreliable on these specific rules
because they are edge-case game mechanics that get confused with general knowledge.
Getting this wrong means accepting a hacked Pokemon.

**Why the rules are hardcoded:** The rules in this agent are stored as Python
dictionaries, not generated by an LLM. The LLM cannot hallucinate them. If the
rules are wrong, they are wrong in a deterministic, fixable way — not randomly
wrong depending on how the question is phrased.

```python
# Example from src/agents/legitimacy_guard.py
_LEGAL_BALL_MAP = {
    "mew": ["cherish ball", "poke ball"],
    "celebi": ["cherish ball"],
    "jirachi": ["cherish ball"],
    "mewtwo": ["master ball", "ultra ball", "poke ball", "cherish ball"],
    # ... 50+ mythicals and legendaries
}

_SHINY_LOCKED = {
    "mew", "celebi", "jirachi", "deoxys", "phione", "manaphy", "darkrai",
    "shaymin", "arceus", "victini", "keldeo", "meloetta", "genesect",
    # ... all event-only mythicals
}
```

---

## Data and Memory

The agents need data. Here is where it all lives:

| What | Where | Format | Managed By |
| --- | --- | --- | --- |
| Pokemon stats, types, abilities | ChromaDB at `localhost:8000` (Docker) | Vector store | `src/rag/vector_store.py` |
| Platform trade history | `data/platform_trades.json` | JSON | Loaded at startup, read-only |
| User's Pokemon collection | `data/user_collection.json` | JSON | Loaded at startup, read-only |
| User preferences | `data/memory.db` | SQLite | `src/memory/user_preferences.py` |
| Conversation history | `data/memory.db` | SQLite | `src/memory/conversation_memory.py` |
| Trade offers (inbox/sent) | `data/memory.db` | SQLite | `src/memory/database.py` |

**SQLite vs ChromaDB:** SQLite stores structured user data — preferences, offer
records, conversation history. ChromaDB stores the Pokemon knowledge base as
vectors for semantic search. They serve completely different purposes and both need
to be running for the full system to work. (ChromaDB requires Docker. SQLite is a
file and requires nothing.)

---

## Worked Example: "trade alakazam for gengar"

Here is what actually happens when you type this command, step by step:

### Step 1: CLI parses the command

`src/cli/app.py` recognizes this as a `trade` command and passes it to the Trade
Advisor with the context "evaluate trading alakazam for gengar."

### Step 2: Trade Advisor determines what it needs

The Trade Advisor's system prompt tells it: for trade evaluations, get Pokemon info
for both Pokemon, get market data for both Pokemon, and check user context.

### Step 3: Pokedex Expert looks up Alakazam

Trade Advisor calls `get_pokemon_info("alakazam")` → this runs the Pokedex Expert
agent, which calls `search_pokemon("alakazam")` → ChromaDB returns Alakazam's stored
document (stats, types, abilities, evolution chain) → Pokedex Expert summarizes the
relevant information.

### Step 4: Pokedex Expert looks up Gengar

Same process for Gengar.

### Step 5: Market Analyst evaluates both

Trade Advisor calls `get_market_data("alakazam")` → Market Analyst reads the trade
history JSON, calculates Alakazam's demand ratio over 7 and 30 days, and returns a
forecast with momentum and sentiment. Repeated for Gengar.

### Step 6: User context is loaded

Trade Advisor calls `get_user_context()` → reads your collection JSON and SQLite
preferences. Are you seeking Gengar? Do you want to keep Alakazam? What is your
trading goal?

### Step 7: Legitimacy is checked (if an offer is being accepted)

If you are evaluating an offer to accept (not just asking hypothetically), Trade
Advisor calls `check_legitimacy("gengar", ball=...)` → Legitimacy Guard checks if
the ball/shiny status is legal.

### Step 8: Trade Advisor synthesizes

Now the Trade Advisor has: both Pokemon's stats and competitive assessments, market
demand data for both, your personal context, and a legitimacy verdict. The LLM
synthesizes all of this into a recommendation with reasoning.

**What you see:**

```text
Based on current market data and your goals:

Gengar Analysis:
  • Strong competitive viability (Ghost/Poison typing, high Special Attack)
  • Market: Bullish (+23% momentum) — demand rising
  • Legitimacy: No issues detected

Alakazam Analysis:
  • Also high competitive value (Psychic type, highest Speed in collection)
  • Market: Stable (0% momentum)

Given that you are seeking Ghost-types for your team and Alakazam is not
on your protected list, this trade works in your favor.

Verdict: Recommend accepting.
```

---

## Required Services

| Service | Required? | What breaks without it |
| --- | --- | --- |
| ChromaDB (Docker) | Yes | Pokedex Expert cannot search — all Pokemon lookups fail |
| SQLite (`data/memory.db`) | Yes (auto-created) | No memory persistence, no offer management |
| LLM API key (Anthropic/OpenAI/Google) | Yes | Nothing works — no LLM = no agents |
| Phoenix (Docker) | No | Tracing UI unavailable, but the app works fine |
| Ollama | No (unless `USE_OLLAMA_EMBEDDINGS=true`) | Hash-based embeddings used instead |

See [`docs/GETTING_STARTED.md`](../GETTING_STARTED.md) for setup commands.

---

**Next: [04-setup-and-first-run.md](04-setup-and-first-run.md)**
