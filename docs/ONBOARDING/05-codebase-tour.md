# Codebase Tour

This file maps the directory structure to the concepts you understand from the
previous files. After reading this, you can navigate to any file with purpose.

---

## Repository Layout

```text
pokemon-trainer-platform-ai/
├── app.py                    ← Entry point — run this
├── Makefile                  ← Shortcuts for common commands
├── pyproject.toml            ← Python dependencies
├── .env.example              ← Template — copy to .env and fill in keys
│
├── src/                      ← All application source code
│   ├── startup.py            ← Runs on startup: checks env, starts services
│   ├── config.py             ← All configuration (env-overridable)
│   │
│   ├── agents/               ← The five AI agents
│   │   ├── trade_advisor_core.py    ← Orchestrator: deps, system prompt, agent
│   │   ├── trade_advisor_tools.py   ← @trade_advisor.tool functions
│   │   ├── trade_advisor_api.py     ← Public async API
│   │   ├── trade_advisor.py         ← Re-export facade
│   │   ├── pokedex_expert.py        ← Pokemon knowledge (RAG)
│   │   ├── trade_market_analyst.py  ← Supply/demand analytics
│   │   ├── legitimacy_guard.py      ← Fraud detection
│   │   ├── battle_strategy_advisor.py ← Competitive Pokemon viability specialist
│   │   └── trade_analytics.py       ← Data engine (not an agent)
│   │
│   ├── cli/                  ← Command-line interface
│   │   ├── app.py            ← Main REPL loop, renders output
│   │   └── commands.py       ← Command parsing (what keywords mean what)
│   │
│   ├── rag/                  ← Vector search infrastructure
│   │   ├── vector_store.py   ← ChromaDB client wrapper
│   │   ├── ingest.py         ← One-time data ingestion script
│   │   └── pokeapi_fetcher.py ← Fetches from pokeapi.co
│   │
│   ├── memory/               ← Persistence layer
│   │   ├── database.py            ← SQLite helpers + trade offer CRUD
│   │   ├── user_preferences.py    ← Read/write user trading goals
│   │   └── conversation_memory.py ← Store and retrieve chat history
│   │
│   ├── data/                 ← Data models and loaders
│   │   ├── models.py         ← Pydantic models (Trade, UserCollection, etc.)
│   │   ├── loader.py         ← Loads JSON files into typed objects
│   │   └── generator.py      ← Generates mock data (make generate-data)
│   │
│   ├── guardrails/           ← Safety layer
│   │   ├── pii_filter.py     ← Regex-based PII detection
│   │   └── middleware.py     ← Wraps agent calls with PII filtering
│   │
│   └── observability/        ← Telemetry
│       ├── observability.py  ← Phoenix startup + health checks
│       └── telemetry_start.py ← Prompts user to opt in at startup
│
├── data/                     ← Runtime data (created on first use, gitignored)
│   ├── memory.db             ← SQLite database
│   ├── platform_trades.json  ← Mock trade history
│   └── user_collection.json  ← Mock user collection
│
├── tests/                    ← Mirrors src/ layout (agents/, cli/, core/, …)
│
└── docs/                     ← Documentation
    ├── GETTING_STARTED.md
    ├── 1PASSWORD.md
    ├── REFERENCE/            ← TESTING, LINTING, MARKET_TRENDS, EVAL_RESULTS
    ├── ONBOARDING/           ← You are here
    └── WALKTHROUGH/          ← 14-phase deep-dive guides
```

---

## Entry Points: Where Execution Starts

### `app.py`

The script you run. It does three things:

1. Sets up the Python path so imports work from `src/`
2. Calls `startup()` to check the environment and start services
3. Launches the CLI with `asyncio.run(cli_main())`

It is intentionally short — all real logic is in `src/`.

### `src/startup.py`

Runs automatically before the CLI opens. It:

- Validates that the required API key is set for the selected LLM
- Creates the SQLite schema if the database file does not exist yet
- Asks whether to enable telemetry
- Starts ChromaDB via Docker if it is not already running
- Auto-recovers from Colima crashes on macOS

### `src/cli/app.py`

The main interactive loop. It:

- Reads user input from the terminal
- Passes it to `src/cli/commands.py` to determine what kind of command it is
- Calls the appropriate handler (sometimes the Trade Advisor agent,
  sometimes a direct function)
