"""Tests for memory system."""

from collections.abc import Generator
from pathlib import Path
from typing import NoReturn

import pytest

import utils as utils_module
from memory.conversation_memory import ConversationMemory, RecommendationMemory
from memory.database import (
    get_connection,
    init_database,
)
from memory.user_preferences import UserPreferencesManager
from utils import is_chromadb_running, is_vector_store_running


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    """Use a temporary database for tests."""
    test_db = tmp_path / "test_memory.db"

    # Patch the DB_NAME constant so get_db_path returns test path
    monkeypatch.setattr("memory.database.DB_NAME", str(test_db))
    monkeypatch.setattr("memory.database.get_db_path", lambda: test_db)

    init_database()
    yield test_db

    # Cleanup
    if test_db.exists():
        test_db.unlink()


class TestDatabase:
    """Tests for database setup."""

    def test_init_creates_tables(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = {row[0] for row in cursor.fetchall()}

        assert "user_preferences" in tables
        assert "conversation_history" in tables
        assert "recommendations" in tables
        assert "learned_preferences" in tables


class TestChromaDBCheck:
    """Tests for ChromaDB service check."""

    def test_is_chromadb_running_returns_bool(self):
        result = is_chromadb_running()
        assert isinstance(result, bool)

    def test_is_chromadb_running_when_available(self, monkeypatch: pytest.MonkeyPatch):
        """Test when ChromaDB is available."""

        class MockResponse:
            status_code = 200

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse()

        monkeypatch.setattr("utils.httpx.get", mock_get)
        assert is_chromadb_running() is True

    def test_is_chromadb_running_when_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        """Test when ChromaDB is not available."""
        import httpx

        def mock_get(*args: object, **kwargs: object) -> NoReturn:
            raise httpx.RequestError("Connection refused")

        monkeypatch.setattr("utils.httpx.get", mock_get)
        assert is_chromadb_running() is False


class TestIsVectorStoreRunning:
    """ROADMAP.md Phase 9 — checks whichever backend is actually active, not always
    self-hosted ChromaDB.
    """

    def test_falls_back_to_is_chromadb_running_when_chroma_api_key_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patched on utils_module.config specifically, not config_module.config — these can be
        # two different objects (see tests/conftest.py's _isolate_chroma_api_key for why,
        # verified directly: this exact gap once let a real CHROMA_API_KEY leak through).
        # is_vector_store_running() itself lives in utils.py and reads utils.py's own binding.
        monkeypatch.setattr(utils_module.config, "chroma_api_key", None)
        monkeypatch.setattr("utils.is_chromadb_running", lambda: True)

        assert is_vector_store_running() is True

    def test_checks_chroma_cloud_when_chroma_api_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock

        monkeypatch.setattr(utils_module.config, "chroma_api_key", "test-key")
        mock_client = MagicMock()
        monkeypatch.setattr("rag.vector_store.create_cloud_client", lambda: mock_client)

        assert is_vector_store_running() is True
        mock_client.heartbeat.assert_called_once()

    def test_returns_false_when_chroma_cloud_is_unreachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(utils_module.config, "chroma_api_key", "test-key")

        def raise_connection_error() -> None:
            raise ConnectionError("unreachable")

        monkeypatch.setattr("rag.vector_store.create_cloud_client", raise_connection_error)

        assert is_vector_store_running() is False


class TestUserPreferencesManager:
    """Tests for UserPreferencesManager."""

    def test_save_and_get_preferences(self):
        manager = UserPreferencesManager("test_user")
        manager.save_preferences(
            favorite_types=["fire", "dragon"],
            goal="collect_legendaries",
            trading_style="value_focused",
        )

        prefs = manager.get_preferences()
        assert prefs["favorite_types"] == ["fire", "dragon"]
        assert prefs["goal"] == "collect_legendaries"
        assert prefs["trading_style"] == "value_focused"

    def test_get_empty_preferences(self):
        manager = UserPreferencesManager("nonexistent_user")
        prefs = manager.get_preferences()
        assert prefs == {}

    def test_update_seeking_add(self):
        manager = UserPreferencesManager("test_user")
        manager.save_preferences(seeking=["pikachu"])
        manager.update_seeking("charizard", add=True)

        prefs = manager.get_preferences()
        assert "charizard" in prefs["seeking"]
        assert "pikachu" in prefs["seeking"]

    def test_update_seeking_remove(self):
        manager = UserPreferencesManager("test_user")
        manager.save_preferences(seeking=["pikachu", "charizard"])
        manager.update_seeking("pikachu", add=False)

        prefs = manager.get_preferences()
        assert "pikachu" not in prefs["seeking"]
        assert "charizard" in prefs["seeking"]

    def test_update_never_trade(self):
        manager = UserPreferencesManager("test_user")
        manager.save_preferences(never_trade=[])
        manager.update_never_trade("mewtwo", add=True)

        prefs = manager.get_preferences()
        assert "mewtwo" in prefs["never_trade"]


class TestConversationMemory:
    """Tests for ConversationMemory."""

    def test_add_and_get_message(self):
        memory = ConversationMemory("test_user_conv")
        memory.clear()  # Ensure clean state
        memory.add_message("user", "Hello")
        memory.add_message("assistant", "Hi there!")

        history = memory.get_history()
        assert len(history) == 2
        roles = {msg["role"] for msg in history}
        assert "user" in roles
        assert "assistant" in roles

    def test_get_history_limit(self):
        memory = ConversationMemory("test_user_limit")
        memory.clear()
        for i in range(10):
            memory.add_message("user", f"Message {i}")

        history = memory.get_history(limit=3)
        assert len(history) == 3

    def test_get_context_string(self):
        memory = ConversationMemory("test_user_context")
        memory.clear()
        memory.add_message("user", "Should I trade?")
        memory.add_message("assistant", "Let me check.")

        context = memory.get_context_string()
        assert "User:" in context
        assert "Assistant:" in context

    def test_clear_history(self):
        memory = ConversationMemory("test_user_clear")
        memory.add_message("user", "Hello")
        memory.clear()

        history = memory.get_history()
        assert len(history) == 0

    def test_trim_history(self):
        memory = ConversationMemory("test_user_trim", max_history=5)
        memory.clear()
        for i in range(10):
            memory.add_message("user", f"Message {i}")

        history = memory.get_history(limit=20)
        assert len(history) == 5


class TestRecommendationMemory:
    """Tests for RecommendationMemory."""

    def test_save_recommendation(self):
        memory = RecommendationMemory("test_user")
        rec_id = memory.save_recommendation(
            offered_pokemon="alakazam",
            requested_pokemon="machamp",
            recommendation="decline",
            reasoning="Alakazam has higher demand",
        )

        assert rec_id > 0

    def test_record_feedback(self):
        memory = RecommendationMemory("test_user")
        rec_id = memory.save_recommendation(
            offered_pokemon="pikachu",
            requested_pokemon="eevee",
            recommendation="accept",
            reasoning="Fair trade",
        )

        memory.record_feedback(rec_id, followed=True, feedback="Good advice!")

        recs = memory.get_past_recommendations()
        assert recs[0]["user_followed"] == 1
        assert recs[0]["user_feedback"] == "Good advice!"

    def test_get_past_recommendations(self):
        memory = RecommendationMemory("test_user")
        memory.save_recommendation("a", "b", "accept", "reason1")
        memory.save_recommendation("c", "d", "decline", "reason2")

        recs = memory.get_past_recommendations(limit=5)
        assert len(recs) == 2
