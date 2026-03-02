# 🧠 Pokémon Trainer's Second Brain: Multi-Agent Financial AI

A state-of-the-art **Hierarchical Multi-Agent System** that transforms Pokémon trading into a
data-driven economy. By applying Wall Street-grade **Technical Analysis** to in-game trade data,
this "Second Brain" helps trainers outmaneuver the market.

## 🚀 The Tech Stack

* **Agent Framework:** [Pydantic AI](https://ai.pydantic.dev/) (Strict type-safety & structured LLM
  outputs)
* **Vector Database:** ChromaDB (RAG for technical Pokémon stats)
* **Observability:** [Pydantic Logfire](https://logfire.pydantic.dev/) / OpenTelemetry (Real-time
  agent tracing)
* **Data Layer:** SQLite (Persistent user memory & market history)

---

## 🛠️ Installation & Setup

```bash
# 1. Install dependencies
uv sync --extra capstone

# 2. Start ChromaDB (interactive — manages Docker/Colima automatically)
./chromadb_setup/chromadb-docker.sh start

# 3. Ingest technical Pokedex data into ChromaDB
uv run python -m src.rag.ingest

# 4. Launch the interactive CLI
op run --env-file .env.op -- uv run python app.py   # 1Password (recommended)
uv run python app.py                                 # plain (requires API key in env)
```

See [`docs/1PASSWORD.md`](docs/1PASSWORD.md) for API key setup and
[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for full installation detail.
Run `make help` from the `capstone/` directory to see all available commands.

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
| **Trade Advisor**    | **Orchestrator**    | **Intent Routing:** Distinguishes between market research vs. trade evaluation.  |
| **Legitimacy Guard** | **Compliance**      | **Scam Prevention:** Verifies origin marks, PokéBall legality, and rarity tiers. |
| **Market Analyst**   | **Forecaster**      | **Momentum Analysis:** Compares 7-day vs 30-day demand ratios.                   |
| **Pokedex Expert**   | **Researcher**      | **RAG Specialist:** Grounding decisions in high-fidelity technical data.         |

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
  evolution ancestry). See [`docs/eval_results/README.md`](docs/eval_results/README.md) for full
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

### 💡 Portfolio Note

This project demonstrates the ability to build complex, coordinated AI systems that move beyond
simple chat. It showcases expertise in **Structured Tool Use**, **Agentic Delegation**, and the
application of **Quantitative Finance** principles to unstructured data.
