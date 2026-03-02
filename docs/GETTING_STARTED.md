# Getting Started

Welcome to the Pokemon Trade Advisor capstone project! This guide will help you
set up and run the project from scratch.

## Prerequisites

Before you begin, ensure you have the following installed:

| Tool   | Version | Purpose            |
| ------ | ------- | ------------------ |
| Python | 3.11+   | Runtime            |
| uv     | Latest  | Package manager    |
| Docker | Latest  | ChromaDB container |
| Git    | Latest  | Version control    |

### Installing Prerequisites

**Python** (via pyenv recommended):

```bash
# macOS
brew install pyenv
pyenv install 3.12
pyenv global 3.12

# Verify
python --version
```

**uv** (fast Python package manager):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify
uv --version
```

**Docker**:

- macOS/Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Linux: `sudo apt install docker.io` or [Docker Engine](https://docs.docker.com/engine/install/)

## Project Setup

### 1. Clone the Repository

```bash
git clone <your-katas-repo-url>
cd katas-exercises
```

### 2. Navigate to Capstone

```bash
cd capstone
```

### 3. Install Dependencies

```bash
uv sync --extra capstone
```

This installs all required packages including:

- pydantic-ai (AI agents)
- httpx (HTTP client for ChromaDB)
- opentelemetry (observability)
- And more...

### 4. Set Up Environment Variables

**Option A — `.env` file:**

```bash
# Required: At least one LLM API key
ANTHROPIC_API_KEY=sk-ant-...
# Or
OPENAI_API_KEY=sk-...
# Or
GEMINI_API_KEY=...

# Optional: For local models
OLLAMA_HOST=http://localhost:11434
```

**Option B — 1Password `.zshrc` integration:** Add `op read` exports to your
`~/.zshrc`. Keys are resolved once when you open a terminal, so 1Password must
be unlocked at that point.

```bash
export ANTHROPIC_API_KEY=$(op read "op://Private/ANTHROPIC_API_KEY/credential")
export GOOGLE_API_KEY=$(op read "op://Private/GEMINI_API_KEY/credential")
```

Authenticate before opening a new terminal (or reload):

```bash
eval $(op signin) && source ~/.zshrc
```

If the app starts with an empty-key error, see
[API Key Empty at App Startup](TROUBLESHOOTING/runtime-errors.md#api-key-empty-at-app-startup).

**Option C — `.env.op` file (recommended for 1Password users):** The project
ships a `.env.op` file containing `op://` URI references. Secrets are resolved
at command-execution time — 1Password does not need to be unlocked when you
open your terminal.

```bash
# Run the app — op resolves secrets from 1Password at this moment
op run --env-file .env.op -- uv run python app.py

# Run tests with live keys
op run --env-file .env.op -- uv run pytest tests/ -v --tb=short
```

The `.env.op` file is safe to commit — it contains `op://` URIs, not actual
keys. Edit it to add or change which 1Password items are used.

### 5. Start Services

Start ChromaDB (required for RAG):

```bash
# Using the startup script
uv run python -m src.startup

# Or manually with Docker
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -e ANONYMIZED_TELEMETRY=false \
  chromadb/chroma:latest
```

Verify ChromaDB is running:

```bash
curl http://localhost:8000/api/v2/heartbeat
# Should return: {"nanosecond heartbeat": ...}
```

### 6. Initialize Data

Generate mock data and index Pokemon:

```bash
# Generate mock trade data and user collection
uv run python -c "from data.generator import generate_platform_trades, generate_user_collection; generate_platform_trades(); generate_user_collection()"

# Index Pokemon into ChromaDB (fetches from PokeAPI)
uv run python -m src.rag.ingest
```

### 7. Run Tests

Verify everything is working:

```bash
uv run pytest tests/ -v
```

## Running the Application

### CLI Interface

Start the interactive CLI:

```bash
uv run python app.py
```

You'll see:

```text
============================================================
           Pokemon Trainer's Second Brain
============================================================
Your AI-powered trade advisor. Use specific commands or
just ask a question in plain English!

COMMANDS:
  trade        - trade {your-pokemon} for {their-pokemon}
  suggest      - Get personalized trade ideas
  offers       - View incoming trade offers (with AI evaluation)
  offers sent  - View offers you have sent
  offer        - offer {pokemon} to {user} for {their-pokemon}
  accept       - accept {offer-id}
  decline      - decline {offer-id}
  pokedex      - Lookup stats, types, and abilities
  market       - Check platform demand and trends
  prefs        - View/update your trading goals
  history      - View recent advisor insights
  about        - Learn how this project works
  clear        - Clear the terminal screen
  help         - Show this screen
  quit         - Exit application
============================================================

>
```

### Example Commands

