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

CMD ["uv", "run", "python", "app.py"]
