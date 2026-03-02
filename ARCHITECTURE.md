# Pokemon Trainer's Second Brain

Capstone Project Architecture

## Business Context: What This Project Demonstrates

While this project uses Pokemon trading as its domain, the underlying
architecture solves a **universal business problem**: helping users make
optimal decisions in a marketplace by synthesizing product knowledge, market
dynamics, and personal preferences.

### Direct Business Parallels

| This Project               | Real-World Equivalent            |
| -------------------------- | -------------------------------- |
| Pokemon Trade Advisor      | Investment recommendation engine |
| Pokedex Expert             | Product catalog / specs database |
| Trade Market Analyst       | Market research / pricing        |
| User preferences + history | Customer profile / CRM data      |
| "Should I trade X for Y?"  | "Should I buy/sell this asset?"  |
| Platform trade history     | Transaction data / order book    |

### Transferable Architecture Patterns

This project implements patterns used in production systems at companies like:

- **Robinhood / Wealthfront**: Personalized investment recommendations based
  on user goals, risk tolerance, and market conditions
- **eBay / StockX**: Marketplace pricing guidance based on supply/demand and
  historical transactions
- **Netflix / Spotify**: Multi-factor recommendation engines combining content
  attributes, user preferences, and behavioral data
- **Salesforce / HubSpot**: CRM systems that learn from user interactions to
  improve suggestions over time

## Overview

A personal knowledge system designed to help Pokemon trainers on the Pokemon
Trainer Platform make intelligent trade decisions. The system combines product
knowledge (Pokemon data), market analytics (platform-wide trade patterns), and
user personalization (preferences and history) to provide data-driven
recommendations.

### Core Value Proposition

- **Product Intelligence**: Understand item value based on attributes, rarity,
  and comparative analysis
- **Market Analytics**: Analyze platform-wide transaction patterns to identify
  supply/demand dynamics
- **Behavioral Learning**: Track user history and learn from past decisions
- **Preference Management**: Remember user goals and constraints to personalize
  recommendations
- **Decision Support**: Synthesize all factors into actionable, explainable
  recommendations

## Capstone Requirements Mapping

| Requirement           | Implementation                                           |
| --------------------- | -------------------------------------------------------- |
| Pydantic AI           | All agents built with Pydantic AI                        |
| 3+ Specialized Agents | Pokedex, Market Analyst, Trade Advisor, Legitimacy Guard |
| RAG Implementation    | Vector store over Pokemon and trade data                 |
| Persistent Memory     | User preferences and conversation history                |
| PII Guardrails        | Filter personal info before storage                      |
| Pydantic Evals        | Multi-agent vs single-agent comparison                   |
| OTEL Observability    | Trace agent calls and measure latency                    |
| Local Data Storage    | SQLite for structured, ChromaDB for vectors              |
| MCP Server (Optional) | Expose advisor as MCP tool                               |

## System Architecture Overview

```text
┌────────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                            │
│                      (CLI / MCP)                               │
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
│ ChromaDB │ │  Trade     │                  │ SQLite +         │
│ + PokeAPI│ │  History   │                  │ PII Filter       │
└──────────┘ └────────────┘                  └──────────────────┘
```

## Data Sources

### Product Catalog: PokeAPI (External)

**Business Analog**: Product database, SKU catalog, asset specifications

Public API providing comprehensive Pokemon data from the game series.

- Pokemon base stats (HP, Attack, Defense, Speed, etc.)
- Type information and type effectiveness matchups
- Evolution chains and evolution requirements
- Abilities and move pools
- Rarity indicators (legendary, mythical, pseudo-legendary status)
- Generation and regional information

**API Endpoint**: <https://pokeapi.co/docs/v2>

### Transaction Data: Platform Trade History (Mock Data)

**Business Analog**: Order book, transaction ledger, sales history

Historical trade data from the Pokemon Trainer Platform showing what users
trade.

- All completed trades on the platform
- Trade timestamps and frequency patterns
- Which Pokemon are frequently offered vs requested (supply/demand)
- Trade acceptance/rejection rates by Pokemon

### Customer Profile: User Personal Data

**Business Analog**: CRM record, user profile, preference settings

Individual user data stored locally for personalization.

- User's Pokemon collection (current inventory/portfolio)
- User's personal trade history
- Stated preferences (favorite types, team goals, trading style)
- Past recommendations and whether they were followed (feedback loop)

## Multi-Agent Architecture

### Agent 1: Pokedex Expert (Product Knowledge Agent)

**Business Analog**: Product specialist, catalog search, specification lookup

**Purpose**: Deep knowledge about Pokemon characteristics and comparative value.

