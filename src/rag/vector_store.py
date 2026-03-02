"""ChromaDB vector store for Pokemon data using v2 API."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, cast

import httpx

from config import config

if TYPE_CHECKING:
    from typing import Any


def get_simple_embedding(text: str, dim: int = 384) -> list[float]:
    """Generate a deterministic hash-based embedding.

    Sufficient for testing but NOT semantically meaningful.
    For semantic search, use get_ollama_embedding instead.
    """
    hash_bytes = hashlib.sha384(text.lower().encode()).digest()
    return [b / 255.0 for b in hash_bytes[:dim]]


def get_ollama_embedding(
    text: str,
    model: str | None = None,
    base_url: str | None = None,
) -> list[float]:
    """Generate embedding using Ollama.

    Requires: ollama running with embedding model.
    Setup: brew install ollama && ollama pull nomic-embed-text

    Args:
        text: Text to embed.
        model: Ollama embedding model. Defaults to config.ollama_embedding_model.
        base_url: Ollama base URL. Defaults to config.ollama_url.
    """
    resolved_model = model or config.ollama_embedding_model
    resolved_url = base_url or config.ollama_url
    response = httpx.post(
        f"{resolved_url}/api/embeddings",
        json={"model": resolved_model, "prompt": text},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["embedding"]


# Resolved at import time from config — set USE_OLLAMA_EMBEDDINGS=true to use Ollama.
get_embedding = get_ollama_embedding if config.use_ollama_embeddings else get_simple_embedding


class PokemonVectorStore:
    """Vector store for Pokemon data using ChromaDB v2 HTTP API."""

    def __init__(self, collection_name: str = "pokemon"):
        """Initialize the vector store."""
        self.collection_name = collection_name
        self.collection_id: str | None = None
        self.client = httpx.Client(timeout=30.0)
        _api_path = "/api/v2/tenants/default_tenant/databases/default_database"
        self._api_base = f"{config.chromadb_url}{_api_path}"
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        response = self.client.post(
            f"{self._api_base}/collections",
            json={"name": self.collection_name, "get_or_create": True},
        )
        response.raise_for_status()
        self.collection_id = response.json()["id"]

    def add_pokemon(self, pokemon_list: list[dict[str, Any]]) -> None:
        """Add Pokemon data to the vector store."""
        if not self.collection_id:
            raise RuntimeError("Collection not initialized")

        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []
        embeddings: list[list[float]] = []

        for pokemon in pokemon_list:
            doc_text = self._create_document_text(pokemon)
            name = cast(str, pokemon["name"])
            types = cast(list[str], pokemon["types"])
            documents.append(doc_text)
            metadatas.append({
                "name": name,
                "types": ",".join(types),
                "is_legendary": str(pokemon.get("is_legendary", False)),
                "is_mythical": str(pokemon.get("is_mythical", False)),
                "smogon_tier": str(pokemon.get("smogon_tier", "Unknown")),
            })
            ids.append(name)
            embeddings.append(get_embedding(doc_text))

        response = self.client.post(
            f"{self._api_base}/collections/{self.collection_id}/add",
            json={
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
                "embeddings": embeddings,
            },
        )
        response.raise_for_status()

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        """Add pre-built documents directly to the collection.

        Use this when document text is constructed outside the store
        (e.g. Smogon strategy data) rather than via add_pokemon().
        """
        if not self.collection_id:
            raise RuntimeError("Collection not initialized")

        response = self.client.post(
            f"{self._api_base}/collections/{self.collection_id}/add",
            json={
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
                "embeddings": embeddings,
            },
        )
        response.raise_for_status()

    def _create_document_text(self, pokemon: dict[str, Any]) -> str:
        """Create searchable text from Pokemon data."""
        stats = cast(dict[str, int], pokemon.get("stats", {}))
        stat_text = ", ".join(f"{k}: {v}" for k, v in stats.items())
        types = cast(list[str], pokemon["types"])
        abilities = cast(list[str], pokemon.get("abilities", []))

        parts = [
            f"Pokemon: {pokemon['name']}",
            f"Types: {', '.join(types)}",
            f"Stats: {stat_text}",
            f"Abilities: {', '.join(abilities)}",
        ]

        if pokemon.get("is_legendary"):
            parts.append("This is a Legendary Pokemon.")
        if pokemon.get("is_mythical"):
            parts.append("This is a Mythical Pokemon.")
        if smogon_tier := pokemon.get("smogon_tier"):
            parts.append(f"Competitive Tier (Smogon): {smogon_tier}.")
        if pokemon.get("description"):
            parts.append(f"Description: {pokemon['description']}")

        return " ".join(parts)

    def query(self, query_text: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Query the vector store."""
        if not self.collection_id:
            raise RuntimeError("Collection not initialized")

        query_embedding = get_embedding(query_text)

        response = self.client.post(
            f"{self._api_base}/collections/{self.collection_id}/query",
            json={
                "query_embeddings": [query_embedding],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            },
        )
        response.raise_for_status()
        data = response.json()

        results: list[dict[str, Any]] = []
        if data.get("documents") and data["documents"][0]:
            for i, doc in enumerate(data["documents"][0]):
                results.append({
                    "document": doc,
                    "metadata": data.get("metadatas", [[]])[0][i] or {},
                    "distance": data.get("distances", [[]])[0][i] or 0,
                })
        return results

    def delete_collection(self) -> None:
        """Delete the collection by name."""
        response = self.client.delete(
            f"{self._api_base}/collections/{self.collection_name}"
        )
        response.raise_for_status()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
        