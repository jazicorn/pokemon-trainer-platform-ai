"""Configuration for the Pokemon Trade Advisor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class ModelProvider(str, Enum):
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
    
    @property
    def model_id(self) -> str:
        """Get the full model identifier for pydantic-ai."""
        if self.provider == ModelProvider.OLLAMA:
            return f"ollama:{self.model_name}"
        return f"{self.provider.value}:{self.model_name}"


MODELS = {
    "claude-sonnet": ModelConfig(
        ModelProvider.ANTHROPIC, "claude-sonnet-4-6"  # Latest stable Sonnet as of Feb 2026
    ),
    "claude-haiku": ModelConfig(
        ModelProvider.ANTHROPIC, "claude-haiku-4-5"  # Current stable Haiku
    ),
    "gemini-flash": ModelConfig(
        ModelProvider.GEMINI, "gemini-1.5-flash"
    ),
    "gemini-pro": ModelConfig(
        ModelProvider.GEMINI, "gemini-1.5-pro"
    ),
    "gpt-4o": ModelConfig(
        ModelProvider.OPENAI, "gpt-4o"
    ),
    "gpt-4o-mini": ModelConfig(
        ModelProvider.OPENAI, "gpt-4o-mini"
    ),
    "llama": ModelConfig(
        ModelProvider.OLLAMA, "llama3.2"
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

    def __post_init__(self) -> None:
        """Validate configuration at instantiation time."""
        if self.default_model not in MODELS:
            raise ValueError(
                f"Unknown model '{self.default_model}'. "
                f"Available: {list(MODELS.keys())}"
            )

    def get_model(self, name: str | None = None) -> ModelConfig:
        """Get model config by name."""
        model_name = name or self.default_model
        if model_name not in MODELS:
            raise ValueError(
                f"Unknown model: {model_name}. "
                f"Available: {list(MODELS.keys())}"
            )
        return MODELS[model_name]

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
)