**Capabilities**:

- Answer questions about Pokemon stats, types, and abilities
- Compare two Pokemon objectively (stats, type coverage, evolution potential)
- Identify Pokemon strengths and weaknesses
- Explain type matchups and competitive viability

**Data Access**:

- RAG over ingested PokeAPI data
- Can make live calls to PokeAPI for missing data

**Example Queries**:

- "What are Eevee's evolution options?"
- "Compare Charizard vs Dragonite"
- "What types counter Steel?"

### Agent 2: Trade Market Analyst (Market Intelligence Agent)

**Business Analog**: Market research analyst, pricing engine, demand forecasting

**Purpose**: Understand platform-wide trading patterns and demand.

**Capabilities**:

- Analyze which Pokemon are in high demand on the platform
- Identify Pokemon that are frequently offered but rarely wanted
- Track trade volume trends over time
- Calculate trade success rates by Pokemon
- Compute supply/demand ratios as a proxy for market value

**Data Access**:

- Platform trade history database
- Aggregated trade statistics

**Key Metrics Computed**:

- **Demand Ratio**: requests / offers (>1 = high demand, <1 = oversupply)
- **Trade Velocity**: trades per time period
- **Acceptance Rate**: completed / (completed + rejected)

**Example Queries**:

- "What's in high demand right now?"
- "Is Gengar hard to get?"
- "What trades get accepted most often?"

### Agent 3: Trade Advisor (Recommendation Orchestrator)

**Business Analog**: Financial advisor, recommendation engine, decision support
system

**Purpose**: Synthesize information from other agents with user context to make
recommendations.

**Capabilities**:

- Evaluate proposed trades considering all factors
- Proactively suggest trades based on user's collection and goals
- Explain reasoning behind recommendations (explainable AI)
- Learn from user feedback on past recommendations

**Data Access**:

- Calls Pokedex Expert for product knowledge
- Calls Trade Market Analyst for market insights
- User's collection, preferences, and trade history from memory

**Decision Framework**:

1. Assess intrinsic value (stats, rarity, evolution potential)
1. Assess market value (supply/demand dynamics)
1. Assess personal value (alignment with user goals)
1. Weigh factors based on user's stated trading style
1. Generate recommendation with full reasoning

**Example Queries**:

- "Should I trade my Alakazam for their Machamp?"
- "What trades should I consider?"
- "Help me complete my Fire team"

### Agent 4: Legitimacy Guard (Compliance Agent)

**Business Analog**: Fraud detection, compliance check, authentication verifier

**Purpose**: Validate trade legitimacy by checking metadata that LLMs commonly
hallucinate.

**Capabilities**:

- Verify PokeBall legality (whether a Pokemon can legally exist in a given ball)
- Classify rarity tiers (Standard, Shiny, Mythical)
- Assess risk levels for trades involving rare or restricted Pokemon

**Data Access**:

- Hardcoded legality rules for restricted Pokemon (e.g., Mew, Celebi)
- Rarity classification tables

**Example Queries**:

- "Is this Mew in a Master Ball legitimate?"
- "What's the risk level of this trade?"

## Memory System

**Business Analog**: Customer profile, preference center, interaction history

### User Preferences (Persistent)

| Preference         | Example Values                |
| ------------------ | ----------------------------- |
| Favorite Types     | `["fire", "dragon", "ghost"]` |
| Team Building Goal | `"Complete Gen 1 collection"` |
| Trading Style      | `"value_focused"`             |
| Must-Keep Pokemon  | `["Charizard", "Pikachu"]`    |
| Actively Seeking   | `["Dragonite", "Gengar"]`     |

**Business Equivalents**:

- Favorite Types = Product category preferences
- Team Building Goal = Investment thesis / portfolio goal
- Trading Style = Risk tolerance / investment style
- Must-Keep Pokemon = Holdings constraints / do-not-sell list
- Actively Seeking = Watchlist / buy targets

### Conversation Memory

- Recent questions and responses
- Trades discussed in current session
- Pokemon the user expressed interest in
- Reasoning the user agreed or disagreed with

### Decision Memory (Feedback Loop)

- Past trade recommendations and outcomes
- Which recommendations the user followed
- User feedback on recommendation quality
- Used to improve future recommendations

### Trade Offers (Persistent)

Managed by `TradeOffersManager` in `memory/database.py`, backed by the
`trade_offers` SQLite table.