```bash
# Evaluate a trade
> trade pikachu for charizard

# Get suggestions based on your collection
> suggest

# View your incoming trade offers with AI evaluation
> offers

# View offers you've sent
> offers sent

# Send a trade offer to another user
> offer gengar to user_002 for alakazam

# Accept or decline an offer by ID
> accept 3
> decline 5

# Ask about Pokemon
> pokedex What are Dragonite's weaknesses?

# Check market trends
> market What Pokemon are trending right now?

# View your preferences
> prefs
```

## Project Structure

```text
capstone/
├── app.py                 # CLI entry point
├── src/
│   ├── agents/           # AI agents (Pokedex, Market, Advisor, Legitimacy Guard)
│   │   ├── pokedex_expert.py
│   │   ├── trade_market_analyst.py
│   │   ├── trade_advisor.py
│   │   ├── trade_analytics.py
│   │   └── legitimacy_guard.py
│   ├── cli/              # Command parsing and Rich UI app
│   ├── config.py         # Model configuration (multi-provider)
│   ├── data/             # Mock data generation and loading
│   ├── evals/            # Evaluation framework
│   ├── guardrails/       # PII detection/filtering + middleware
│   ├── mcp_server/       # MCP server (optional)
│   ├── memory/           # SQLite + conversation memory
│   ├── observability/    # OpenTelemetry setup
│   ├── rag/              # Vector store and ingestion
│   └── startup.py        # Service startup script
├── tests/                # Test suite
├── data/                 # Generated data files
└── observability/        # Docker compose for Phoenix
```

## Configuration

Every config field can be set with an environment variable — no code edits
needed. Values are read once at startup from `src/config.py`.

### Environment Variable Reference

| Env var                  | Default                    | Purpose                              |
| ------------------------ | -------------------------- | ------------------------------------ |
| `POKEMON_MODEL`          | `claude-sonnet`            | Active LLM — see model keys below    |
| `CHROMADB_URL`           | `http://localhost:8000`    | ChromaDB server base URL             |
| `PHOENIX_URL`            | `http://127.0.0.1:6006`    | Phoenix tracing UI URL               |
| `OLLAMA_URL`             | `http://localhost:11434`   | Ollama server base URL               |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text`         | Embedding model when using Ollama    |
| `PROJECT_NAME`           | `pokemon-trade-advisor`    | Phoenix project / tracing namespace  |
| `USE_OLLAMA_EMBEDDINGS`  | `false`                    | `true` to embed via Ollama instead   |

API keys (required for non-Ollama providers):

| Env var             | Provider                          |
| ------------------- | --------------------------------- |
| `ANTHROPIC_API_KEY` | `claude-sonnet`, `claude-haiku`   |
| `OPENAI_API_KEY`    | `gpt-4o`, `gpt-4o-mini`           |
| `GOOGLE_API_KEY`    | `gemini-flash`, `gemini-pro`      |

### Model Selection

Available model keys: `claude-sonnet` (default), `claude-haiku`, `gemini-flash`,
`gemini-pro`, `gpt-4o`, `gpt-4o-mini`, `llama`.

```bash
# Switch model for a single run
POKEMON_MODEL=gpt-4o uv run python app.py

# Point at a remote ChromaDB
CHROMADB_URL=http://myserver:8000 uv run python app.py

# Use Ollama for both inference and embeddings
POKEMON_MODEL=llama USE_OLLAMA_EMBEDDINGS=true uv run python app.py
```

### User Preferences

Set your trading preferences:

```python
from memory import UserPreferencesManager

prefs = UserPreferencesManager("user_001")
prefs.save_preferences(
    favorite_types=["fire", "dragon"],
    goal="Complete my Dragon collection",
    trading_style="collection_focused",
    seeking=["dragonite", "salamence"],
    never_trade=["charizard"],  # My favorite!
)
```

## Observability (Optional)

### Start Phoenix for Tracing

```bash
cd observability
docker compose up -d
```

View traces at: <http://localhost:6006>

### Enable Tracing in Code

```python
from observability.observability import setup as setup_observability

setup_observability()  # Call at startup
```

## Troubleshooting

See [TROUBLESHOOTING/runtime-errors.md](TROUBLESHOOTING/runtime-errors.md).

## Next Steps

1. **Explore the Agents**: Look at `src/agents/` to understand how each
   agent works

1. **Run Evaluations**: Test the system quality:

   ```bash
   uv run python -m src.evals.eval_trade_advisor
   uv run python -m src.evals.eval_rag_comparison
   ```

1. **Customize**: Add your own Pokemon preferences and see how
   recommendations change

1. **Extend**: Try adding new features like:
   - New agent capabilities
   - Additional data sources
   - Custom evaluation metrics

## Getting Help

- Check [`REFERENCE/TESTING.md`](REFERENCE/TESTING.md) for test-specific guidance
- Review phase documentation in `docs/CAPSTONE_GUIDE/`
- Look at test files for usage examples

Happy trading! 🎮
