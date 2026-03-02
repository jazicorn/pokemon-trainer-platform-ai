# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.1.0] — 2026-03-02

### Added — Core Platform (Phases 1–14)

#### Phase 1 — Project Setup & Infrastructure

- `src/config.py`: env-var-driven `Config` dataclass with multi-provider model registry
- `src/startup.py`: startup orchestration — SQLite init, ChromaDB health check,
  Phoenix boot with Colima prompt
- `src/observability/observability.py`: OpenTelemetry + Arize Phoenix tracing via
  `init_telemetry()`
- Docker pre-check with friendly Colima start prompt and Rich spinner on Phoenix startup

#### Phase 2 — Mock Data

- `src/data/models.py`: Pydantic models for `Pokemon`, `TradeOffer`, `UserCollection`,
  `MarketHistory`
- `src/data/generator.py`: deterministic mock trade and collection data generator
- `src/data/tiers.py` + `src/data/value_scoring.py`: rarity tier classification and
  value scoring
- `src/data/loader.py`: unified data-loading API (`load_user_collection`,
  `load_platform_trades`)

#### Phase 3 — Memory System

- `src/memory/database.py`: SQLite schema — users, preferences, conversation history,
  recommendations
- `src/memory/user_preferences.py`: CRUD for user trading goals, seeking list,
  never-trade list
- `src/memory/conversation_memory.py`: conversation history and recommendation
  persistence

#### Phase 4 — PII Guardrails

- `src/guardrails/pii_filter.py`: regex + heuristic PII detection (email, phone, SSN,
  credit card)
- `src/guardrails/middleware.py`: pre/post-processing middleware that scrubs PII from
  agent I/O

#### Phase 5 — Pokedex Expert (RAG Agent)

- `src/rag/pokeapi_fetcher.py`: PokeAPI client with structured `extract_pokemon_info()`
- `src/rag/vector_store.py`: ChromaDB-backed `PokemonVectorStore` with cosine
  similarity search
- `src/rag/ingest.py` + `src/rag/smogon_fetcher.py`: ingestion pipelines for PokeAPI
  and Smogon data
- `src/agents/pokedex_expert.py`: PydanticAI agent grounded in vector-store retrieval

#### Phase 6 & 7 — Market Analyst & Momentum Forecasting

- `src/agents/trade_market_analyst.py`: market analytics agent with structured report
  output
- `src/agents/trade_analytics.py`: momentum score —
  `((Ratio_7d − Ratio_30d) / Ratio_30d) × 100`
- Sentiment classification: Bullish (>+15%), Bearish (<−15%), Stable

#### Phase 8 — Legitimacy Guard

- `src/agents/legitimacy_guard.py`: compliance agent — ball legality, origin marks,
  rarity tiers
- Cross-references metadata that LLMs typically hallucinate (PokéBall provenance,
  Galar/Paldea marks)

#### Phase 9 & 10 — Trade Advisor & Multi-Agent Orchestration

- `src/agents/trade_advisor_core.py`: `AdvisorDependencies`, system prompt, PydanticAI
  agent
- `src/agents/trade_advisor_tools.py`: 12 `@trade_advisor.tool` functions
- `src/agents/trade_advisor_api.py`: public async API — `evaluate_trade`,
  `get_trade_suggestions`, `get_pending_offers`, `send_trade_offer`
- `src/agents/trade_advisor.py`: thin re-export facade for backward compatibility
- Master-Worker delegation pattern — Trade Advisor routes to Legitimacy Guard,
  Market Analyst, Pokedex Expert

#### Phase 11 — CLI Interface

- `src/cli/app.py`: Typer + Rich interactive CLI with `status`, `prefs`, `help`,
  `reset` commands
- `status` and `prefs` commands rendered as matching Rich Table layouts
- `PendingConfirmation` dataclass with 5-minute expiry and tightened accept regex

#### Phase 12 — Trade Offers

- Trade inbox/outbox: view pending offers, accept/decline with typed confirmation flow
- `send_trade_offer()` and `get_pending_offers()` wired to Trade Advisor agent tools

#### Phase 13 — Evaluations

- `src/evals/cases.py` + `src/evals/scoring.py`: pydantic-evals dataset with keyword
  and recommendation scorers
- `src/evals/eval_trade_advisor.py`: trade advisor evaluation — 4 cases,
  avg `recommendation_score: 0.5`
- `src/evals/eval_rag_comparison.py`: RAG vs no-RAG diff — **+15.8% keyword
  accuracy**, +100% on multi-hop questions
- Results captured in `docs/REFERENCE/EVAL_RESULTS.md`

#### Phase 14 — MCP Server (Optional)

- `src/mcp_server/server.py` + `src/mcp_server/tools.py`: Model Context Protocol
  server exposing `query_pokedex`, `get_market_data`, `evaluate_trade` as MCP tools
- `user_id` passed through all MCP tool calls for per-user memory context

### Infrastructure & Tooling

- `pytest.ini`: `asyncio_mode = strict`, `requires_chromadb` marker registration
- `Makefile`: `test`/`test-live` use `-m "not requires_chromadb"`, `test-rag` uses
  `-m "requires_chromadb"`; `phoenix-start`/`phoenix-stop` targets added
- `pyproject.toml`: switched from basedpyright to pyright; `[tool.pyright]` with
  `extraPaths = ["src"]`, strict mode with selective suppressions
- `docs/`: full onboarding suite — `GETTING_STARTED.md`, `ARIZE_PHOENIX_SETUP.md`,
  `1PASSWORD.md`, `REFERENCE/`, `ONBOARDING/`, `TROUBLESHOOTING/`,
  `WALKTHROUGH/` (14 phase guides)

---

[Unreleased]: https://github.com/jasmineanderson/pokemon-trainer-platform-ai/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jasmineanderson/pokemon-trainer-platform-ai/releases/tag/v0.1.0
