"""Configuration for the Pokemon Trade Advisor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

# Resolved relative to this file, not cwd, so this works regardless of where
# `uv run python app.py` is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv_files(project_root: Path) -> None:
    """Load .env.local then .env, both with override=False.

    Real environment variables (a shell export, Docker's `environment:`,
    `op run`, CI secrets) always win over both files — dotenv only fills in
    variables that aren't already set. Loading .env.local FIRST means it
    also wins over .env, without needing override=True on that second call
    (which would incorrectly clobber a real shell-exported var).

    Factored out (rather than inlined below) so tests can point it at a
    tmp_path instead of mutating this project's real .env/.env.local files.
    """
    load_dotenv(project_root / ".env.local", override=False)
    load_dotenv(project_root / ".env", override=False)


_load_dotenv_files(_PROJECT_ROOT)


class ModelProvider(StrEnum):
    """Supported model providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


@dataclass
class ModelConfig:
    """Model configuration."""

    provider: ModelProvider
    model_name: str
    # Ollama only: the model name to use instead of `model_name` when OLLAMA_URL
    # points directly at Ollama Cloud's API (ollama.com) rather than a local
    # daemon. Ollama Cloud's direct API uses bare model names (no "-cloud"
    # suffix) — see Config.get_model() for where this gets applied.
    direct_api_model_name: str | None = None

    @property
    def model_id(self) -> str:
        """Get the full model identifier for pydantic-ai."""
        if self.provider == ModelProvider.OLLAMA:
            return f"ollama:{self.model_name}"
        return f"{self.provider.value}:{self.model_name}"


MODELS = {
    "claude-sonnet": ModelConfig(
        ModelProvider.ANTHROPIC,
        "claude-sonnet-4-6",  # Latest stable Sonnet as of Feb 2026
    ),
    "claude-haiku": ModelConfig(
        ModelProvider.ANTHROPIC,
        "claude-haiku-4-5",  # Current stable Haiku
    ),
    "gemini-flash": ModelConfig(ModelProvider.GEMINI, "gemini-1.5-flash"),
    "gemini-pro": ModelConfig(ModelProvider.GEMINI, "gemini-1.5-pro"),
    "gpt-4o": ModelConfig(ModelProvider.OPENAI, "gpt-4o"),
    "gpt-4o-mini": ModelConfig(ModelProvider.OPENAI, "gpt-4o-mini"),
    "llama": ModelConfig(ModelProvider.OLLAMA, "llama3.2"),
    # Ollama Cloud — one key, two transports, auto-detected from OLLAMA_URL:
    #   OLLAMA_URL=http://localhost:11434 (default) -> local daemon proxies to
    #     the cloud. Needs: brew install ollama && ollama signin && ollama pull
    #     gpt-oss:120b-cloud. `make ollama-mode-cloud-proxy` sets this up.
    #   OLLAMA_URL=https://ollama.com -> direct API access, no local install.
    #     Needs an API key from https://ollama.com/settings/keys, set as
    #     OLLAMA_API_KEY. `make ollama-mode-cloud-direct` sets this up.
    # More cloud models: https://ollama.com/search?c=cloud
    # or docs/REFERENCE/OLLAMA_CLOUD_MODELS.md for a point-in-time snapshot.
    "llama-cloud": ModelConfig(
        ModelProvider.OLLAMA,
        "gpt-oss:120b-cloud",
        direct_api_model_name="gpt-oss:120b",
    ),
}


