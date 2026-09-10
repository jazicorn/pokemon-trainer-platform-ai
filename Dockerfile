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
RUN uv sync --locked --no-dev --no-install-project

# Now add the application source.
COPY app.py ./
COPY src/ ./src/

# Run as a non-root user. --create-home gives it a real $HOME so `uv run`'s
# own cache resolution (e.g. XDG_CACHE_HOME's default) has somewhere
# writable; chown /app so the venv `uv sync` already populated (as root,
# above) stays usable.
#
# Note for docker-compose's `./data:/app/data` volume mount: the host
# directory's ownership needs to allow writes from this container UID, or
# align the two explicitly (e.g. a matching --uid here, or a permissive host
# directory) — a volume-permissions concern this Dockerfile alone can't fully
# solve, since it depends on the host side too.
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uv", "run", "python", "app.py"]
