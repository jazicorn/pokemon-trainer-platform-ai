# How to Contribute

This file covers what to change, how to verify the change worked, and how
to debug when it does not.

---

## Understand the Layers First

The codebase has a layered architecture where lower layers are dependencies
of higher ones. Changes to low-level layers (like config or data models) can
break everything above them. Changes to agents are largely self-contained.

```text
CLI (highest level — presentation layer)
    ↑
Trade Advisor (orchestrator agent)
    ↑
Specialist Agents (Pokedex Expert, Market Analyst, Legitimacy Guard)
    ↑
RAG + Memory + Analytics (data access layer)
    ↑
Config + Data Models (foundation)
```

The full phase-by-phase breakdown of this dependency structure is in
[`docs/WALKTHROUGH/PHASES_OVERVIEW.md`](../WALKTHROUGH/PHASES_OVERVIEW.md).
If you are making a significant change, read the relevant phase doc first —
it explains the design intent.

---

## The Most Common Things You Might Change

### Add a new tool to an existing agent

Tools are Python `async` functions decorated with `@agent.tool`. The Pokedex
Expert is the cleanest example:

```python
# src/agents/pokedex_expert.py

@pokedex_expert.tool
async def search_pokemon(
    ctx: RunContext[PokedexDependencies],
    query: str,
) -> str:
    """Search for Pokemon information in the knowledge base."""
    results = ctx.deps.vector_store.query(query, n_results=3)
    return "\n\n".join(r["document"] for r in results)
```

The pattern:

1. Decorate with `@<agent_name>.tool`
2. First argument is always `ctx: RunContext[<DependenciesType>]`
3. Additional arguments become the parameters the LLM passes when calling
  the tool
4. The docstring becomes the tool description the LLM sees — write it clearly
5. Return a string (the LLM reads whatever you return)
6. Access injected dependencies via `ctx.deps`

After adding a tool:

- Add a test in the corresponding test file (e.g.,
  `tests/agents/test_pokedex_agent.py`)
- The LLM will discover and use the tool automatically based on the docstring
  and argument names

### Change how an agent behaves or responds

Edit the `SYSTEM_PROMPT` string in the agent file. This is the single most
impactful change you can make — it controls the LLM's persona, its
decision-making rules, and how it formats responses.

The system prompts are near the top of each agent file:

- `src/agents/trade_advisor_core.py` — contains the system prompt with
  detailed operating modes and instruction for when to call each tool
- `src/agents/pokedex_expert.py` — instructs the agent to always base answers
  on retrieved data
- `src/agents/trade_market_analyst.py` — instructs the agent on how to
  interpret market signals
- `src/agents/legitimacy_guard.py` — instructs the agent on risk assessment
  and what to flag

When experimenting with system prompts, run the app (`make run`) and try a
few queries manually to see if the behavior changed as expected. Phoenix
tracing (see below) shows you exactly what the LLM was working with.

### Add more Pokemon to the knowledge base

1. Open `src/rag/ingest.py`
2. Find the `POKEMON_TO_INDEX` list
3. Add the Pokemon names you want (lowercase, matching the PokeAPI name format)
4. Run `make ingest` to re-index

The PokeAPI names for special cases: `mr-mime`, `farfetchd`, `nidoran-f`,
`nidoran-m`. Check `https://pokeapi.co/api/v2/pokemon/{name}` to verify a
name works before adding it.

### Switch which LLM the app uses

Set the `POKEMON_MODEL` environment variable:

```bash
POKEMON_MODEL=gpt-4o make run        # GPT-4o
POKEMON_MODEL=gemini-flash make run  # Gemini Flash
POKEMON_MODEL=llama make run         # Ollama (local, no API key needed)
```

Available model keys are in `src/config.py` under the `MODELS` dictionary.

### Change the mock user collection

Edit `data/user_collection.json` directly. The structure is straightforward
— a list of owned Pokemon plus a preferences object with `goal`, `seeking`,
`never_trade`, and `favorite_types`. Changes take effect on the next app
startup.

---

## Running Tests

Run the full test suite (excluding ChromaDB integration tests that require
the service):

```bash
uv run pytest tests/ -v --tb=short -m "not requires_chromadb"
```

Run tests for a specific component:

```bash
uv run pytest tests/agents/test_pokedex_agent.py -v
uv run pytest tests/agents/test_legitimacy_guard.py -v
```

Run with full tracebacks on failure:

```bash
uv run pytest tests/ --tb=long
```

Run the ChromaDB integration tests (requires `make chromadb-start` first):

```bash
make test-rag
```

