"""Tests for cross-instance SQLite memory persistence.

These tests verify that data written by one instance of a memory class
is correctly read by a brand-new instance pointed at the same database —
the fundamental guarantee of persistent storage.
"""

import pytest

from memory.database import init_database
from memory.conversation_memory import ConversationMemory, RecommendationMemory
from memory.user_preferences import UserPreferencesManager


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redirect all memory.database operations to a fresh temp file."""
    db_file = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory.database.get_db_path", lambda: db_file)
    init_database()
    return db_file


# ---------------------------------------------------------------------------
# ConversationMemory
# ---------------------------------------------------------------------------

class TestConversationPersistence:
    """ConversationMemory writes must survive creating a new instance."""

    def test_messages_persist_across_instances(self, isolated_db):
        """Messages written by instance A are readable by instance B."""
        instance_a = ConversationMemory("user_test")
        instance_a.add_message("user", "Hello, I want to trade my Pikachu.")
        instance_a.add_message("assistant", "I can help with that trade.")

        instance_b = ConversationMemory("user_test")
        history = instance_b.get_history()

        assert len(history) == 2
        contents = {h["content"] for h in history}
        assert "Hello, I want to trade my Pikachu." in contents
        assert "I can help with that trade." in contents

    def test_clear_on_one_instance_affects_new_instance(self, isolated_db):
        """Clearing history on instance A leaves nothing for instance B."""
        instance_a = ConversationMemory("user_clear_test")
        instance_a.add_message("user", "Some message")
        instance_a.clear()

        instance_b = ConversationMemory("user_clear_test")
        assert instance_b.get_history() == []

    def test_history_trim_respects_max_history(self, isolated_db):
        """Adding more messages than max_history keeps at most max_history rows."""
        instance_a = ConversationMemory("user_trim_test", max_history=10)
        for i in range(25):
            instance_a.add_message("user", f"Message {i}")

        instance_b = ConversationMemory("user_trim_test", max_history=10)
        history = instance_b.get_history()

        assert len(history) <= 10

    def test_different_users_are_isolated(self, isolated_db):
        """Messages for user A must not appear in user B's history."""
        ConversationMemory("user_alice").add_message("user", "Alice message")
        ConversationMemory("user_bob").add_message("user", "Bob message")

        alice_history = ConversationMemory("user_alice").get_history()
        bob_history = ConversationMemory("user_bob").get_history()

        assert all("Alice" in m["content"] for m in alice_history)
        assert all("Bob" in m["content"] for m in bob_history)

    def test_get_context_string_contains_persisted_messages(self, isolated_db):
        """get_context_string() works correctly with persisted messages."""
        instance_a = ConversationMemory("user_ctx_test")
        instance_a.add_message("user", "Trade Pikachu for Gengar?")
        instance_a.add_message("assistant", "That is a fair trade.")

        context = ConversationMemory("user_ctx_test").get_context_string(limit=5)
        assert "Trade Pikachu" in context
        assert "fair trade" in context


# ---------------------------------------------------------------------------
# UserPreferencesManager
# ---------------------------------------------------------------------------

class TestPreferencesPersistence:
    """UserPreferencesManager writes must survive creating a new instance."""

    def test_preferences_persist_across_instances(self, isolated_db):
        """Preferences saved by instance A are readable by instance B."""
        instance_a = UserPreferencesManager("user_prefs_test")
        instance_a.save_preferences(
            goal="Complete Dex",
            favorite_types=["fire", "dragon"],
            trading_style="aggressive",
        )

        instance_b = UserPreferencesManager("user_prefs_test")
        prefs = instance_b.get_preferences()

        assert prefs["goal"] == "Complete Dex"
        assert "fire" in prefs["favorite_types"]
        assert prefs["trading_style"] == "aggressive"

    def test_update_seeking_persists(self, isolated_db):
        """Adding a Pokemon to the seeking list persists to a new instance."""
        instance_a = UserPreferencesManager("user_seeking_test")
        instance_a.update_seeking("gengar", add=True)

        instance_b = UserPreferencesManager("user_seeking_test")
        prefs = instance_b.get_preferences()

        assert "gengar" in prefs["seeking"]

    def test_remove_from_seeking_persists(self, isolated_db):
        """Removing a Pokemon from seeking persists to a new instance."""
        instance_a = UserPreferencesManager("user_seeking_remove")
        instance_a.update_seeking("eevee", add=True)
        instance_a.update_seeking("eevee", add=False)

        instance_b = UserPreferencesManager("user_seeking_remove")
        prefs = instance_b.get_preferences()

        assert "eevee" not in prefs["seeking"]

    def test_update_never_trade_persists(self, isolated_db):
        """never_trade list updates are persisted across instances."""
        instance_a = UserPreferencesManager("user_never_test")
        instance_a.update_never_trade("mewtwo", add=True)

        instance_b = UserPreferencesManager("user_never_test")
        prefs = instance_b.get_preferences()

        assert "mewtwo" in prefs["never_trade"]

    def test_empty_preferences_for_unknown_user(self, isolated_db):
        """A brand-new user with no saved prefs returns an empty dict."""
        prefs = UserPreferencesManager("brand_new_user").get_preferences()
        assert prefs == {}


# ---------------------------------------------------------------------------
# RecommendationMemory
# ---------------------------------------------------------------------------

class TestRecommendationPersistence:
    """RecommendationMemory writes must survive creating a new instance."""

    def test_recommendation_persists_across_instances(self, isolated_db):
        """A recommendation saved by instance A is retrievable by instance B."""
        instance_a = RecommendationMemory("user_rec_test")
        instance_a.save_recommendation(
            offered_pokemon="pikachu",
            requested_pokemon="gengar",
            recommendation="accept",
            reasoning="Gengar has better competitive value.",
        )

        instance_b = RecommendationMemory("user_rec_test")
        recs = instance_b.get_past_recommendations()

        assert len(recs) == 1
        assert recs[0]["offered_pokemon"] == "pikachu"
        assert recs[0]["requested_pokemon"] == "gengar"

    def test_save_recommendation_returns_positive_id(self, isolated_db):
        """save_recommendation() returns a positive integer row ID."""
        mem = RecommendationMemory("user_id_test")
        rec_id = mem.save_recommendation(
            offered_pokemon="bulbasaur",
            requested_pokemon="charmander",
            recommendation="decline",
            reasoning="Unequal trade.",
        )
        assert isinstance(rec_id, int)
        assert rec_id > 0

    def test_feedback_recorded_and_visible_to_new_instance(self, isolated_db):
        """Feedback recorded by instance A is visible to instance B."""
        instance_a = RecommendationMemory("user_feedback_test")
        rec_id = instance_a.save_recommendation(
            offered_pokemon="squirtle",
            requested_pokemon="jigglypuff",
            recommendation="accept",
            reasoning="Good value.",
        )
        instance_a.record_feedback(rec_id, followed=True, feedback="Great advice!")

        instance_b = RecommendationMemory("user_feedback_test")
        recs = instance_b.get_past_recommendations()

        assert recs[0]["user_followed"] == 1
        assert recs[0]["user_feedback"] == "Great advice!"

    def test_multiple_recommendations_both_present(self, isolated_db):
        """get_past_recommendations returns all saved recommendations."""
        mem = RecommendationMemory("user_order_test")
        mem.save_recommendation("first", "mon_a", "accept", "Reason A")
        mem.save_recommendation("second", "mon_b", "decline", "Reason B")

        recs = RecommendationMemory("user_order_test").get_past_recommendations()

        assert len(recs) == 2
        offered = {r["offered_pokemon"] for r in recs}
        assert offered == {"first", "second"}