- Renders the response using the Rich library (colored panels, tables)
- Handles the two-stage confirmation flows for accepting offers and sending
  outgoing offers

### `src/config.py`

All configuration in one place. Worth reading in full — it is short (113
lines). Every value can be overridden by an environment variable. The `MODELS`
dictionary is where you can see all supported LLMs.

```python
# src/config.py

MODELS = {
    "claude-sonnet": ModelConfig(ModelProvider.ANTHROPIC, "claude-sonnet-4-6"),
    "claude-haiku":  ModelConfig(ModelProvider.ANTHROPIC, "claude-haiku-4-5"),
    "gemini-flash":  ModelConfig(ModelProvider.GEMINI,    "gemini-1.5-flash"),
    "gpt-4o":        ModelConfig(ModelProvider.OPENAI,    "gpt-4o"),
    "llama":         ModelConfig(ModelProvider.OLLAMA,    "llama3.2"),
    # ...
}

config = Config(
    default_model=os.getenv("POKEMON_MODEL", "claude-sonnet"),
    chromadb_url=os.getenv("CHROMADB_URL", "http://localhost:8000"),
    # ...
)
```

---

## The Agents: Where the Intelligence Lives

Every agent file has the same four-part structure:

1. **A `Dependencies` class** — what data the agent needs access to
2. **A `SYSTEM_PROMPT` string** — the instructions given to the LLM that
  control its behavior
3. **An `Agent(...)` instantiation** — connects the LLM model and dependencies
  type
4. **`@agent.tool` decorated functions** — the Python tools the LLM can call

Here is the full structure of the simplest agent, the Pokedex Expert:

```python
# src/agents/pokedex_expert.py (simplified)

class PokedexDependencies(BaseModel):
    """What data this agent has access to."""
    vector_store: PokemonVectorStore | None = None
    user_id: str = "user_001"

SYSTEM_PROMPT = """You are a Pokemon expert with deep knowledge of all Pokemon
species, their stats, types, abilities, and competitive viability.
...
Be concise but thorough. Always base your answers on the retrieved data."""

pokedex_expert = Agent(
    config.model_id,          # Which LLM model to use
    deps_type=PokedexDependencies,
    system_prompt=SYSTEM_PROMPT,
)

@pokedex_expert.tool
async def search_pokemon(ctx: RunContext[PokedexDependencies], query: str) -> str:
    """Search for Pokemon information in the knowledge base."""
    results = ctx.deps.vector_store.query(query, n_results=3)
    return "\n\n".join(r["document"] for r in results)

@pokedex_expert.tool
async def get_type_effectiveness(...) -> str:
    ...

@pokedex_expert.tool
async def get_my_collection(ctx: RunContext[PokedexDependencies]) -> str:
    ...
```

The pattern is identical in `trade_market_analyst.py` and `legitimacy_guard.py`.
The Trade Advisor is split across three files — `trade_advisor_core.py`
(dependencies + system prompt + agent), `trade_advisor_tools.py` (tools), and
`trade_advisor_api.py` (public async API) — with `trade_advisor.py` as a thin
re-export facade. Once you know this structure, you can read any agent file.

The `SYSTEM_PROMPT` is the most impactful thing you can change. It is the
instructions the LLM reads before every interaction — it controls the agent's
persona, its decision-making rules, and when to call which tool.

---

## RAG Infrastructure

### `src/rag/vector_store.py`

The `PokemonVectorStore` class. A thin wrapper around the ChromaDB HTTP client.

Key methods:

- `add_pokemon(pokemon_id, document, metadata)` — store a document in ChromaDB
- `query(query_text, n_results=3)` — semantic search, returns the top N most
  relevant documents
- `close()` — clean up the connection

### `src/rag/ingest.py`

Run once with `make ingest`. Fetches 40+ Pokemon from PokeAPI, formats them
into documents, and calls `add_pokemon()` for each. The list of Pokemon to
index is `POKEMON_TO_INDEX` — edit this list if you want to add more.

### `src/rag/pokeapi_fetcher.py`

Handles the raw HTTP calls to `https://pokeapi.co/api/v2/pokemon/{name}` and
converts the API response into the document format the vector store expects.
Has a local cache in `data/pokemon_cache/` to avoid re-fetching.

---

