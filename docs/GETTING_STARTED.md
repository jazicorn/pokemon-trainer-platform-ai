# Getting Started

Welcome to the Pokemon Trainer Platform - AI! This guide will help you
set up and run the project from scratch.

## Prerequisites

Before you begin, ensure you have the following installed:

| Tool   | Version | Purpose            |
| ------ | ------- | ------------------ |
| Python | 3.13+   | Runtime            |
| uv     | Latest  | Package manager    |
| Docker | Latest  | ChromaDB container |
| Git    | Latest  | Version control    |

### Installing Prerequisites

**Python** (via pyenv recommended):

```bash
# macOS
brew install pyenv

# Initialize pyenv for Zsh
echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc

# Install Python 3.13
pyenv install 3.13

# Use Python 3.13 for this project
pyenv local 3.13
```

`pyenv local 3.13` creates a `.python-version` file in the project directory,
so this project uses Python 3.13 without changing the Python version for other
projects.

**uv** (fast Python package manager):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Docker**:

- macOS/Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop)
- macOS via Homebrew: Docker-compatible runtimes such as [Colima](https://github.com/abiosoft/colima)
  are also supported (`brew install colima docker && colima start`)
- macOS via [MacPorts](https://www.macports.org/install.php#installing) (install MacPorts
  itself first, then): `sudo port install colima docker && colima start` — MacPorts' `docker`
  port is the CLI only, same as Homebrew's; Colima provides the actual engine either way
- Linux: `sudo apt install docker.io` or [Docker Engine](https://docs.docker.com/engine/install/)

**Ollama** (optional — only needed for `make run-ollama` / `make run-ollama-cloud`, the
model options that require no API key at all; `make run-ollama-cloud-direct` needs an
Ollama API key instead, but no local `ollama` install):

- macOS via Homebrew:

  ```bash
  brew install ollama
  brew services start ollama
  ```

- macOS via [MacPorts](https://www.macports.org/install.php#installing) (install MacPorts
  itself first, then):

  ```bash
  sudo port install ollama
  sudo port load ollama
  ```

Either way, `ollama` itself works the same from here. Verify the server is up:

```bash
curl http://localhost:11434
# Should return: Ollama is running
```

Then either pull a local model (see `MODELS["llama"]` in `src/config.py`) — heavier on
older/less powerful hardware, since inference runs on your machine:

```bash
ollama pull llama3.2
```

**Or — Ollama Cloud:** inference runs on Ollama's servers, not your machine. There are two
ways to reach it — same `POKEMON_MODEL=llama-cloud`, different `OLLAMA_URL`, auto-detected
by `src/config.py` (no local GPU needed either way):

- `make run-ollama-cloud` — via the local `ollama` install above, proxied through it:

  ```bash
  ollama signin
  ollama pull gpt-oss:120b-cloud
  ```

- `make run-ollama-cloud-direct` — talks to `https://ollama.com` directly, **no local
  `ollama` install needed at all**. Just an API key:

  ```bash
  export OLLAMA_API_KEY=...   # from https://ollama.com/settings/keys
  ```

More cloud models: <https://ollama.com/search?c=cloud>, or see
[docs/REFERENCE/OLLAMA_CLOUD_MODELS.md](REFERENCE/OLLAMA_CLOUD_MODELS.md) for a
point-in-time snapshot of what's available.

After installing the prerequisites, verify that they are available:

```bash
python --version
which python
uv --version
docker --version
git --version
```

## Project Setup

### 1. Clone the Repository

```bash
git clone <repo-url>
cd pokemon-trainer-platform-ai
```

### 2. Install Dependencies

```bash
uv sync
```

This creates or updates the project's virtual environment and installs the dependencies
defined by the project.

This installs all required packages including:

- pydantic-ai (AI agents)
- httpx (HTTP client for ChromaDB)
- opentelemetry (observability)
- And more...

### 3. Set Up Environment Variables

**Option A — `.env` file:** copy [`.env.example`](../.env.example) to `.env` and fill in your
values. `config.py` loads it automatically via `python-dotenv` — no sourcing needed, it
just works on the next `uv run python app.py` / `make run*`.

```bash
cp .env.example .env
```

```bash
# Required: At least one LLM API key
ANTHROPIC_API_KEY=sk-ant-...
# Or
OPENAI_API_KEY=sk-...
# Or
GOOGLE_API_KEY=...

# Optional: For local or cloud Ollama models
OLLAMA_URL=http://localhost:11434
# OLLAMA_API_KEY=...  # only for direct Ollama Cloud API access (OLLAMA_URL=https://ollama.com)
```

`.env.local` (also auto-loaded, also gitignored) is available too — it takes precedence
over `.env`, which takes precedence over the defaults in `src/config.py`. Handy for
per-machine overrides you'd rather keep separate from your main `.env`. A real
environment variable (a shell export, Docker's `environment:`, `op run`, CI secrets)
always wins over both files.

**Option B — 1Password `.zshrc` integration:** Add `op read` exports to your
`~/.zshrc`. Keys are resolved once when you open a terminal, so 1Password must
be unlocked at that point.

```bash
export ANTHROPIC_API_KEY=$(op read "op://Private/ANTHROPIC_API_KEY/credential")
export GOOGLE_API_KEY=$(op read "op://Private/GOOGLE_API_KEY/credential")
# export OLLAMA_API_KEY=$(op read "op://Private/OLLAMA_API_KEY/credential")
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

### 4. Start Services

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

**Alternative — Docker Compose:** `make docker-run` builds the app image and starts it
alongside ChromaDB in one step (add `PROFILES="--profile observability"` for Phoenix, or
`PROFILES="--profile platform-db"` for local PostgreSQL). This replaces step 4 and the
`make run` step below with a single command — see the "Docker Compose" section in the
[README](../README.md) or [`docker-compose.yml`](../docker-compose.yml) directly.

### 5. Initialize Data

Generate mock data and index Pokemon:

```bash
# Generate mock trade data and user collection
uv run python -m src.data.generator

# Index Pokemon into ChromaDB (fetches from PokeAPI)
uv run python -m src.rag.ingest
```

### 6. Run Tests

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
pokemon-trainer-platform-ai/
├── app.py                 # CLI entry point
├── src/
│   ├── agents/           # AI agents (Pokedex, Market, Advisor, Legitimacy Guard)
│   │   ├── pokedex_expert.py
│   │   ├── trade_market_analyst.py
│   │   ├── trade_advisor_core.py      # Dependencies, system prompt, agent
│   │   ├── trade_advisor_tools.py     # @trade_advisor.tool functions
│   │   ├── trade_advisor_api.py       # Public async API
│   │   ├── trade_advisor.py           # Re-export facade
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
├── tests/                # Mirrors src/ layout (agents/, cli/, core/, ...)
└── data/                 # Generated data files (gitignored)
```

## Configuration

Every config field can be set with an environment variable — no code edits
needed. Values are read once at startup from `src/config.py`.

### Environment Variable Reference

| Env var | Default | Purpose |
| --- | --- | --- |
| `POKEMON_MODEL` | `claude-sonnet` | Active LLM — see model keys below |
| `CHROMADB_URL` | `http://localhost:8000` | ChromaDB server base URL |
| `PHOENIX_URL` | `http://127.0.0.1:6006` | Phoenix tracing UI URL |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server base URL — `https://ollama.com` for direct Ollama Cloud API access |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model when using Ollama |
| `PROJECT_NAME` | `pokemon-trade-advisor` | Phoenix project / tracing namespace |
| `USE_OLLAMA_EMBEDDINGS` | `false` | `true` to embed via Ollama instead |
| `PLATFORM_DB_URL` | (not set) | PostgreSQL DSN — enables live trade offers from the web API |

API keys:

| Env var | Required for |
| --- | --- |
| `ANTHROPIC_API_KEY` | `claude-sonnet`, `claude-haiku` |
| `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
| `GOOGLE_API_KEY` | `gemini-flash`, `gemini-pro` |
| `OLLAMA_API_KEY` | `llama-cloud`, only via the direct-API transport (`OLLAMA_URL=https://ollama.com`) |

`OLLAMA_API_KEY` is not needed for local `llama`, and not needed for `llama-cloud` via
the local-proxy transport either — `ollama signin` handles auth there instead. Get a key
from <https://ollama.com/settings/keys>.

### Model Selection

Available model keys: `claude-sonnet` (default), `claude-haiku`, `gemini-flash`,
`gemini-pro`, `gpt-4o`, `gpt-4o-mini`, `llama`, `llama-cloud`.

```bash
# Switch model for a single run
POKEMON_MODEL=gpt-4o uv run python app.py

# Point at a remote ChromaDB
CHROMADB_URL=http://myserver:8000 uv run python app.py

# Use Ollama for both inference and embeddings
POKEMON_MODEL=llama USE_OLLAMA_EMBEDDINGS=true uv run python app.py
```

### Platform Database (Optional)

When `PLATFORM_DB_URL` is set the `trade_offers` table is shared read-write
with the Pokemon Trainer Platform web API — the web API inserts offers and this
project evaluates and responds to them. Without it, a local SQLite table with
seeded mock offers is used instead (zero breaking change).

```bash
# Install the optional psycopg driver
uv sync --group platform-db

# Connect to your PostgreSQL instance
PLATFORM_DB_URL=postgresql://user:pass@localhost:5432/pokemon_platform \
  uv run python app.py
```

See `docs/REFERENCE/PLATFORM_DB.md` for the full schema, role setup, and
fallback behaviour table.

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
make phoenix-start
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

2. **Run Evaluations**: Test the system quality:

   ```bash
   uv run python -m src.evals.eval_trade_advisor
   uv run python -m src.evals.eval_rag_comparison
   ```

3. **Customize**: Add your own Pokemon preferences and see how
   recommendations change

4. **Extend**: Try adding new features like:
   - New agent capabilities
   - Additional data sources
   - Custom evaluation metrics

## Getting Help

- Check [`REFERENCE/TESTING.md`](REFERENCE/TESTING.md) for test-specific guidance
- Review phase documentation in `docs/WALKTHROUGH/`
- Look at test files for usage examples

Happy trading! 🎮