Most tests mock the LLM, so they run without API keys and complete in
seconds. See [`docs/REFERENCE/TESTING.md`](../REFERENCE/TESTING.md) for the
async patterns used in tests and guidance on writing new ones.

---

## Linting

The project uses `pyright` for type checking and `ruff` for formatting
and linting. Run before committing:

```bash
uv run pyright src/
uv run ruff check src/
```

See [`docs/REFERENCE/PYRIGHT.md`](../REFERENCE/PYRIGHT.md) for the full setup, VS Code
integration, and which checks are disabled and why.

---

## Debugging When Something Goes Wrong

### "ChromaDB is unreachable"

Docker is not running, or the ChromaDB container stopped.

```bash
make chromadb-status   # Check if container is up
make chromadb-start    # Start it if not
```

### "API key is empty" or "contains a 1Password URI"

Your environment variable did not resolve correctly.

- Simple `.env` approach: verify the `.env` file exists in the project root and
  has the correct key
- 1Password approach: run `eval $(op signin)` first, then `make run`
  (which uses `op run`)

### Wrong output from an agent

The agent is producing unexpected responses. To understand why, you need to
see what data the LLM was working with.

#### Option 1: Add a print statement

Add a `print()` to the tool function that is returning unexpected results.
This shows you the raw data before the LLM interprets it.

#### Option 2: Use Phoenix tracing (recommended)

Start the app with telemetry enabled (type `y` at the startup prompt). Open
`http://127.0.0.1:6006`. You will see a trace for every request showing:

- Which tools were called, in what order
- The exact arguments passed to each tool
- The exact response each tool returned
- The full LLM prompt and response at each step

This is the fastest way to diagnose unexpected agent behavior.

#### Option 3: Check the system prompt

Open the agent file and read the `SYSTEM_PROMPT`. Is the agent following
instructions correctly? System prompt issues produce consistent wrong
behavior across many different queries.

### A test is failing

Run just that test with `--tb=long` for the full traceback:

```bash
uv run pytest tests/agents/test_trade_advisor.py::TestSomeClass::test_something -v --tb=long
```

If the test is an async test (most agent tests are), see
[`docs/REFERENCE/TESTING.md`](../REFERENCE/TESTING.md) for the `@pytest.mark.asyncio` pattern
and how mocked LLM responses work.

### Import errors

Usually means you are running Python from the wrong directory or without
`uv`:

```bash
# Wrong
python app.py

# Right — from the project root
uv run python app.py
```

The project adds `src/` to the Python path at startup, so
`from agents.trade_advisor import ...` works. Running `python` directly
without `uv` skips this.

---

## Optional: Using Phoenix for Observability

Phoenix is a tracing UI that shows you a visual timeline of every agent
call. It is optional — the app works without it — but it is invaluable when
debugging agent behavior.

**Start it:**

When the app asks "Enable telemetry? (y/N)", type `y`. The app will start
Phoenix automatically (requires Docker).

**Open it:**

```text
http://127.0.0.1:6006
```

**What you see:**

Every request appears as a trace. Expand a trace to see the full span
hierarchy: the Trade Advisor call, the specialist agent calls it triggered,
each tool call within those agents, and the LLM prompt/response at every
step. You can see exactly what data the LLM had when it produced its output.

---

## Deeper Reading

Once you have a solid foundation, these docs go deeper on specific
components:

| Resource | What it covers |
| --- | --- |
| [`docs/WALKTHROUGH/PHASES_OVERVIEW.md`](../WALKTHROUGH/PHASES_OVERVIEW.md) | Phase-by-phase breakdown of every component with test commands |
| [`ARCHITECTURE.md`](../../ARCHITECTURE.md) | Full architecture reference: business analogies, data source details, worked examples |
| [`docs/WALKTHROUGH/phase-05-pokedex-expert.md`](../WALKTHROUGH/phase-05-pokedex-expert.md) | Deep dive on RAG and the Pokedex Expert |
| [`docs/WALKTHROUGH/phase-09-trade-advisor.md`](../WALKTHROUGH/phase-09-trade-advisor.md) | Deep dive on the Trade Advisor orchestrator |
| [`docs/WALKTHROUGH/phase-10-multi-agent-orchestration.md`](../WALKTHROUGH/phase-10-multi-agent-orchestration.md) | How agents delegate to each other |
| [`docs/REFERENCE/EVAL_RESULTS.md`](../REFERENCE/EVAL_RESULTS.md) | RAG vs. no-RAG evaluation results |
| [`docs/REFERENCE/TESTING.md`](../REFERENCE/TESTING.md) | Testing patterns, async tests, mocking LLM responses |

---

You are ready to contribute.
