# Stage 5: Pokedex Expert

## Overview

Stage 5 introduces the first specialized agent: the **Pokedex Expert**. It answers questions about
Pokemon stats, types, abilities, and comparisons by retrieving data from a **ChromaDB vector store**
(RAG) populated with PokeAPI data. The agent also has access to the user's personal collection.

This phase establishes the RAG pattern used throughout the system: ingest external data into
ChromaDB, embed it, and retrieve relevant chunks at query time.

## Where It Fits

```text
Stage 1: Infrastructure (ChromaDB running)
Stage 2: Mock Data (user_collection.json for context)
        |
Stage 5: Pokedex Expert (RAG agent)
        |
Stage 11: Multi-Agent Orchestration (Trade Advisor calls Pokedex Expert as a tool)
Stage 8:  Evaluations (RAG accuracy is measured)
```

## Key Files

| File | Role |
| --- | --- |
| `src/agents/pokedex_expert.py` | Defines the `pokedex_expert` Pydantic AI agent, `PokedexDependencies`, `TYPE_CHART`, and the `query_pokedex()` public entry point |
| `src/rag/vector_store.py` | `PokemonVectorStore`: wraps ChromaDB HTTP v2 API with embed, upsert, and semantic search |
| `src/rag/ingest.py` | Fetches 40 Pokemon from PokeAPI (or cache), formats them as documents, and ingests into ChromaDB |
| `src/rag/pokeapi_fetcher.py` | `fetch_and_process_pokemon()`: fetches raw PokeAPI data + species data and returns structured dicts |

## Key Concepts

### Hash-based deterministic embeddings

By default the system uses `get_simple_embedding()` from `vector_store.py`: SHA-384 hash of the
lowercased text, bytes normalized to `[0, 1]`. This produces a 48-float vector. No GPU, no Ollama,
no network call required — output is always the same for the same input.

The trade-off: hash-based vectors have no semantic meaning. "fire dragon" and "flying fire" produce
completely different embeddings even though they are semantically close. For better retrieval
quality, enable `USE_OLLAMA_EMBEDDINGS=true` with Ollama running and the `nomic-embed-text` model
pulled.

### ChromaDB HTTP v2 API

`PokemonVectorStore` talks directly to ChromaDB's REST API at
`/api/v2/tenants/default_tenant/databases/default_database`. All HTTP calls use `httpx`. This avoids
the ChromaDB Python client dependency entirely and makes the integration explicit and easy to debug
with curl.

### Three tools on the agent

- `search_pokemon(query)` — queries ChromaDB and returns top-3 document chunks as plain text
- `get_type_effectiveness(attacking_type, defending_type)` — looks up `TYPE_CHART` (17 hardcoded
  matchups); returns "normal effectiveness (1x)" for anything not in the chart
- `get_my_collection()` — calls `load_user_collection(user_id)` and formats the user's tradeable
  Pokemon and preferences as plain text

### Local disk cache for PokeAPI

`pokeapi_fetcher.py` writes raw PokeAPI JSON to `data/pokemon_cache/<name>.json` and
`data/pokemon_cache/<name>_species.json`. Subsequent ingest runs read from cache. The cache already
exists in the repo for all 40 indexed Pokemon, so the ingest script will not hit the network unless
the cache files are deleted.

## Exploring the Code

Start with `src/rag/vector_store.py`. Read `_create_document_text()` to see how a Pokemon dict
becomes a single searchable string (name, types, stats, abilities, legendary/mythical flags, Pokedex
description). Then read `add_pokemon()` to see the batch embed-and-upsert pattern. Then read
`query()` to see how an embedded query string returns `[{document, metadata, distance}]` results.

In `src/agents/pokedex_expert.py`, look at `PokedexDependencies` — it holds an optional
`PokemonVectorStore` and a `user_id` string. Read the system prompt to understand the agent's
decision rules. Finally, look at `query_pokedex()` — it constructs deps, runs the agent, and ensures
the HTTP client is closed in the `finally` block.