| Column              | Purpose                                    |
| ------------------- | ------------------------------------------ |
| `sender_id`         | User who sent the offer                    |
| `recipient_id`      | User the offer is addressed to             |
| `offered_pokemon`   | Pokemon being offered                      |
| `requested_pokemon` | Pokemon requested in return                |
| `status`            | `pending` / `accepted` / `declined`        |
| `ai_analysis`       | Cached AI evaluation of the offer fairness |

**Business Equivalent**: Order management system, marketplace bid/ask book

## RAG Implementation

### Vector Store Contents

- Pokemon data chunks (one document per Pokemon with stats, abilities, types)
- Evolution chain information
- Type effectiveness charts
- Platform trade history (chunked by time period or Pokemon)
- User's collection metadata

### Embedding Strategy

- Default: Hash-based deterministic embeddings (384 dimensions, no external dependencies)
- Optional: Semantic embeddings via Ollama (`nomic-embed-text`) for higher quality retrieval
- Store in ChromaDB (local, no cloud required) via direct HTTP API (v2)
- Chunk Pokemon data to balance detail vs retrieval precision

### Retrieval Scenarios

| Query Type                   | RAG Retrieval                 |
| ---------------------------- | ----------------------------- |
| "What fire types do I have?" | User collection + type data   |
| "Is Dragonite valuable?"     | Stats + platform demand data  |
| "What trades have I done?"   | User's personal trade history |
| "What's trending?"           | Recent platform trade stats   |

**Business Analogs**:

- Collection queries = Portfolio by sector
- Value queries = Asset valuation
- Trade history = Transaction history
- Trending queries = Market trends report

## PII Guardrails

**Business Analog**: GDPR compliance, data privacy layer, PII redaction

### What Gets Filtered

- Email addresses mentioned in conversation
- Phone numbers
- Real names of other users ("my friend John wants to trade...")
- Physical addresses
- Any external account identifiers

### Implementation

- Regex-based detection for structured PII (emails, phones, SSNs, credit cards, IPs, usernames)
- Pattern-based name detection with Pokemon name exclusion to avoid false positives
- Applied before storing to memory or message history
- Replace detected PII with generic placeholders (`[EMAIL]`, `[NAME]`, `[PHONE]`, etc.)

## Evaluation Strategy

**Business Analog**: A/B testing, model validation, recommendation quality
metrics

### Eval 1: Trade Recommendation Quality

**Hypothesis**: Multi-agent architecture (Product + Market + Advisor) produces
better recommendations than a single LLM call.

**Test Cases**:

- "Should I trade X for Y?" with known optimal answers
- Vary by: stats comparison, market demand mismatch, user preference alignment

**Metrics**:

- Accuracy: Does recommendation match expected answer?
- Reasoning completeness: Are all relevant factors considered?
- Explainability: Is the reasoning clear and actionable?

### Eval 2: RAG vs No-RAG Accuracy

**Hypothesis**: RAG improves accuracy on factual queries about collections and
history.

**Test Cases**:

- "What [type] Pokemon do I have?"
- "When did I last trade for [Pokemon]?"
- "What Pokemon are in high demand?"

**Metrics**:

- Factual accuracy against ground truth
- Retrieval precision (did it find the right documents?)
- Hallucination rate

### Eval 3: Memory Personalization

**Hypothesis**: Recommendations improve with memory of user preferences.

**Test Cases**:

- Same trade question, different user profiles
- Recommendation should change based on stated goals

**Metrics**:

- Preference alignment: Does recommendation match user's stated style?
- Context utilization: Does system reference relevant past context?

## Project Structure