@dataclass
class Config:
    """Application configuration."""

    # Model settings
    default_model: str = "claude-sonnet"

    # Embedding settings
    use_ollama_embeddings: bool = False
    ollama_embedding_model: str = "nomic-embed-text"

    # Infrastructure URLs
    chromadb_url: str = "http://localhost:8000"
    phoenix_url: str = "http://127.0.0.1:6006"
    ollama_url: str = "http://localhost:11434"
    smogon_url: str = "https://pkmn.github.io/smogon/data"

    # Project settings
    project_name: str = "pokemon-trade-advisor"

    # Platform PostgreSQL (optional) — set PLATFORM_DB_URL to enable live data
    platform_db_url: str | None = None

    # HTTP API tenant store (Phase 3) — Fernet key encrypting each tenant's
    # own platform_db_url at rest in data/tenants.db. Required for any tenant
    # operation (api.tenants); unused by the CLI. Generate with:
    #   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Back it up outside the deployment — losing it makes every stored
    # platform_db_url permanently unrecoverable, not just hard to find.
    tenant_db_encryption_key: str | None = None

    # HTTP API observability (Phase 4). Both optional — the API runs fine
    # with neither set, just without tracing/error-reporting wired up.
    #
    # ENABLE_PHOENIX opts the API into the *same* Phoenix/OTEL pipeline the
    # CLI uses (src/observability/observability.py's init_telemetry()), but
    # via setup(auto_start_phoenix=False) — never auto-starting Phoenix via
    # Docker/Colima the way the CLI's interactive startup does. If Phoenix
    # isn't already reachable, tracing is silently skipped rather than
    # trying to launch infrastructure from an unattended server process.
    enable_phoenix: bool = False

    # Sentry DSN for dedicated error tracking (free "Developer" tier: 5,000
    # errors/month — see ROADMAP.md Phase 4). sentry_sdk.init(dsn=None) is
    # documented as a safe no-op, so this is fine unset for local dev.
    sentry_dsn: str | None = None

    # Rate limiting storage (Phase 14) — a redis:// or rediss:// URI (e.g. an
    # Upstash Redis instance). None/unset falls back to slowapi's default
    # in-memory counter — correct for a single local dev process, but each
    # of a scaled-out API's own instances would then keep its own separate
    # count (see ROADMAP.md Phase 14's rate-limiting note). Also fixes a
    # smaller issue at single-instance scale: an in-memory counter resets on
    # every restart/redeploy.
    rate_limit_storage_uri: str | None = None

    # Chroma Cloud (ROADMAP.md Phase 14) — managed, hybrid-search-capable vector
    # storage, replacing self-hosted ChromaDB in production. chroma_api_key's presence is the
    # switch: set, PokemonVectorStore (src/rag/vector_store.py) talks to Chroma Cloud; unset,
    # it falls back to local self-hosted ChromaDB via config.chromadb_url — same "presence of
    # the value is the switch" idiom as platform_db_url/sentry_dsn above. Also read directly
    # from the CHROMA_API_KEY env var by chromadb's own ChromaCloudQwenEmbeddingFunction/
    # ChromaCloudSpladeEmbeddingFunction and CloudClient — no extra wiring needed, since
    # _load_dotenv_files() above already puts .env's values into os.environ.
    chroma_api_key: str | None = None
    chroma_tenant: str | None = None
    chroma_database: str | None = None
    # Optional — CloudClient's own default (api.trychroma.com) is correct for standard Chroma
    # Cloud SaaS. Only needed for a non-default deployment (e.g. a dedicated/custom host);
    # present here because Chroma's own project quickstart page includes it alongside the
    # other three vars regardless.
    chroma_host: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration at instantiation time."""
        if self.default_model not in MODELS:
            raise ValueError(f"Unknown model '{self.default_model}'. Available: {list(MODELS.keys())}")

    def get_model(self, name: str | None = None) -> ModelConfig:
        """Get model config by name.

        For Ollama entries with a `direct_api_model_name`, swaps in that name
        when `ollama_url` points directly at Ollama Cloud (ollama.com) rather
        than a local daemon — see ModelConfig.direct_api_model_name.
        """
        model_name = name or self.default_model
        if model_name not in MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(MODELS.keys())}")
        model = MODELS[model_name]
        if model.direct_api_model_name and "ollama.com" in self.ollama_url:
            return ModelConfig(model.provider, model.direct_api_model_name)
        return model

    @property
    def model_id(self) -> str:
        """Get the default model identifier."""
        return self.get_model().model_id


# Global config instance — all fields are env-var overridable.
# Set these in your shell or .env to point at non-default infrastructure.
config = Config(
    default_model=os.getenv("POKEMON_MODEL", "claude-sonnet"),
    use_ollama_embeddings=os.getenv("USE_OLLAMA_EMBEDDINGS", "").lower() == "true",
    chromadb_url=os.getenv("CHROMADB_URL", "http://localhost:8000"),
    phoenix_url=os.getenv("PHOENIX_URL", "http://127.0.0.1:6006"),
    ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    ollama_embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
    smogon_url=os.getenv("SMOGON_URL", "https://pkmn.github.io/smogon/data"),
    project_name=os.getenv("PROJECT_NAME", "pokemon-trade-advisor"),
    platform_db_url=os.getenv("PLATFORM_DB_URL") or None,
    tenant_db_encryption_key=os.getenv("TENANT_DB_ENCRYPTION_KEY") or None,
    enable_phoenix=os.getenv("ENABLE_PHOENIX", "").lower() == "true",
    sentry_dsn=os.getenv("SENTRY_DSN") or None,
    rate_limit_storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI") or None,
    chroma_api_key=os.getenv("CHROMA_API_KEY") or None,
    chroma_tenant=os.getenv("CHROMA_TENANT") or None,
    chroma_database=os.getenv("CHROMA_DATABASE") or None,
    chroma_host=os.getenv("CHROMA_HOST") or None,
)

# pydantic-ai's OllamaProvider reads OLLAMA_BASE_URL (not this project's own
# OLLAMA_URL) to know where to send Ollama requests — without this, any
# "ollama:*" model_id raises UserError at Agent construction time, regardless
# of local or cloud use.
#
# It must include a "/v1" suffix — OllamaProvider passes it straight to the
# OpenAI SDK client, which hits Ollama's OpenAI-compatible endpoints
# (http://localhost:11434/v1/chat/completions, or https://ollama.com/v1/...
# for direct cloud access), not Ollama's native /api/chat. config.ollama_url
# itself stays bare (no /v1) because it's also used for embeddings via
# get_ollama_embedding(), which calls Ollama's native /api/embeddings path.
#
# setdefault() so an explicitly-set OLLAMA_BASE_URL (e.g. for direct testing
# outside this app) always wins. _stripped guards against someone reasonably
# setting OLLAMA_URL to an already-/v1 value themselves (pydantic-ai's own
# docs show base_url with /v1 already on it), which would otherwise double up.
_stripped_ollama_url = config.ollama_url.rstrip("/")
if not _stripped_ollama_url.endswith("/v1"):
    _stripped_ollama_url += "/v1"
os.environ.setdefault("OLLAMA_BASE_URL", _stripped_ollama_url)