In `src/rag/ingest.py`, the `POKEMON_TO_INDEX` list names 40 Pokemon. `ingest_pokemon_data()` calls
`fetch_and_process_pokemon()` (which reads from cache or PokeAPI), then calls `store.add_pokemon()`.
Run this once when setting up a new ChromaDB instance.

## Running the Code

```bash
# One-time: ingest Pokemon data into ChromaDB (requires ChromaDB running)
# Cache already exists so this will not hit PokeAPI
uv run python -m src.rag.ingest

# Query the Pokedex Expert directly (requires API key)
uv run python -c "
import asyncio
from agents import query_pokedex
result = asyncio.run(query_pokedex('What are Charizard strengths and weaknesses?'))
print(result)
"

# Inspect raw vector store results without an agent
uv run python -c "
import sys; sys.path.insert(0, 'src')
from rag.vector_store import PokemonVectorStore
store = PokemonVectorStore()
results = store.query('fire dragon flying', n_results=3)
for r in results:
    print(r['document'][:120])
store.close()
"

# Verify the type chart directly
uv run python -c "
import sys; sys.path.insert(0, 'src')
from agents.pokedex_expert import TYPE_CHART
print(TYPE_CHART.get(('fire', 'grass')))
print(TYPE_CHART.get(('fairy', 'dragon')))
print(TYPE_CHART.get(('normal', 'normal'), 'normal effectiveness (1x)'))
"
```

## Running the Tests

```bash
# Agent structure, type chart, and async integration (no ChromaDB needed)
uv run pytest tests/agents/test_pokedex_agent.py -v

# Vector store and embedding (ChromaDB required — interactive Docker prompt shown)
uv run pytest tests/rag/test_rag.py -v

# Skip ChromaDB tests entirely
uv run pytest tests/rag/test_rag.py::TestExtractPokemonInfo tests/rag/test_rag.py::TestEmbedding tests/rag/test_rag.py::TestDockerHelpers -v
```

### What the tests cover

`test_pokedex_agent.py`:

- `TestTypeChart` — verifies fire beats grass, water beats fire, chart is non-empty
- `TestPokedexDependencies` — verifies `vector_store=None` is accepted without error
- `TestPokedexExpertAgent` — verifies agent has a system prompt and a configured model
- `TestPokedexAgentIntegration` — four async tests using `FunctionModel` to drive the agent without
  a live LLM: search with a mock store, search with no store (graceful fallback), type effectiveness
  for a known matchup, type effectiveness for an unknown matchup

`test_rag.py`:

- `TestExtractPokemonInfo` — verifies basic field extraction and species data (legendary flag,
  description)
- `TestEmbedding` — verifies determinism, different inputs produce different outputs, values
  normalized to `[0, 1]`, output length is 48
- `TestDockerHelpers` — verifies platform-specific Docker start commands (darwin, win32, linux)
- `TestPokemonVectorStore` — two integration tests that require ChromaDB:
  `test_create_document_text` and `test_add_and_query_pokemon`

## Common Gotchas

### Must ingest before querying

ChromaDB starts empty. Run `uv run python -m src.rag.ingest` at least once after starting a new
ChromaDB container. The Pokemon cache already exists so the ingest is fast (no network calls).

### ChromaDB required for vector store tests

`tests/rag/test_rag.py::TestPokemonVectorStore` requires ChromaDB. The `ensure_chromadb` fixture
offers to start Docker interactively. Skip it with `-m "not requires_chromadb"` or by naming only
the non-ChromaDB test classes.

### Embedding dimension is 48, not 384

The `get_simple_embedding()` function has a `dim=384` parameter but SHA-384 only produces 48 bytes.
Slicing 48 bytes with `[:384]` returns all 48. The effective vector dimension is always 48. The test
asserts `len(result) == 48`. Do not expect 384-dimensional vectors.

### `PokedexDependencies` uses `model_construct` in some tests

When passing a `MagicMock` as `vector_store`, use
`PokedexDependencies.model_construct(vector_store=mock_store)` instead of
`PokedexDependencies(vector_store=mock_store)` to bypass Pydantic type validation.
