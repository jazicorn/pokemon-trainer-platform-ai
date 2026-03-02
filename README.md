# Pokemon Trainer Platform - AI

**🧠 Pokémon Trainer's Second Brain** — Multi-Agent AI Advisor

A state-of-the-art **Hierarchical Multi-Agent System** built for Pokémon trainers who want more
than guesswork. Five specialized agents collaborate: forecasting trade market demand, verifying
trade legitimacy, surfacing Pokédex knowledge via RAG, evaluating battle team composition, and
routing it all through a single conversational interface.

## 🚀 The Tech Stack

* **Agent Framework:** [Pydantic AI](https://ai.pydantic.dev/) (Strict type-safety & structured LLM
  outputs)
* **LLM Support:** Anthropic Claude (default), Google Gemini, OpenAI GPT-4o, Ollama (local)
* **Vector Database:** ChromaDB (RAG for technical Pokémon stats)
* **Observability:** [Pydantic Logfire](https://logfire.pydantic.dev/) / OpenTelemetry / Arize Phoenix
  (Real-time agent tracing)
* **Data Layer:** SQLite (Persistent user memory & market history)

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
uv run python app.py      # plain (requires API key already in env)
```

See [`docs/1PASSWORD.md`](docs/1PASSWORD.md) for API key setup and
[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for full installation detail.
Run `make help` to see all available commands.

> **Tip for manual testing:** `make reset-db` deletes `data/memory.db` so mock offers and
> conversation history are wiped clean on the next `make run`. Useful when re-testing the
> offers inbox or starting a fresh session.

---

## 🏛️ System Architecture: Hierarchical Delegation

Unlike "flat" agent systems, this project uses a **Master-Worker pattern**. The **Trade Advisor**
acts as the orchestrator, detecting user intent and delegating specialized tasks to worker agents.
This isolation prevents "Tool Overload" and ensures higher reasoning accuracy.

| Agent                | Core Responsibility | Intelligence Layer                                                               |
| -------------------- | ------------------- | -------------------------------------------------------------------------------- |
| **Trade Advisor**           | **Orchestrator** | **Intent Routing:** Distinguishes between market research vs. trade evaluation.        |
| **Legitimacy Guard**        | **Compliance**   | **Scam Prevention:** Verifies origin marks, PokéBall legality, and rarity tiers.       |
| **Market Analyst**          | **Forecaster**   | **Momentum Analysis:** Compares 7-day vs 30-day demand ratios.                         |
| **Pokedex Expert**          | **Researcher**   | **RAG Specialist:** Grounding decisions in high-fidelity technical data.                |
| **Battle Strategy Advisor** | **Strategist**   | **Competitive Viability:** Evaluates team composition and Pokémon tier placement.       |

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

| Command                | Description                                      |
| ---------------------- | ------------------------------------------------ |
| `make run`             | Launch CLI with Claude (default) via 1Password   |
| `make run-gemini`      | Launch CLI with Gemini Flash via 1Password       |
| `make run-openai`      | Launch CLI with GPT-4o via 1Password             |
| `make run-ollama`      | Launch CLI with local Ollama (no API key needed) |
| `make test`            | Run all tests with mocked LLM                    |
| `make test-live`       | Run tests against live APIs                      |
| `make test-rag`        | Run ChromaDB integration tests                   |
| `make eval`            | Run trade advisor evaluation                     |
| `make eval-rag`        | Run RAG vs no-RAG comparison                     |
| `make ingest`          | Index Pokémon data into ChromaDB                 |
| `make generate-data`   | Regenerate mock trade and collection data        |
| `make chromadb-start`  | Start ChromaDB Docker container                  |
| `make chromadb-stop`   | Stop ChromaDB Docker container                   |
| `make chromadb-status` | Show ChromaDB container status                   |
| `make reset-db`        | Delete local SQLite database                     |

---

### 💡 Portfolio Note

This project demonstrates the ability to build complex, coordinated AI systems that move beyond
simple chat. It showcases expertise in **Structured Tool Use**, **Agentic Delegation**, and the
application of **Quantitative Analysis**, RAG, and multi-agent coordination to a structured domain problem.