```text
pokemon-trainer-platform-ai/
├── app.py                     # Main entry point
├── telemetry_setup.py         # OpenTelemetry initialisation
├── pyproject.toml             # Dependencies and tool config
├── pytest.ini                 # Test configuration
├── Makefile                   # Shortcuts for common commands
├── .env.example               # Template — copy to .env and fill in keys
├── chromadb_setup/            # ChromaDB Docker management scripts
│   └── chromadb-docker.sh
├── docs/
│   ├── GETTING_STARTED.md
│   ├── ARCHITECTURE.md        # This file
│   ├── REFERENCE/             # TESTING, LINTING, EVAL_RESULTS, MARKET_TRENDS
│   ├── ONBOARDING/            # Step-by-step onboarding guides
│   └── WALKTHROUGH/           # 14-phase deep-dive guides
│       ├── PHASES_OVERVIEW.md
│       ├── phase-01-project-setup.md
│       ├── phase-02-mock-data.md
│       ├── phase-03-memory-system.md
│       ├── phase-04-pii-guardrails.md
│       ├── phase-05-pokedex-expert.md
│       ├── phase-06-market-analyst.md
│       ├── phase-07-market-forecasting.md
│       ├── phase-08-legitimacy-guard.md
│       ├── phase-09-trade-advisor.md
│       ├── phase-10-multi-agent-orchestration.md
│       ├── phase-11-cli-interface.md
│       ├── phase-12-trade-offers.md
│       ├── phase-13-evaluations.md
│       └── phase-14-mcp-server.md
├── src/
│   ├── __init__.py
│   ├── startup.py
│   ├── config.py
│   ├── utils.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── trade_advisor_core.py      # Orchestrator: deps, system prompt, agent
│   │   ├── trade_advisor_tools.py     # @trade_advisor.tool functions
│   │   ├── trade_advisor_api.py       # Public async entry points
│   │   ├── trade_advisor.py           # Re-export facade
│   │   ├── pokedex_expert.py
│   │   ├── trade_market_analyst.py
│   │   ├── battle_strategy_advisor.py
│   │   ├── legitimacy_guard.py
│   │   └── trade_analytics.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   └── commands.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── generator.py
│   │   ├── loader.py
│   │   ├── tiers.py
│   │   └── value_scoring.py
│   ├── evals/
│   │   ├── __init__.py
│   │   ├── cases.py
│   │   ├── scoring.py
│   │   ├── eval_trade_advisor.py
│   │   └── eval_rag_comparison.py
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── pii_filter.py
│   │   └── middleware.py
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── tools.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── user_preferences.py
│   │   └── conversation_memory.py
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── observability.py
│   │   └── telemetry_start.py
│   └── rag/
│       ├── __init__.py
│       ├── vector_store.py
│       ├── ingest.py
│       ├── smogon_ingest.py
│       ├── pokeapi_fetcher.py
│       └── smogon_fetcher.py
├── data/                      # Runtime data (created on first use, gitignored)
│   ├── memory.db
│   ├── platform_trades.json
│   └── user_collection.json
└── tests/                     # Mirrors src/ layout
    ├── conftest.py
    ├── agents/
    │   ├── test_trade_advisor.py
    │   ├── test_trade_analytics.py
    │   ├── test_multi_agent.py
    │   ├── test_pokedex_agent.py
    │   ├── test_legitimacy_guard.py
    │   └── test_trade_offers.py
    ├── cli/test_cli.py
    ├── core/
    │   ├── test_config.py
    │   └── test_startup_validation.py
    ├── data/test_data.py
    ├── evals/
    │   ├── test_evals.py
    │   └── test_evals_execution.py
    ├── guardrails/test_guardrails.py
    ├── mcp/test_mcp_server.py
    ├── memory/
    │   ├── test_memory.py
    │   └── test_memory_persistence.py
    └── rag/test_rag.py        # requires_chromadb marker
```

## Mock Data Schemas

### Platform Trade History

File: `data/platform_trades.json`

```json
{
  "trades": [
    {
      "trade_id": "t001",
      "timestamp": "2024-01-15T10:30:00Z",
      "offered_pokemon": "pikachu",
      "requested_pokemon": "eevee",
      "status": "completed",
      "user_a_id": "user_123",
      "user_b_id": "user_456"
    },
    {
      "trade_id": "t002",
      "timestamp": "2024-01-15T14:22:00Z",
      "offered_pokemon": "geodude",
      "requested_pokemon": "machop",
      "status": "completed",
      "user_a_id": "user_789",
      "user_b_id": "user_012"
    },
    {
      "trade_id": "t003",
      "timestamp": "2024-01-16T09:15:00Z",
      "offered_pokemon": "abra",
      "requested_pokemon": "gastly",
      "status": "rejected",
      "user_a_id": "user_123",
      "user_b_id": "user_345"
    }
  ]
}
```

### User Collection

File: `data/user_collection.json`

```json
{
  "user_id": "user_123",
  "pokemon": [
    {
      "pokemon_id": "charizard",
      "nickname": "Blaze",
      "acquired_date": "2024-01-01",
      "acquired_via": "evolution",
      "tradeable": false
    },
    {
      "pokemon_id": "alakazam",
      "nickname": null,
      "acquired_date": "2024-01-10",
      "acquired_via": "trade",
      "tradeable": true
    },
    {
      "pokemon_id": "pikachu",
      "nickname": "Sparky",
      "acquired_date": "2024-01-05",
      "acquired_via": "catch",
      "tradeable": true
    }
  ],
  "preferences": {
    "favorite_types": ["fire", "psychic"],
    "goal": "build_psychic_team",
    "trading_style": "value_focused",
    "never_trade": ["charizard"],
    "seeking": ["gengar", "hypno", "mewtwo"]
  },
  "trade_history": [
    {
      "trade_id": "t001",
      "date": "2024-01-15",
      "gave": "pikachu",
      "received": "eevee",
      "satisfied": true
    }
  ]
}
```

