<!-- markdownlint-disable MD033 -->

<h1 align="center">
  🧠 Pokemon Trainer Platform - AI
</h1>

<p align="center">
  <em>
    A hierarchical multi-agent AI advisor for Pokémon trainers — five specialized agents
    collaborate on trade evaluation, market forecasting, legitimacy checks, battle
    viability, and Pokédex knowledge via RAG.
  </em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
  <img src="https://img.shields.io/badge/python-3.13%2B-blue" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/agents-pydantic--ai-blue" alt="Pydantic AI">
  <img src="https://img.shields.io/badge/vector--db-chromadb-blue" alt="ChromaDB">
  <!-- markdownlint-disable-next-line MD013 -->
  <a href="https://jazicorn.github.io/pokemon-trainer-platform-ai/"><img src="https://img.shields.io/badge/docs-mkdocs--material-blue" alt="Docs site"></a>
  <!-- markdownlint-disable-next-line MD013 -->
  <a href="https://github.com/jazicorn/pokemon-trainer-platform-ai/actions/workflows/ci-test.yml"><img src="https://github.com/jazicorn/pokemon-trainer-platform-ai/actions/workflows/ci-test.yml/badge.svg" alt="CI Test"></a>
  <!-- markdownlint-disable-next-line MD013 -->
  <a href="https://github.com/jazicorn/pokemon-trainer-platform-ai/actions/workflows/ci-quality.yml"><img src="https://github.com/jazicorn/pokemon-trainer-platform-ai/actions/workflows/ci-quality.yml/badge.svg" alt="CI Quality"></a>
</p>

---

## 🚀 The Tech Stack

* **Agent Framework:** [Pydantic AI](https://ai.pydantic.dev/) (Strict type-safety & structured LLM
  outputs)
