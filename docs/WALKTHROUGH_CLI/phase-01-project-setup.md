# Phase 1: Project Setup & Infrastructure

## Overview

Phase 1 is the foundation layer. It wires together the three infrastructure services the rest of the
system depends on — **SQLite** (persistent memory), **ChromaDB** (vector store), and **Phoenix**
(observability tracing) — and validates that the environment is correctly configured before any
agent runs.

The startup sequence runs automatically when `app.py` launches: environment variables are validated,
the SQLite schema is initialized, Phoenix is started via Docker, and ChromaDB is confirmed running.
If any step fails, the error message tells you exactly what to fix.

## Where It Fits

```text
[No dependencies]
        ↓
Phase 1: Infrastructure (config, startup, observability)
        ↓
All other phases depend on this
```

## Key Files

- `app.py` — Entry point. Prints the startup banner, calls `startup()`, then launches the CLI.
- `src/startup.py` — Orchestrates infrastructure: validates env vars, initializes the database,
  starts Phoenix, confirms ChromaDB. Also exports `is_chromadb_running()`.
- `src/config.py` — Central config object. Reads model selection, service URLs, and feature flags
  from environment variables. All config values have sensible defaults.
- `src/observability/observability.py` — Sets up OpenTelemetry + Logfire tracing via Phoenix. Called
  during startup if Phoenix is available.

## Key Concepts

**Environment-first config**: Every config value in `config.py` can be overridden with an
environment variable — no code edits needed to switch models or point at a different ChromaDB
instance. Run `POKEMON_MODEL=gpt-4o uv run python app.py` to switch models for a single run.

**Startup validation**: `validate_environment()` in `startup.py` detects which LLM provider is
active (from `POKEMON_MODEL`) and checks that the corresponding API key is present and non-empty. It
also detects the 1Password CLI (`op`) and tailors its error message — if your key is a `op://` URI
that was never resolved, it tells you exactly how to fix it.

**Four-step init sequence**: `startup()` runs steps in a fixed order — (0) validate env, (1) init
SQLite schema, (2) setup observability, (3) start ChromaDB. Each step is independently toggleable
via boolean kwargs, which is how tests disable services they don't need.

**Graceful degradation**: If Phoenix or ChromaDB can't start, the app warns and continues rather
than crashing. ChromaDB is only strictly required for RAG queries. Phoenix is only needed for trace
visibility.

**Flush vs. buffer**: Startup messages use `print(..., flush=True)` in `app.py` and
`_console.print()` (Rich) in `startup.py` so each line appears immediately, even when stdout is
piped through `op run`.

**Provider map**: `PROVIDER_ENV_VARS` in `startup.py` maps each provider string to its required env
var. `ollama` maps to `None` — local Ollama needs no API key, so validation is skipped entirely.

## Exploring the Code

Start at `app.py` — it's only ~35 lines and shows the full startup + CLI launch sequence. The
`sys.path.insert` at the top is the reason all `src/` imports work without a package install.

In `startup.py`, read `validate_environment()` to understand how the 1Password-aware error messages
work. There are four distinct branches: valid key, `op://` URI (never resolved), empty string with
`op` installed, and missing key entirely. Then read `startup()` to see the four-step init sequence
and how each step is guarded by its boolean kwarg.

In `config.py`, find the `MODELS` dict to see every supported provider and model key. The
`ModelConfig.model_id` property shows how Ollama gets a different prefix (`ollama:llama3.2`) vs.
cloud providers (`anthropic:claude-sonnet-4-6`). The global `config` instance at the bottom is what
every other module imports.

In `observability/observability.py`, read `setup()` to see how Phoenix Docker container management
is separated from OTEL initialization. The container is named `phoenix-pokemon-trainer` and is reused
across runs.

## Running the Code

```bash
# Standard launch (1Password resolves secrets)
op run --env-file .env.op -- uv run python app.py

# Plain launch (API key already in environment)
uv run python app.py

# Switch model for one run
POKEMON_MODEL=gpt-4o uv run python app.py

# Point at a remote ChromaDB
CHROMADB_URL=http://myserver:8000 uv run python app.py

# Run with local Ollama (no API key needed)
POKEMON_MODEL=llama uv run python app.py
```

Expected startup output (each line appears as the action completes):

```text
Pokemon Trainer's Second Brain
========================================
Starting infrastructure...
Initializing local database...
Starting Phoenix in Docker...
Starting ChromaDB...
✓ ChromaDB running at http://localhost:8000
Starting CLI...
```

## Running the Tests

```bash
# Config: model keys, URL defaults, env var overrides
uv run pytest tests/core/test_config.py -v

# Startup: env var validation and error messages
uv run pytest tests/core/test_startup_validation.py -v

# Run both together
uv run pytest tests/core/test_config.py tests/core/test_startup_validation.py -v
```

`test_config.py` checks that `ModelConfig.model_id` is formatted correctly per provider, that all
seven model keys are present in `MODELS`, that `Config` defaults match expected values, and that
every env var overrides the corresponding field. Tests use `importlib.reload(cfg_module)` after
`monkeypatch.setenv()` because `config` is a module-level singleton — you have to reload the module
for env var changes to take effect. Each test class has a `teardown_method` that reloads the module
again to restore defaults.

`test_startup_validation.py` checks that `validate_environment()` passes for valid keys, raises
`EnvironmentError` for missing or empty keys, skips validation entirely for Ollama, and produces
error messages that name both the variable and the provider.

## Common Gotchas

**`op://` URIs in env vars**: If you see `EnvironmentError: Environment variable ANTHROPIC_API_KEY
contains a 1Password URI`, you ran the app without `op run`. Fix: `op run --env-file .env.op -- uv
run python app.py`.

**Empty key after shell reload**: If `ANTHROPIC_API_KEY` is set but empty, your shell ran `op read`
before 1Password was authenticated. Fix: `eval $(op signin) && source ~/.zshrc`.

**Module reload in tests**: `test_config.py` calls `importlib.reload(cfg_module)` in both the test
body and `teardown_method`. If you write new config tests, follow the same pattern — skipping
teardown reload will pollute subsequent tests with your patched env var.

**ChromaDB prompt disappears**: The `chromadb-docker.sh` script asks `Proceed? (y/N):` before
starting Colima. The prompt is written to stdout — if you don't see it, check that you're running
interactively (not in a CI pipe).