## Example Interaction Flow

**User**: Should I trade my Alakazam for their Machamp?

### Step 1: Trade Advisor receives query

Orchestrator identifies this as a trade evaluation request.

### Step 2: Calls Pokedex Expert (Product Analysis)

- Gets Alakazam stats: High Sp. Attack (135), Psychic type, fully evolved
- Gets Machamp stats: High Attack (130), Fighting type, fully evolved
- Type analysis: Psychic beats Fighting, but both are fully evolved with
  similar total stats

### Step 3: Calls Trade Market Analyst (Market Analysis)

- Alakazam trade frequency: Requested 45 times, offered 20 times resulting in
  **high demand** (2.25x ratio)
- Machamp trade frequency: Requested 30 times, offered 35 times resulting in
  **lower demand** (0.86x ratio)

### Step 4: Checks User Memory (Personalization)

- User's goal: "Build competitive Psychic team"
- User's collection: Already has Alakazam (only Psychic type), no Machamp
- Trading style: "value_focused"
- Never-trade list: Alakazam not on it, but aligns with stated goal

### Step 5: Synthesizes Recommendation

**Trade Advisor**: I'd recommend against this trade. Here's why:

1. **Market value**: Alakazam is in higher demand on the platform (2.25x more
   requested than offered vs Machamp at 0.86x)
1. **Your goal**: You're building a Psychic team, and Alakazam is one of the
   best Psychic attackers with 135 Sp. Attack
1. **Collection fit**: Trading Alakazam would leave you with no Psychic types

If you want Fighting coverage, I could help you find a trade that doesn't
sacrifice your Psychic core. Would you like suggestions?

## Implementation Priority

Suggested build order:

1. **Set up project structure**: Create folder structure under `capstone/`
1. **Add dependencies to pyproject.toml**: httpx, sentence-transformers
1. **Create mock data**: Generate `platform_trades.json` with 100+ trades and
   create sample `user_collection.json`
1. **Build Pokedex Expert agent**: Ingest PokeAPI data into vector store and
   implement basic Pokemon queries
1. **Build Trade Market Analyst agent**: Query and analyze mock trade data
1. **Build Trade Advisor orchestrator**: Implement agent coordination and add
   memory system
1. **Add PII guardrails**
1. **Write and run evaluations**: Compare multi-agent vs single-agent and
   measure RAG impact
1. **Build simple CLI interface**
1. **(Optional) Create MCP server wrapper**

## Tech Stack Summary

| Component           | Technology                                   |
| ------------------- | -------------------------------------------- |
| Agent Framework     | Pydantic AI                                  |
| Vector Database     | ChromaDB (HTTP API v2)                       |
| Structured Database | SQLite                                       |
| Embeddings          | Hash-based (default) or Ollama               |
| Observability       | OpenTelemetry / Pydantic Logfire             |
| External API        | PokeAPI                                      |
| Interface           | Rich CLI                                     |
| MCP (Optional)      | Pydantic MCP SDK                             |

## Skills Demonstrated

This project demonstrates proficiency in:

| Skill Category         | Specific Skills                       |
| ---------------------- | ------------------------------------- |
| AI/ML Engineering      | Multi-agent orchestration, RAG        |
| Data Engineering       | ETL, vector DB, data modeling         |
| Software Architecture  | Microservices, separation of concerns |
| Product Thinking       | Recommendations, personalization      |
| Privacy and Compliance | PII detection, data minimization      |
| DevOps                 | Observability, tracing, monitoring    |
| Evaluation             | A/B testing, metric design            |

## Integration with Pokemon Trainer Platform

Once complete, this Second Brain can be integrated with your
[pokemon-trainer-platform][pokemon-platform] as:

1. **MCP Server**: Expose the Trade Advisor as an MCP tool that the platform
   can call
1. **API Endpoint**: Wrap the Trade Advisor in a FastAPI endpoint
1. **Embedded Module**: Import the agents directly into your platform codebase

The modular architecture allows any of these integration patterns.

## Reusing Existing Repo Components

This capstone leverages existing repo infrastructure:

| Component       | Source                |
| --------------- | --------------------- |
| OTEL Setup      | `telemetry_setup.py`  |
| ChromaDB Setup  | `chromadb_setup/`     |
| Dependency Mgmt | Root `pyproject.toml` |
| Python Env      | `uv.lock`             |

[pokemon-platform]: https://github.com/jazicorn-tw/pokemon-trainer-platform