* **LLM Support:** Anthropic Claude (default), Google Gemini, OpenAI GPT-4o, Ollama (local or cloud)
* **Vector Database:** ChromaDB (RAG for technical Pokémon stats)
* **Observability:** [Pydantic Logfire](https://logfire.pydantic.dev/) / OpenTelemetry / Arize Phoenix
  (Real-time agent tracing)
* **Data Layer:** SQLite (default) or PostgreSQL via `PLATFORM_DB_URL` (persistent user memory,
  market history & shared trade offers)

---

## 📋 Prerequisites

* **Python ≥ 3.13** — managed via `uv`
* **[uv](https://docs.astral.sh/uv/)** — Python package & project manager
* **Docker / Colima** — required for ChromaDB
* **[1Password CLI](https://developer.1password.com/docs/cli/)** — optional, recommended for API
  key management

## 🛠️ Installation & Setup

```bash
# 1. Install dependencies
uv sync

# 2. Start ChromaDB (interactive — manages Docker/Colima automatically)
make chromadb-start

# 3. Ingest technical Pokedex data into ChromaDB
make ingest

# 4. Launch the interactive CLI
make run                  # Anthropic Claude via 1Password (default)
make run-gemini           # Google Gemini via 1Password
make run-openai           # OpenAI GPT-4o via 1Password
make run-ollama           # Local Ollama llama (no API key needed)
make run-ollama-cloud         # Ollama Cloud via local daemon proxy (needs `ollama signin`)
make run-ollama-cloud-direct  # Ollama Cloud direct API — no local ollama install
uv run python app.py      # plain (requires API key already in env)
```

See [`docs/1PASSWORD.md`](docs/1PASSWORD.md) for API key setup and
[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for full installation detail.
Run `make help` to see all available commands.

> **Tip for manual testing:** `make reset-db` deletes `data/memory.db` so mock offers and
> conversation history are wiped clean on the next `make run`. Useful when re-testing the
> offers inbox or starting a fresh session.

### 🐳 Or: Docker Compose (no local Python/uv setup needed)

```bash
cp .env.example .env   # fill in at least one LLM API key

make docker-run                                       # CLI + ChromaDB
make docker-run PROFILES="--profile observability"    # + Phoenix tracing
make docker-run PROFILES="--profile platform-db"      # + local PostgreSQL
```

ChromaDB starts automatically as a dependency (with a health check gating the app's
start). See [`docker-compose.yml`](docker-compose.yml) for the full service list and
[`docs/REFERENCE/PLATFORM_DB.md`](docs/REFERENCE/PLATFORM_DB.md) for the `platform-db`
profile's schema.

---

## 🌐 Web API

The same multi-agent system is also available over HTTP — every route requires a per-tenant
API key, each mapped server-side to that tenant's own Postgres database (see
[`docs/REFERENCE/PLATFORM_DB.md`](docs/REFERENCE/PLATFORM_DB.md)'s schema contract).

```bash
# 1. Set TENANT_DB_ENCRYPTION_KEY (see docs/1PASSWORD.md's "Other Secrets" section)
export TENANT_DB_ENCRYPTION_KEY=$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# 2. Provision a tenant — prints a real API key once, store it now
uv run python scripts/provision_tenant.py "my-tenant" "postgresql://user:pass@host/db"

# 3. Start the API
make run-api
```

| Method | Path                    | Auth | Description                            |
| ------ | ----------------------- | ---- | -------------------------------------- |
| GET    | `/health`               | No   | Service health check                   |
| POST   | `/v1/chat`              | Yes  | Free-text natural language agent query |
| POST   | `/v1/trade/evaluate`    | Yes  | Structured trade evaluation            |
| GET    | `/v1/trade/suggestions` | Yes  | Proactive trade suggestions            |
| GET    | `/v1/offers`            | Yes  | Pending trade offer inbox              |
| POST   | `/v1/offers/send`       | Yes  | Send a trade offer                     |
| POST   | `/v1/pokedex/query`     | Yes  | Pokedex knowledge question             |
| POST   | `/v1/market/query`      | Yes  | Market demand & trend query            |

```bash
curl http://localhost:8080/health

curl -X POST http://localhost:8080/v1/trade/evaluate \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard"}'

curl -H "X-API-Key: $API_KEY" "http://localhost:8080/v1/trade/suggestions?user_id=user_001"
```

Swagger UI is available at `http://localhost:8080/docs` (set your key via its Authorize
button). See [`ROADMAP.md`](ROADMAP.md) for the phased build-out plan this API followed, and
[`ROADMAP_PLATFORM.md`](ROADMAP_PLATFORM.md) for what comes after it.

---

## 🏛️ System Architecture: Hierarchical Delegation

Unlike "flat" agent systems, this project uses a **Master-Worker pattern**. The **Trade Advisor**
acts as the orchestrator, detecting user intent and delegating specialized tasks to worker agents.
This isolation prevents "Tool Overload" and ensures higher reasoning accuracy.

| Agent                       | Core Responsibility | Intelligence Layer                                                                |
| --------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| **Trade Advisor**           | **Orchestrator**    | **Intent Routing:** Distinguishes between market research vs. trade evaluation.   |
| **Legitimacy Guard**        | **Compliance**      | **Scam Prevention:** Verifies origin marks, PokéBall legality, and rarity tiers.  |
| **Market Analyst**          | **Forecaster**      | **Momentum Analysis:** Compares 7-day vs 30-day demand ratios.                    |
| **Pokedex Expert**          | **Researcher**      | **RAG Specialist:** Grounding decisions in high-fidelity technical data.          |
| **Battle Strategy Advisor** | **Strategist**      | **Competitive Viability:** Evaluates team composition and Pokémon tier placement. |

---

## 🛡️ Scam Prevention & Legitimacy

The **Legitimacy Guard** provides a safety net for high-value trades. It cross-references metadata
that typical LLMs hallucinate:

* **Ball Legality**: Checks if a Pokémon can legally exist in a specific PokéBall.
* **Provenance**: Validates "Origin Marks" (Go, Galar, Paldea).
* **Rarity Tiering**: Categorizes assets from "Common" to "Shiny Mythical."

---

## 🛠️ Testing & Quality Assurance

We use **Deterministic Model Mocking** to test our agents without calling expensive APIs.

```bash
make test         # Unit/integration tests — mocked LLM, no API keys needed
make test-live    # Same tests against live LLM APIs (via 1Password)
make test-rag     # ChromaDB integration tests (ChromaDB must be running)
```

---

## 📦 CI/CD & Releases

Every push to `main` runs [`ci-test.yml`](.github/workflows/ci-test.yml),
[`ci-quality.yml`](.github/workflows/ci-quality.yml), and
[`image-build.yml`](.github/workflows/image-build.yml). If it merges cleanly,
[`release.yml`](.github/workflows/release.yml) then self-determines whether a release is
warranted straight from [Conventional Commits](https://www.conventionalcommits.org/) history
(`feat`/`fix`/`perf` bump; anything else is a no-op) via
[Commitizen](https://commitizen-tools.github.io/commitizen/), pushes a
`chore(release): bump version X → Y` commit and a matching `vX.Y.Z` tag, and
[`image-publish.yml`](.github/workflows/image-publish.yml) then builds and publishes that
version to GHCR:

```bash
docker pull ghcr.io/jazicorn/pokemon-trainer-platform-ai:latest
```

---

## 📈 Technical Analysis for a Gaming Economy

The breakthrough feature of this project is its ability to perform **Predictive Forecasting**.
Instead of just looking at total trade counts, the **Market Analyst** calculates a **Momentum
Score**—a primitive version of a *Moving Average Crossover*.

### The Momentum Formula

The AI tracks the **Demand Ratio** (Requested / Offered) over two distinct time horizons to project
future value:

`Momentum = ((Ratio_7d - Ratio_30d) / Ratio_30d) * 100`

### Sentiment Classification

* 🚀 **Bullish (Momentum > +15%):** Demand is accelerating; a high-growth asset.
* 📉 **Bearish (Momentum < -15%):** Demand is cooling; oversupply detected.
* ⚖️ **Stable:** Market value is holding steady.

---

## 🧪 Scientific Validation: Multi-Agent Evaluations

This project follows **Eval-Driven Development (EDD)**. We use Pydantic Evals to quantify the
performance gains of our hierarchical architecture.

### Benchmark Results

* **+15.8% RAG Accuracy Gain:** The RAG-enabled Pokedex Expert outperformed a plain LLM baseline
  on Pokemon knowledge retrieval, with the largest gain on multi-hop questions (+100% on Pikachu
  evolution ancestry). See [`docs/REFERENCE/EVAL_RESULTS.md`](docs/REFERENCE/EVAL_RESULTS.md) for full
  captured output.

### Running the Evals

```bash
make eval        # Trade advisor evaluation
make eval-rag    # RAG vs no-RAG comparison
```

---

## 🔍 Features in Action

### Predictive Market Reports

> **User:** "What is the forecast for Pikachu?"
> **Advisor:** "Pikachu is currently **Bullish**. While its 30-day demand is 1.2, the 7-day velocity
has spiked to 2.4 (+100% momentum). **Recommendation:** Hold your position; market value is rising."

### Goal-Aligned Trade Evaluation

* Cross-references trade proposals against your `seeking` list and `primary_goal`.
* Suggests "Market-Smart" pivots (e.g., "Instead of Machop, trade for Gastly—it has better momentum
  for your Psychic team goal.")

---

## ⚙️ Make Commands Reference

| Command | Description |
| --- | --- |
| `make run` | Launch CLI with Claude (default) via 1Password |
| `make run-gemini` | Launch CLI with Gemini Flash via 1Password |
| `make run-openai` | Launch CLI with GPT-4o via 1Password |
| `make run-ollama` | Launch CLI with local Ollama (no API key needed) |
| `make run-ollama-cloud` | Ollama Cloud via local daemon proxy |
| `make run-ollama-cloud-direct` | Ollama Cloud direct API — no local ollama install |
| `make run-api` | Launch the HTTP API (see [Web API](#web-api) above) |
| `make test` | Run all tests with mocked LLM |
| `make test-live` | Run tests against live APIs |
| `make test-rag` | Run ChromaDB integration tests |
| `make eval` | Run trade advisor evaluation |
| `make eval-rag` | Run RAG vs no-RAG comparison |
| `make lint` | Check formatting, lint rules, and types |
| `make lint-fix` | Auto-fix formatting and lint issues |
| `make hooks-install` | One-time setup: enable this repo's git hooks |
| `make commit` | Guided Conventional Commits prompt (Commitizen) |
| `make docker-build` | Build the app's Docker image |
| `make docker-run` | Run the CLI in Docker (+ ChromaDB) |
| `make docker-down` | Stop and remove all Docker Compose services |
| `make ingest` | Index Pokémon data into ChromaDB |
| `make generate-data` | Regenerate mock trade and collection data |
| `make chromadb-start` | Start ChromaDB Docker container |
| `make chromadb-stop` | Stop ChromaDB Docker container |
| `make chromadb-status` | Show ChromaDB container status |
| `make reset-db` | Delete local SQLite database |

---

### 💡 Portfolio Note

This project demonstrates the ability to build complex, coordinated AI systems that move beyond
simple chat. It showcases expertise in **Structured Tool Use**, **Agentic Delegation**, and the
application of **Quantitative Analysis**, RAG, and multi-agent coordination to a structured domain problem.
