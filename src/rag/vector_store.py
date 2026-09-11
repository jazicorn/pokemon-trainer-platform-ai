"""Vector store for Pokemon data (ROADMAP.md Phase 9).

Two backends, chosen automatically by whether config.chroma_api_key is set (same "presence of
the value is the switch" idiom as platform_db_url/sentry_dsn in config.py):

- **Cloud** (chroma_api_key set): Chroma Cloud, via the official `chromadb` client. Dense-only,
  embeddings computed client-side (get_simple_embedding/get_ollama_embedding — same functions
  local mode uses), not Chroma Cloud's hosted Qwen/Splade functions. Those were the original
  design here, but both depend on a JSON schema-validation file that's missing from every
  published chromadb-client wheel (1.5.6-1.5.9, verified directly) *and* from Chroma's own
  GitHub source — a genuine upstream bug, not something fixable client-side. Revisit hosted
  embeddings (and real hybrid/sparse search) once that's fixed upstream. GroupBy dedup across
  chunks of the same source document (see chunking.py) still applies, using plain Knn distance
  — no Rrf, since there's only one ranking signal without a sparse index. Documents over
  Chroma's 16 KiB limit are still chunked transparently before upload — that limit is on the
  document field itself, unrelated to which side computes the embedding.
- **Local** (chroma_api_key unset — the default, and what tests/local dev use): unchanged from
  before this phase — raw httpx calls against self-hosted ChromaDB's v2 REST API.

Both are exposed through the same PokemonVectorStore public interface, so callers
(rag/ingest.py, rag/smogon_ingest.py, the agents/ modules) don't need to know which backend is
active.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, cast

import httpx

from config import config
from rag.chunking import chunk_document

if TYPE_CHECKING:
    from typing import Any

    from chromadb import Collection


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


# Resolved at import time from config — set USE_OLLAMA_EMBEDDINGS=true to use Ollama. Used by
# both backends now — see module docstring on why cloud mode doesn't use Chroma's own hosted
# embedding functions.
get_embedding = get_ollama_embedding if config.use_ollama_embeddings else get_simple_embedding

# The metadata key GroupBy dedups on (see _query_cloud) — named once here rather than repeated
# as a string literal.
_SOURCE_DOCUMENT_ID_KEY = "source_document_id"
_CHUNK_INDEX_KEY = "chunk_index"


def create_cloud_client() -> Any:
    """Build a Chroma Cloud CloudClient from config — shared by PokemonVectorStore and
    utils.is_vector_store_running() so the tenant/database/api_key/cloud_host wiring lives in
    exactly one place. Callers are responsible for checking config.chroma_api_key first.
    """
    from chromadb import CloudClient

    # cloud_host is keyword-only on CloudClient and only accepted when explicitly passed —
    # omit entirely rather than pass None, so CloudClient's own default (api.trychroma.com)
    # applies for the common case where chroma_host is unset.
    cloud_client_kwargs: dict[str, Any] = {
        "tenant": config.chroma_tenant,
        "database": config.chroma_database,
        "api_key": config.chroma_api_key,
    }
    if config.chroma_host:
        cloud_client_kwargs["cloud_host"] = config.chroma_host
    return CloudClient(**cloud_client_kwargs)


def _create_cloud_collection(client: Any, collection_name: str) -> Collection:
    """get_or_create the Chroma Cloud collection.

    No schema — see module docstring: hosted embedding functions are blocked by an upstream
    bug, so this collection stores client-computed embeddings passed explicitly on add/query,
    the same way local mode already does.
    """
    return cast("Collection", client.get_or_create_collection(name=collection_name))


class PokemonVectorStore:
    """Vector store for Pokemon data — see module docstring for the two backends."""

    def __init__(self, collection_name: str = "pokemon"):
        """Initialize the vector store."""
        self.collection_name = collection_name
        self.use_cloud = bool(config.chroma_api_key)

        if self.use_cloud:
            self._cloud_client = create_cloud_client()
            self._collection = _create_cloud_collection(self._cloud_client, collection_name)
        else:
            self.collection_id: str | None = None
            self.client = httpx.Client(timeout=30.0)
            _api_path = "/api/v2/tenants/default_tenant/databases/default_database"
            self._api_base = f"{config.chromadb_url}{_api_path}"
            self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist (local mode only)."""
        response = self.client.post(
            f"{self._api_base}/collections",
            json={"name": self.collection_name, "get_or_create": True},
        )
        response.raise_for_status()
        self.collection_id = response.json()["id"]

    def add_pokemon(self, pokemon_list: list[dict[str, Any]]) -> None:
        """Add Pokemon data to the vector store."""
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []

        for pokemon in pokemon_list:
            doc_text = self._create_document_text(pokemon)
            name = cast(str, pokemon["name"])
            types = cast(list[str], pokemon["types"])
            documents.append(doc_text)
            metadatas.append(
                {
                    "name": name,
                    "types": ",".join(types),
                    "is_legendary": str(pokemon.get("is_legendary", False)),
                    "is_mythical": str(pokemon.get("is_mythical", False)),
                    "smogon_tier": str(pokemon.get("smogon_tier", "Unknown")),
                }
            )
            ids.append(name)

        embeddings = [get_embedding(d) for d in documents]
        if self.use_cloud:
            self._add_cloud(ids, documents, metadatas, embeddings)
        else:
            self._add_local(ids, documents, metadatas, embeddings)

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        """Add pre-built documents directly to the collection.

        Use this when document text is constructed outside the store (e.g. Smogon strategy
        data) rather than via add_pokemon().
        """
        if self.use_cloud:
            self._add_cloud(ids, documents, metadatas, embeddings)
        else:
            self._add_local(ids, documents, metadatas, embeddings)

    def _add_cloud(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        """Chunk any oversized document (Chroma Cloud's 16 KiB/document limit — see
        chunking.py), tag every chunk with source_document_id/chunk_index for GroupBy dedup at
        query time.

        A chunked document's embedding is a real inaccuracy today, not just a simplification:
        the same pre-computed embedding (of the *whole* document) is reused for every one of
        its chunks, rather than each chunk getting its own. Harmless in practice right now,
        since nothing is actually large enough to get chunked (see chunking.py's own
        docstring) — worth revisiting (embed each chunk's own text) if that changes.
        """
        chunk_ids: list[str] = []
        chunk_documents: list[str] = []
        chunk_metadatas: list[dict[str, str]] = []
        chunk_embeddings: list[list[float]] = []

        for doc_id, doc_text, metadata, embedding in zip(ids, documents, metadatas, embeddings, strict=True):
            for chunk in chunk_document(doc_id, doc_text, metadata=metadata):
                chunk_ids.append(chunk.chunk_id)
                chunk_documents.append(chunk.text)
                chunk_embeddings.append(embedding)
                chunk_metadatas.append(
                    {
                        **chunk.metadata,
                        _SOURCE_DOCUMENT_ID_KEY: chunk.source_document_id,
                        _CHUNK_INDEX_KEY: str(chunk.chunk_index),
                    }
                )

        # cast: list's invariance means list[dict[str, str]]/list[list[float]] don't satisfy
        # chromadb's own List[Metadata]/List[Embedding] parameter types, even though
        # dict[str, str] and list[float] are each structurally valid on their own.
        self._collection.add(
            ids=chunk_ids,
            documents=chunk_documents,
            metadatas=cast("list[Any]", chunk_metadatas),
            embeddings=cast("list[Any]", chunk_embeddings),
        )

    def _add_local(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
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
        if self.use_cloud:
            return self._query_cloud(query_text, n_results)
        return self._query_local(query_text, n_results)

    def _query_cloud(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
        """Dense-only search (see module docstring on why — no hosted embedding functions,
        so no sparse index and no Rrf fusion signal to add). Still GroupBy'd on
        source_document_id so multiple chunks of the same source document collapse to their
        single best-scoring chunk (a no-op today, since nothing is currently large enough to
        get chunked — see chunking.py's own docstring — but keeps this correct once something
        is).

        Uses the same Search/Knn/GroupBy building blocks a real hybrid search would (rather
        than the older query() API) precisely so re-adding a second (sparse) rank signal later
        — once Chroma's upstream bug is fixed — is a small diff here, not a rewrite.
        """
        from chromadb import K, Knn, Search
        from chromadb.execution.expression.operator import GroupBy, MinK

        candidate_limit = max(n_results * 4, 20)  # gather enough candidates before GroupBy dedup
        query_embedding = get_embedding(query_text)

        # MinK, not MaxK: plain Knn's own score is a distance — lower means closer/better —
        # so MinK(k=1) keeps each group's single best-scoring chunk, not its worst.
        search = (
            Search()
            .rank(Knn(query=query_embedding, limit=candidate_limit))
            .group_by(GroupBy(keys=K(_SOURCE_DOCUMENT_ID_KEY), aggregate=MinK(keys=K.SCORE, k=1)))
            .limit(n_results)
            .select(K.DOCUMENT, K.SCORE, K.METADATA)
        )
        # search() takes a single Search or a list of them, batching results one outer list
        # entry per Search submitted — .rows()[0] is this call's one (and only) payload.
        # SearchResultRow is a plain TypedDict (id/document/embedding/metadata/score string
        # keys), not the K.* constants used to build the query itself.
        payloads = self._collection.search(search).rows()
        rows = payloads[0] if payloads else []

        return [
            {
                "document": row.get("document"),
                "metadata": row.get("metadata") or {},
                "distance": row.get("score") or 0,
            }
            for row in rows
        ]

    def _query_local(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
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
                results.append(
                    {
                        "document": doc,
                        "metadata": data.get("metadatas", [[]])[0][i] or {},
                        "distance": data.get("distances", [[]])[0][i] or 0,
                    }
                )
        return results

    def delete_collection(self) -> None:
        """Delete the collection by name."""
        if self.use_cloud:
            self._cloud_client.delete_collection(name=self.collection_name)
        else:
            response = self.client.delete(f"{self._api_base}/collections/{self.collection_name}")
            response.raise_for_status()

    def close(self) -> None:
        """Close the HTTP client (local mode only — the cloud client has no persistent
        connection of its own to close).
        """
        if not self.use_cloud:
            self.client.close()
