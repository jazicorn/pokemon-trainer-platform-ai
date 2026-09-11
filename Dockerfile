# Runtime image for the Pokemon Trainer's Second Brain CLI.
#
# This packages the CLI app only — ChromaDB, Phoenix, and (optionally)
# PostgreSQL are separate services in docker-compose.yml, not built here.
#
# Build:  docker compose build app
# Run:    docker compose run --rm app

FROM python:3.13-slim

# Pinned to match the uv version used locally (see `uv --version`).
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

# Install third-party dependencies first, separately from app source, for
# better layer caching. --no-install-project skips packaging this repo
# itself (chromadb_setup's console script isn't needed inside this image —
# the CLI is launched directly via `uv run python app.py`).
COPY pyproject.toml uv.lock ./
# platform-db: psycopg, needed by the API server for every tenant's own
# Postgres connection (Phase 3+), and by self-serve registration's
# connectivity check (Phase 15) before a tenant is even stored.
RUN uv sync --locked --no-dev --no-install-project --group platform-db

# Now add the application source.
COPY app.py api_server.py ./
COPY src/ ./src/

# Non-root runtime user. --create-home gives it a real $HOME so `uv run`'s
# own cache resolution (e.g. XDG_CACHE_HOME's default) has somewhere
# writable; chown /app so the venv `uv sync` already populated (as root,
# above) stays usable. gosu is what docker-entrypoint.sh uses to drop from
# root to this user after fixing up /app/data's ownership at container
# start (see that script) — a freshly created volume (Docker or Fly) is
# root-owned regardless of this USER line.
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app \
    && apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Stays root here deliberately — docker-entrypoint.sh is the one that drops
# to appuser, after it can still chown /app/data as root.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uv", "run", "python", "app.py"]
