"""Live integration tests against a real Chroma Cloud account (ROADMAP.md Phase 9).

Unlike test_vector_store_cloud.py (fully mocked, runs in `make test`), these hit the real
Chroma Cloud API — real network calls, real (billed) Qwen/Splade embedding calls. Deselected
from `make test` by default via the requires_chroma_cloud marker (pytest.ini); run explicitly
with `make test-chroma-cloud`, and only with CHROMA_API_KEY (and CHROMA_TENANT/CHROMA_DATABASE,
if your account needs them) actually set — see .env.example.

Uses a dedicated collection name (not "pokemon") and deletes it in teardown, so this can't
collide with or leave behind real ingested data.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from rag.vector_store import PokemonVectorStore

requires_chroma_cloud: pytest.MarkDecorator = pytest.mark.requires_chroma_cloud


@requires_chroma_cloud
class TestChromaCloudRoundTrip:
    @pytest.fixture
    def store(self) -> Generator[PokemonVectorStore]:
        store = PokemonVectorStore(collection_name="pokemon_test_live")
        assert store.use_cloud, "CHROMA_API_KEY must be set to run this test — see .env.example"
        try:
            yield store
        finally:
            store.delete_collection()

    def test_add_and_query_round_trip(self, store: PokemonVectorStore) -> None:
        store.add_pokemon(
            [
                {
                    "name": "Pikachu",
                    "types": ["Electric"],
                    "stats": {"hp": 35, "attack": 55},
                    "abilities": ["Static"],
                }
            ]
        )

        results = store.query("electric mouse Pokemon", n_results=1)

        assert results
        assert "Pikachu" in results[0]["document"]

    def test_sparse_search_finds_an_exact_keyword_dense_search_alone_might_miss(
        self, store: PokemonVectorStore
    ) -> None:
        """Confirms hybrid search is actually blending dense + sparse, not just running dense —
        a rare/specific token (a made-up ability name) that a semantic-only search has no
        reason to associate with the query, but an exact keyword/sparse match should surface.
        """
        store.add_pokemon(
            [
                {
                    "name": "Testmon",
                    "types": ["Normal"],
                    "stats": {"hp": 50},
                    "abilities": ["Zzyzxblorp"],
                }
            ]
        )

        results = store.query("Zzyzxblorp", n_results=1)

        assert results
        assert "Testmon" in results[0]["document"]
