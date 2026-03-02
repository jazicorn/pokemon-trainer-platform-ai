# Glossary

Quick-reference definitions for every term you will encounter in this codebase.
Each entry includes "In this project:" to connect the concept to the actual
implementation.

---

## Agent (AI Agent)

An AI agent is a Large Language Model that has been given access to tools —
Python functions it can call to get real information or take real actions. The
LLM decides when to call a tool, what arguments to pass, and how to use the
result in its final response. Agents can do more than just generate text: they
can retrieve data, run calculations, check databases, and interact with external
services.

*In this project:* There are four agents — Trade Advisor, Pokedex Expert, Trade
Market Analyst, and Legitimacy Guard. Each is an LLM with a set of specific
Python tools.

---

## ChromaDB

An open-source vector database. Stores documents as numerical vectors so they
can be searched by meaning rather than by keywords. Runs as a Docker container
and exposes an HTTP API.

*In this project:* ChromaDB stores the Pokemon knowledge base (stats, types,
abilities) ingested from the PokeAPI. The Pokedex Expert queries it to retrieve
relevant documents before answering questions.

---

## Colima

A lightweight container runtime for macOS. An alternative to Docker Desktop
that runs Docker containers without requiring the full Docker Desktop
application. Manages a Linux virtual machine on macOS that containers run
inside.

*In this project:* Required on macOS to run ChromaDB. The startup script
handles installing and starting Colima automatically, including recovering from
VM crashes.

---

## Demand Ratio

The ratio of how many times a Pokemon was requested in trades to how many times
it was offered. A demand ratio above 1.0 means more traders want it than are
giving it away; below 1.0 means the opposite.

*In this project:* Calculated by the `TradeAnalytics` class from the mock
platform trade history. The Market Analyst uses it to classify demand level and
compare trade value.

---

## Embedding / Embedding Model

A mathematical representation of text as a list of numbers (a vector). An
embedding model converts a piece of text into this representation. Text with
similar meaning produces similar vectors, enabling semantic search.

*In this project:* Pokemon documents are converted to embeddings and stored in
ChromaDB. By default, a hash-based embedding function is used (fast but not
truly semantic). Set `USE_OLLAMA_EMBEDDINGS=true` to use the Ollama
`nomic-embed-text` model for real semantic embeddings.

---

## Hallucination

When an AI language model generates a response that sounds plausible and
confident but is factually incorrect. Hallucination occurs because LLMs predict
likely text rather than look up facts — they can produce wrong answers with high
apparent confidence.

*In this project:* RAG (retrieval-augmented generation) reduces hallucination
in the Pokedex Expert by giving the LLM real Pokemon data before it responds.
The Legitimacy Guard uses hardcoded data to eliminate hallucination entirely for
legality checks.

---

## Hierarchical Delegation

An architecture pattern where one orchestrator agent routes work to specialized
worker agents. The orchestrator does not do the specialized work itself — it
delegates and synthesizes.

*In this project:* The Trade Advisor is the orchestrator. It delegates Pokemon
lookups to the Pokedex Expert, market analysis to the Market Analyst, and fraud
checks to the Legitimacy Guard. This is also called the "Master-Worker" pattern.

---

## LLM (Large Language Model)

A neural network trained on massive amounts of text that learned statistical
patterns in language. Given text input (a prompt), it generates a continuation
token by token. Modern LLMs can answer questions, write code, analyze data, and
follow complex instructions — all as forms of sophisticated text generation.

*In this project:* The reasoning engine inside every agent. Supported LLMs are
Claude (Anthropic), GPT-4 (OpenAI), Gemini (Google), and Llama (via Ollama).
Configured via the `POKEMON_MODEL` environment variable.

---

## Momentum Score

A measure of how a Pokemon's trading demand is changing over time. Calculated
by comparing the 7-day demand ratio to the 30-day demand ratio. Positive
momentum means demand is rising; negative means it is falling.

*In this project:* `Momentum = ((ratio_7day - ratio_30day) / ratio_30day) *
100`. Above +15% is classified as Bullish; below -15% is Bearish; between is
Stable. Used by the Market Analyst to generate trade recommendations.

---

## Bullish / Bearish / Stable

Market sentiment classifications based on momentum score.

- **Bullish** (momentum > +15%): demand is accelerating — may be a good time
  to hold rather than trade away
- **Bearish** (momentum < -15%): demand is cooling — may be a good time to
  trade while value is higher
