# Setup and First Run

This guide gets you from a fresh machine to running the application and
interacting with it. It explains what each step is doing and why, not just
what commands to run.

For the full technical reference with all options and advanced configuration, see
[`docs/GETTING_STARTED.md`](../GETTING_STARTED.md).

---

## What You Need Before You Start

| Tool | Why you need it |
| --- | --- |
| Python 3.11+ | The application is written in Python |
| `uv` | Fast Python package manager — used instead of `pip` |
| Docker (or Colima on macOS) | ChromaDB runs as a Docker container |
| One LLM API key | The agents need a real LLM to reason — this is a paid external service |

**Which API key do you need?**

The default model is Claude (Anthropic). You need one of these:

| Provider | Env variable | Default model |
| --- | --- | --- |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | `claude-sonnet` |
| OpenAI (GPT-4) | `OPENAI_API_KEY` | `gpt-4o` |
| Google (Gemini) | `GOOGLE_API_KEY` | `gemini-flash` |
| None (local Ollama) | — | `llama3.2` |

If you are using Ollama for a fully local, no-cost setup, see
[`docs/GETTING_STARTED.md`](../GETTING_STARTED.md) for the Ollama-specific instructions.

For installing any of the prerequisites, see [`docs/GETTING_STARTED.md`](../GETTING_STARTED.md)
— it has OS-specific install instructions for each tool.

---

## Step 1: Install Dependencies

From the project root:

```bash
uv sync
```

`uv sync` installs all Python packages listed in `pyproject.toml`.

You should see `uv` download and install packages. This takes a minute on first run.

---

## Step 2: Set Up Your API Key

The LLM is a paid external service. Your API key tells the service who is
making the request. Never commit API keys to git.

**The simple approach — create a `.env` file:**

Create a `.env` file in the project root:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Then run the app with:

```bash
uv run python app.py
```

**The 1Password approach (if your team uses 1Password):**

The project also supports 1Password CLI integration, which keeps secrets
out of files entirely. See [`docs/1PASSWORD.md`](../1PASSWORD.md) for the
setup steps. The `make run` shortcut in `Makefile` uses this approach.

---

## Step 3: Start ChromaDB

ChromaDB is the vector database that stores the Pokemon knowledge base.
It runs as a Docker container.

```bash
make chromadb-start
```

What this does: it runs the `chromadb_setup/chromadb-docker.sh` script,
which starts (or creates) a Docker container running the ChromaDB server
on port 8000.

**On macOS:** Docker on Apple Silicon Macs uses Colima as a lightweight
Docker runtime instead of Docker Desktop. If you have not installed
Colima, the script will prompt you. If Colima crashes on startup (a known
issue with the VZ driver on some Macs), the startup script auto-recovers
by switching to the QEMU driver — see
[`docs/INFRASTRUCTURE_FIXES.md`](../INFRASTRUCTURE_FIXES.md) for details.

**Verify it worked:**

```bash
make chromadb-status
```

You should see the container running and a health check response from `localhost:8000`.

---

## Step 4: Ingest Pokemon Data

Before the Pokedex Expert can answer questions, it needs data in ChromaDB. This one-time
setup step fetches 40 Pokemon from the public PokeAPI and stores them as searchable
documents.

```bash
make ingest
```

What this does: runs `src/rag/ingest.py`, which fetches Pokemon data from
`https://pokeapi.co`, processes it, and calls
`PokemonVectorStore.add_pokemon()` for each one. The data is stored
persistently in the `chroma_data/` volume, so you only need to run this
once (or again if you want to add more Pokemon).

You should see output like:

```text
Ingesting Pokemon data into ChromaDB...
✓ Pikachu
✓ Charizard
✓ Blastoise
...
Ingestion complete. 40 Pokemon indexed.
```

---

## Step 5: Generate Mock Data (First Time Only)

The Market Analyst needs trade history data, and you need a user collection to
personalize the recommendations.

```bash
make generate-data
```

This creates two files in `data/`:

- `platform_trades.json` — thousands of mock trade records representing
  platform history
- `user_collection.json` — a sample trainer's Pokemon collection and preferences

These files are already committed to the repo, so you may not need to run this unless
they are missing or you want to reset them.

---

## Step 6: Run the App

```bash
make run
```

What this expands to:

```bash
op run --env-file .env.op -- uv run python app.py
```

If you are using the simple `.env` approach instead:

```bash
uv run python app.py
```

**What you should see:**

```text
Pokemon Trainer's Second Brain
Checking environment...
Starting ChromaDB...  ✓ Already running
Initializing database...  ✓ Done

Enable telemetry? Sends trace data to Phoenix for observability. (y/N):
```

Type `N` (or just press Enter) to skip telemetry for now. Phoenix and telemetry are
optional — the app works fully without them.

```text
============================================================
       Pokemon Trainer's Second Brain
============================================================

TRADE
  trade    {your-pokemon} for {their-pokemon}  Evaluate a trade
  ...

trainer>
```

You are in. The `trainer>` prompt means the app is ready.

---

## Step 7: Try Three Things

Run these three commands to exercise the major components. Each one exercises a different
part of the system.

### 1. Look up Pokemon data (Pokedex Expert + ChromaDB)

```text
trainer> pokedex What are Charizard's stats?
```

This calls the Pokedex Expert, which searches ChromaDB for Charizard's
document and returns its actual stats from the PokeAPI data. If this
works, ChromaDB is healthy and the ingestion succeeded.

### 2. Check market trends (Market Analyst + trade data)

```text
trainer> market What Pokemon are trending right now?
```

This calls the Trade Market Analyst, which reads the platform trade history and returns
the top trending Pokemon with their momentum data. If this works, the mock data was
generated correctly.

### 3. Evaluate a trade (full multi-agent stack)

```text
trainer> trade pikachu for charizard
```

This exercises everything: Trade Advisor calls the Pokedex Expert (which queries
ChromaDB), then the Market Analyst (which reads trade history), then loads your user
context from the JSON file. The Trade Advisor synthesizes all of it into a
recommendation. If this works, the whole system is functioning.

---

## If Something Goes Wrong

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `ChromaDB is unreachable` | Docker container not running | `make chromadb-start` |
| `ANTHROPIC_API_KEY is empty` or `contains a 1Password URI` | Key not resolved | Check your `.env` file, or run via `op run` if using 1Password |
| `ModuleNotFoundError` | Python path not set correctly | Make sure you are running from the project root with `uv run python app.py` |
| `No Pokemon found matching that query` | ChromaDB empty | Run `make ingest` |
| `KeyError` or `FileNotFoundError` on trade data | Mock data missing | Run `make generate-data` |

For extended troubleshooting, see the Troubleshooting section of
[`docs/GETTING_STARTED.md`](../GETTING_STARTED.md).

---

## Optional: Enable Telemetry

When you start the app, it asks whether to enable telemetry. If you say
yes, it starts a Phoenix tracing server that shows you a visual timeline
of every tool call each agent made — useful when debugging agent behavior.

To use it:

1. Answer `y` at the telemetry prompt (or make sure `docker` is available
   so Phoenix can start)
2. Open `http://127.0.0.1:6006` in your browser after startup

This is completely optional. The app works the same with or without it.

---

**Next: [05-codebase-tour.md](05-codebase-tour.md)**
