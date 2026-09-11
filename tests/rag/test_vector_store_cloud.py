"""Tests for the Chroma Cloud backend of PokemonVectorStore (ROADMAP.md Phase 9).

Everything here mocks chromadb's own classes — no real Chroma Cloud account/API key/network
access is used or required, matching this project's standing policy of never needing a live
external service for `make test`. Live-service coverage belongs behind a
@requires_chroma_cloud-marked test instead (see pytest.ini's requires_chromadb marker for the
existing precedent), not here.

Dense-only, embeddings computed client-side — see vector_store.py's own module docstring for
why: Chroma Cloud's hosted Qwen/Splade embedding functions are blocked by a confirmed upstream
bug (a JSON schema-validation file missing from every published chromadb-client wheel, and from
Chroma's own GitHub source).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import rag.vector_store as vector_store_module
from rag.vector_store import PokemonVectorStore

# _create_cloud_collection is deliberately tested directly (TestCreateCloudCollection below),
# accessed as vector_store_module._create_cloud_collection with a pyright ignore at each call
# site rather than imported by name.


@pytest.fixture(autouse=True)
def cloud_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force PokemonVectorStore into cloud mode for every test in this file.

    Sets chroma_host explicitly (to None) too, not just the other three — otherwise this
    leaks whatever real value happens to be in the local developer's own .env (chroma_host is
    optional and most machines running these tests won't have it set, but this one might),
    making the test's behavior depend on the machine running it rather than being hermetic.

    Patches vector_store_module.config specifically, not config_module.config — verified
    directly that these can be two different objects by the time this file's tests run
    (tests/core/test_config.py's importlib.reload(cfg_module) replaces config_module.config
    partway through the session; rag/vector_store.py's own `from config import config` keeps
    its own, separate reference to whatever object existed when IT was first imported).
    Patching config_module.config here would silently no-op against the actual object
    PokemonVectorStore reads — see tests/conftest.py's _isolate_chroma_api_key for the full
    story (a real CHROMA_API_KEY leaking through this exact gap is what surfaced it).
    """
    monkeypatch.setattr(vector_store_module.config, "chroma_api_key", "test-api-key")
    monkeypatch.setattr(vector_store_module.config, "chroma_tenant", "test-tenant")
    monkeypatch.setattr(vector_store_module.config, "chroma_database", "test-database")
    monkeypatch.setattr(vector_store_module.config, "chroma_host", None)


@pytest.fixture
def mock_collection() -> MagicMock:
    """A mock Chroma Cloud collection — what get_or_create_collection returns."""
    collection = MagicMock()
    collection.search.return_value.rows.return_value = [[]]
    return collection


@pytest.fixture
def mock_cloud_client(mock_collection: MagicMock) -> MagicMock:
    client = MagicMock()
    client.get_or_create_collection.return_value = mock_collection
    return client


def _make_store(
    mock_cloud_client: MagicMock, mock_collection: MagicMock, collection_name: str = "pokemon"
) -> PokemonVectorStore:
    with (
        patch("chromadb.CloudClient", return_value=mock_cloud_client),
        patch.object(vector_store_module, "_create_cloud_collection", return_value=mock_collection) as mock_create,
    ):
        store = PokemonVectorStore(collection_name=collection_name)
    mock_create.assert_called_once_with(mock_cloud_client, collection_name)
    return store