## Memory and Data

### `src/memory/database.py`

The SQLite layer. Contains:

- `init_db()` — creates the schema on first run
- `TradeOffersManager` — CRUD for the trade offers inbox and sent items
  - `seed_offers()` — public dispatcher: no-op when PostgreSQL is configured,
    otherwise seeds 5 mock offers on first inbox view
  - `get_inbox(user_id)` — pending incoming offers
  - `get_sent(user_id)` — outgoing offers you created
  - `update_status(offer_id, status)` — accept or decline

All five `TradeOffersManager` methods dispatch to PostgreSQL when
`PLATFORM_DB_URL` is set, falling back to SQLite when it is not.

### `src/data/platform_db.py`

Optional PostgreSQL client. Only active when `PLATFORM_DB_URL` is set.
`PlatformDBClient` wraps psycopg3 and provides the same interface as
`TradeOffersManager`'s SQLite methods. `get_platform_db()` is a
module-level singleton that returns `None` silently when the env var is
unset, so all callers fall back to mock data without any extra logic.

The `trade_offers` table is **shared read-write**: the web API inserts
offers; this project reads them and writes back `status` and `ai_analysis`.
All other tables (`trades`, `user_pokemon`, `user_preferences`,
`user_trade_history`) are read-only from this project's perspective.

### `src/memory/user_preferences.py`

Reads and writes user trading preferences (favorite types, trading goal,
never-trade list, seeking list). Backed by SQLite. The preferences inform the
Trade Advisor's `get_user_context()` tool.

### `src/memory/conversation_memory.py`

Stores and retrieves the conversation history per user session. Used by the
Trade Advisor's `get_recent_history()` tool so the agent has context about
what you discussed earlier in the session.

### `data/platform_trades.json`

Thousands of mock trade records. Each record has a timestamp, offered Pokemon,
requested Pokemon, user IDs, and status (COMPLETED, PENDING, REJECTED). The
`TradeAnalytics` class in `src/agents/trade_analytics.py` reads this on
startup and builds indexes for fast lookups.

### `data/user_collection.json`

The logged-in user's Pokemon and preferences. Loaded at startup by
`load_user_collection()` in `src/data/loader.py`. Modify this file to change
what collection the system thinks you have during local development.

---

## Safety Layer

### `src/guardrails/pii_filter.py`

Regex-based PII scanner. Detects email addresses, phone numbers, social
security numbers, and similar patterns in user input before it gets stored in
conversation history or sent to the LLM. Warns the user if PII is detected.

### `src/guardrails/middleware.py`

Wraps agent calls so the PII filter runs automatically. You do not call the
filter manually — it fires on every agent invocation.

---

## Tests

Tests mirror the `src/` layout — one subdirectory per module:

| Test file | What it covers |
| --- | --- |
| `core/test_config.py` | Config loading and env var overrides |
| `core/test_startup_validation.py` | Startup env var validation |
| `data/test_data.py` | Data model validation |
| `memory/test_memory.py` | SQLite operations |
| `memory/test_memory_persistence.py` | Cross-instance persistence |
| `guardrails/test_guardrails.py` | PII detection |
| `agents/test_pokedex_agent.py` | Pokedex Expert agent behavior (mocked LLM) |
| `agents/test_trade_analytics.py` | Market calculations |
| `agents/test_legitimacy_guard.py` | Ball legality rules |
| `agents/test_trade_advisor.py` | Orchestrator behavior (mocked LLM) |
| `agents/test_multi_agent.py` | Agent-to-agent delegation |
| `agents/test_trade_offers.py` | Offer management |
| `cli/test_cli.py` | CLI command parsing |
| `evals/test_evals.py` | Evaluation scoring unit tests |
| `evals/test_evals_execution.py` | End-to-end eval pipeline (mocked LLM) |
| `mcp/test_mcp_server.py` | MCP tool definitions |
| `rag/test_rag.py` | ChromaDB integration (`requires_chromadb` marker) |

Most tests mock the LLM so they run without API keys and without making
network calls. The LLM responses are deterministic in tests, making failures
reproducible.

See [`docs/REFERENCE/TESTING.md`](../REFERENCE/TESTING.md) for how to run
tests and the async testing patterns used.

---

**Next: [06-how-to-contribute.md](06-how-to-contribute.md)**