- **Stable** (between -15% and +15%): steady market with no strong direction

*In this project:* Returned by the `get_market_forecast()` tool in the Trade
Market Analyst.

---

## Multi-Agent System

A system where multiple AI agents work together, each handling a specialized
part of a larger task. One agent (the orchestrator) coordinates the others (the
workers/specialists). Each specialist has its own system prompt, tools, and data
access.

*In this project:* The Trade Advisor orchestrates the Pokedex Expert, Market
Analyst, and Legitimacy Guard. Each agent is in its own file under
`src/agents/`.

---

## Orchestrator

The coordinating agent in a multi-agent system. It receives the user's request,
decides what information is needed, delegates to the appropriate specialist
agents, and synthesizes their outputs into a final response.

*In this project:* The Trade Advisor (`src/agents/trade_advisor.py`) is the
orchestrator. It is the only agent that the CLI talks to directly.

---

## pydantic-ai

A Python library for building AI agents with type safety and structured
outputs. Uses Pydantic's data validation to ensure that tool inputs and outputs
match their declared types. Built by the team behind Pydantic.

*In this project:* The framework all four agents are built with. The
`Agent(model_id, deps_type=..., system_prompt=...)` instantiation and the
`@agent.tool` decorator are pydantic-ai constructs.

---

## RAG (Retrieval Augmented Generation)

A technique for grounding LLM responses in real data. Before asking the LLM to
answer, relevant documents are retrieved from a knowledge base and included in
the prompt as context. The LLM reasons over real, specific data rather than
relying on training memory.

*In this project:* The Pokedex Expert uses RAG. When you ask about a Pokemon,
`search_pokemon()` retrieves the relevant ChromaDB documents before the LLM
produces its response. RAG improved answer accuracy by +15.8% in the project's
evaluation (see `docs/REFERENCE/EVAL_RESULTS.md`).

---

## Rich

A Python library for rendering formatted text in the terminal. Supports colored
output, tables, panels, progress bars, and markdown rendering.

*In this project:* Used by `src/cli/app.py` to render the formatted responses,
panels, and tables you see in the terminal.

---

## SQLite

A lightweight, file-based relational database. No server required — the
database is a single `.db` file. Supports standard SQL queries.

*In this project:* Used to persist user preferences, conversation history, and
trade offer records across sessions. The database file is at `data/memory.db`
and is created automatically on first run.

---

## System Prompt

The instructions given to an LLM agent before any user interaction. Controls
the agent's persona, decision-making rules, response style, and when to call
which tools. The most impactful single thing you can change in an agent.

*In this project:* Each agent file has a `SYSTEM_PROMPT` string near the top.
For example, the Trade Advisor's system prompt defines five operating modes
(Market Intelligence, Trade Evaluation, General Inquiries, Outgoing Offers,
Offer Management) and detailed instructions for each.

---

## Tool (AI Agent Tool)

A Python function that an AI agent can call during its reasoning process. The
LLM sees the function's name, docstring, and parameter names, and decides when
to call it based on the user's request. The tool runs as regular Python code
and returns a string result that the LLM incorporates into its response.

*In this project:* Tools are decorated with `@agent.tool`. The Pokedex Expert
has `search_pokemon`, `get_type_effectiveness`, and `get_my_collection`. The
Trade Advisor has over a dozen tools, including calls that run the specialist
agents.

---

## uv

A fast Python package manager and environment manager. A faster, more reliable
alternative to `pip` and `venv`. Reads from `pyproject.toml` to manage
dependencies.

*In this project:* Used for all Python operations. `uv sync --extra capstone`
installs dependencies. `uv run python app.py` runs the app using the managed
virtual environment. The virtual environment is at `.venv/` in the repo root
(not inside `capstone/`).

---

## Vector Database

A database that stores data as vectors (lists of numbers representing meaning)
and supports semantic search — finding the closest matches by meaning rather
than by keyword. See also: Embedding.

*In this project:* ChromaDB is the vector database. It stores Pokemon knowledge
documents and supports semantic queries from the Pokedex Expert agent.

---

## Worker Agent

A specialist agent in a multi-agent system that handles one specific domain.
Receives requests from the orchestrator, performs a focused task, and returns
results. Distinct from the orchestrator, which coordinates without doing
specialized work itself.

*In this project:* The Pokedex Expert, Trade Market Analyst, and Legitimacy
Guard are worker agents. They are called by the Trade Advisor orchestrator via
tool functions.