class TestInitialization:
    def test_use_cloud_is_true_when_api_key_is_set(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        store = _make_store(mock_cloud_client, mock_collection)
        assert store.use_cloud is True

    def test_cloud_client_constructed_with_config_values(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        with (
            patch("chromadb.CloudClient", return_value=mock_cloud_client) as mock_cls,
            patch.object(vector_store_module, "_create_cloud_collection", return_value=mock_collection),
        ):
            PokemonVectorStore()

        mock_cls.assert_called_once_with(tenant="test-tenant", database="test-database", api_key="test-api-key")

    def test_cloud_host_is_passed_through_when_set(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vector_store_module.config, "chroma_host", "custom.example.com")

        with (
            patch("chromadb.CloudClient", return_value=mock_cloud_client) as mock_cls,
            patch.object(vector_store_module, "_create_cloud_collection", return_value=mock_collection),
        ):
            PokemonVectorStore()

        mock_cls.assert_called_once_with(
            tenant="test-tenant", database="test-database", api_key="test-api-key", cloud_host="custom.example.com"
        )


class TestCreateCloudCollection:
    def test_calls_get_or_create_collection_with_no_schema(self) -> None:
        """No schema — see vector_store.py's module docstring on why (blocked upstream bug)."""
        mock_client = MagicMock()

        vector_store_module._create_cloud_collection(mock_client, "pokemon")  # pyright: ignore[reportPrivateUsage]

        mock_client.get_or_create_collection.assert_called_once_with(name="pokemon")


class TestAddPokemon:
    def test_adds_one_id_and_document_per_pokemon(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        store = _make_store(mock_cloud_client, mock_collection)

        store.add_pokemon([{"name": "Pikachu", "types": ["Electric"], "stats": {"hp": 35}}])

        _, kwargs = mock_collection.add.call_args
        assert kwargs["ids"] == ["Pikachu::0"]
        assert "Pikachu" in kwargs["documents"][0]

    def test_short_document_metadata_carries_source_document_id_and_chunk_index(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        store = _make_store(mock_cloud_client, mock_collection)

        store.add_pokemon([{"name": "Pikachu", "types": ["Electric"], "stats": {}}])

        _, kwargs = mock_collection.add.call_args
        metadata = kwargs["metadatas"][0]
        assert metadata["source_document_id"] == "Pikachu"
        assert metadata["chunk_index"] == "0"

    def test_computes_and_sends_an_embedding(self, mock_cloud_client: MagicMock, mock_collection: MagicMock) -> None:
        """Dense-only, computed client-side (see module docstring) — unlike the originally
        planned schema-based design, add() here must be called WITH real embeddings.
        """
        store = _make_store(mock_cloud_client, mock_collection)

        store.add_pokemon([{"name": "Pikachu", "types": ["Electric"], "stats": {}}])

        _, kwargs = mock_collection.add.call_args
        assert len(kwargs["embeddings"]) == 1
        assert isinstance(kwargs["embeddings"][0], list)
        assert len(kwargs["embeddings"][0]) > 0


class TestAddDocuments:
    def test_forwards_the_given_embeddings(self, mock_cloud_client: MagicMock, mock_collection: MagicMock) -> None:
        store = _make_store(mock_cloud_client, mock_collection)

        store.add_documents(
            ids=["doc1"],
            documents=["some strategy text"],
            metadatas=[{"name": "doc1"}],
            embeddings=[[0.1, 0.2, 0.3]],
        )

        _, kwargs = mock_collection.add.call_args
        assert kwargs["ids"] == ["doc1::0"]
        assert kwargs["embeddings"] == [[0.1, 0.2, 0.3]]

    def test_oversized_document_is_split_into_multiple_chunk_ids(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        store = _make_store(mock_cloud_client, mock_collection)
        big_text = "\n".join(["x" * 100] * 300)  # ~30KB, over the 16KB limit

        store.add_documents(ids=["doc1"], documents=[big_text], metadatas=[{"name": "doc1"}], embeddings=[[0.1]])

        _, kwargs = mock_collection.add.call_args
        assert len(kwargs["ids"]) > 1
        assert all(cid.startswith("doc1::") for cid in kwargs["ids"])

    def test_oversized_document_reuses_the_same_embedding_for_every_chunk(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        """A known, accepted inaccuracy — see _add_cloud's own docstring — not a bug: nothing
        actually gets chunked today, so this only matters once something does.
        """
        store = _make_store(mock_cloud_client, mock_collection)
        big_text = "\n".join(["x" * 100] * 300)

        store.add_documents(ids=["doc1"], documents=[big_text], metadatas=[{"name": "doc1"}], embeddings=[[0.1, 0.2]])

        _, kwargs = mock_collection.add.call_args
        assert len(kwargs["embeddings"]) == len(kwargs["ids"])
        assert all(e == [0.1, 0.2] for e in kwargs["embeddings"])


class TestQuery:
    def test_empty_results_returns_empty_list(self, mock_cloud_client: MagicMock, mock_collection: MagicMock) -> None:
        store = _make_store(mock_cloud_client, mock_collection)

        results = store.query("electric mouse")

        assert results == []

    def test_parses_rows_into_the_common_result_shape(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        mock_collection.search.return_value.rows.return_value = [
            [{"id": "Pikachu", "document": "Pokemon: Pikachu", "metadata": {"name": "Pikachu"}, "score": 0.1}]
        ]
        store = _make_store(mock_cloud_client, mock_collection)

        results = store.query("electric mouse")

        assert results == [{"document": "Pokemon: Pikachu", "metadata": {"name": "Pikachu"}, "distance": 0.1}]

    def test_search_uses_a_knn_rank_with_a_computed_embedding(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        from chromadb import Knn

        store = _make_store(mock_cloud_client, mock_collection)

        store.query("electric mouse")

        (search_arg,), _ = mock_collection.search.call_args
        rank = search_arg._rank  # pyright: ignore[reportPrivateUsage]
        assert isinstance(rank, Knn)
        assert isinstance(rank.query, list)  # a computed embedding vector, not the raw query string

    def test_search_groups_by_source_document_id(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        store = _make_store(mock_cloud_client, mock_collection)

        store.query("electric mouse")

        (search_arg,), _ = mock_collection.search.call_args
        assert search_arg._group_by is not None  # pyright: ignore[reportPrivateUsage]


class TestDeleteAndClose:
    def test_delete_collection_calls_cloud_client(
        self, mock_cloud_client: MagicMock, mock_collection: MagicMock
    ) -> None:
        store = _make_store(mock_cloud_client, mock_collection, collection_name="pokemon")

        store.delete_collection()

        mock_cloud_client.delete_collection.assert_called_once_with(name="pokemon")

    def test_close_does_not_raise(self, mock_cloud_client: MagicMock, mock_collection: MagicMock) -> None:
        store = _make_store(mock_cloud_client, mock_collection)

        store.close()  # no httpx.Client exists in cloud mode — must not AttributeError
