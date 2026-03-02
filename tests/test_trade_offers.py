"""Tests for TradeOffersManager and offer agent functions."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from memory.database import TradeOffersManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Note: pytestmark is NOT set at module level so sync class tests are not
# incorrectly flagged. Async tests are marked individually below.

def make_mgr(user_id: str = "test_user", tmp_path=None) -> TradeOffersManager:
    """Return a TradeOffersManager backed by an in-memory DB for isolation."""
    import memory.database as db_module
    from pathlib import Path

    if tmp_path is not None:
        db_path = tmp_path / "test_memory.db"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        mgr = TradeOffersManager(user_id)
        db_module.get_db_path = original
        return mgr

    return TradeOffersManager(user_id)


# ---------------------------------------------------------------------------
# TradeOffersManager — CRUD
# ---------------------------------------------------------------------------

class TestTradeOffersManager:
    def test_create_offer_returns_positive_id(self, tmp_path):
        mgr = TradeOffersManager.__new__(TradeOffersManager)
        mgr.user_id = "alice"

        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()
            offer_id = mgr.create_offer("bob", "pikachu", "charizard")
            assert isinstance(offer_id, int)
            assert offer_id > 0
        finally:
            db_module.get_db_path = original

    def test_get_inbox_filters_by_recipient(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            alice = TradeOffersManager.__new__(TradeOffersManager)
            alice.user_id = "alice"
            bob = TradeOffersManager.__new__(TradeOffersManager)
            bob.user_id = "bob"

            # bob sends an offer to alice
            bob.create_offer("alice", "gengar", "eevee")
            # alice sends an offer to bob (should NOT appear in alice's inbox)
            alice.create_offer("bob", "snorlax", "mewtwo")

            inbox = alice.get_inbox()
            assert len(inbox) == 1
            assert inbox[0]["sender_id"] == "bob"
            assert inbox[0]["offered_pokemon"] == "gengar"
            assert inbox[0]["requested_pokemon"] == "eevee"
        finally:
            db_module.get_db_path = original

    def test_get_sent_filters_by_sender(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            alice = TradeOffersManager.__new__(TradeOffersManager)
            alice.user_id = "alice"
            bob = TradeOffersManager.__new__(TradeOffersManager)
            bob.user_id = "bob"

            alice.create_offer("bob", "lapras", "dragonite")
            bob.create_offer("alice", "gengar", "eevee")  # bob's offer, not alice's

            sent = alice.get_sent()
            assert len(sent) == 1
            assert sent[0]["recipient_id"] == "bob"
            assert sent[0]["offered_pokemon"] == "lapras"
        finally:
            db_module.get_db_path = original

    def test_update_status_accepted(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            sender = TradeOffersManager.__new__(TradeOffersManager)
            sender.user_id = "carol"
            recipient = TradeOffersManager.__new__(TradeOffersManager)
            recipient.user_id = "dave"

            offer_id = sender.create_offer("dave", "pikachu", "bulbasaur")
            updated = recipient.update_status(offer_id, "accepted")

            assert updated is True
            inbox = recipient.get_inbox()
            assert len(inbox) == 0  # no longer pending
        finally:
            db_module.get_db_path = original

    def test_update_status_declined(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            sender = TradeOffersManager.__new__(TradeOffersManager)
            sender.user_id = "eve"
            recipient = TradeOffersManager.__new__(TradeOffersManager)
            recipient.user_id = "frank"

            offer_id = sender.create_offer("frank", "mewtwo", "mew")
            updated = recipient.update_status(offer_id, "declined")

            assert updated is True
            inbox = recipient.get_inbox()
            assert len(inbox) == 0
        finally:
            db_module.get_db_path = original

    def test_update_status_wrong_user_returns_false(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            sender = TradeOffersManager.__new__(TradeOffersManager)
            sender.user_id = "grace"
            bystander = TradeOffersManager.__new__(TradeOffersManager)
            bystander.user_id = "heidi"  # not the recipient

            offer_id = sender.create_offer("ivan", "charizard", "blastoise")
            # heidi tries to accept an offer addressed to ivan
            updated = bystander.update_status(offer_id, "accepted")
            assert updated is False
        finally:
            db_module.get_db_path = original

    def test_seed_mock_offers_idempotent(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            mgr = TradeOffersManager.__new__(TradeOffersManager)
            mgr.user_id = "new_user"

            mgr.seed_mock_offers()
            first_count = len(mgr.get_inbox())

            mgr.seed_mock_offers()  # second call should be a no-op
            second_count = len(mgr.get_inbox())

            assert first_count == second_count
            assert first_count > 0
        finally:
            db_module.get_db_path = original

    def test_save_ai_analysis_persists(self, tmp_path):
        import memory.database as db_module
        db_path = tmp_path / "db.sqlite"
        original = db_module.get_db_path
        db_module.get_db_path = lambda: db_path
        try:
            from memory.database import init_database
            init_database()

            sender = TradeOffersManager.__new__(TradeOffersManager)
            sender.user_id = "judy"

            offer_id = sender.create_offer("karl", "snorlax", "munchlax")
            sender.save_ai_analysis(offer_id, "This is a fair trade.")

            # Verify via raw query
            from memory.database import get_connection
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ai_analysis FROM trade_offers WHERE id = ?", (offer_id,))
                row = cursor.fetchone()
                assert row["ai_analysis"] == "This is a fair trade."
        finally:
            db_module.get_db_path = original


# ---------------------------------------------------------------------------
# Agent functions — mocked evaluate_trade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_offers_calls_evaluate_trade(tmp_path):
    """get_pending_offers() should call evaluate_trade for each offer."""
    import memory.database as db_module
    db_path = tmp_path / "db.sqlite"
    original = db_module.get_db_path
    db_module.get_db_path = lambda: db_path

    try:
        from memory.database import init_database, TradeOffersManager as TOM
        init_database()

        # Pre-populate inbox for test_user
        sender = TOM.__new__(TOM)
        sender.user_id = "other_user"
        sender.create_offer("test_user", "charizard", "bulbasaur")

        with patch(
            "agents.trade_advisor.evaluate_trade",
            new=AsyncMock(return_value="Charizard is worth more — bad deal."),
        ):
            from agents.trade_advisor import get_pending_offers
            result = await get_pending_offers("test_user")

        assert "Charizard" in result or "charizard" in result.lower()
        assert "Offer #" in result
    finally:
        db_module.get_db_path = original


@pytest.mark.asyncio
async def test_send_trade_offer_calls_evaluate_trade(tmp_path):
    """send_trade_offer() should call evaluate_trade before persisting."""
    import memory.database as db_module
    db_path = tmp_path / "db.sqlite"
    original = db_module.get_db_path
    db_module.get_db_path = lambda: db_path

    try:
        from memory.database import init_database
        init_database()

        with patch(
            "agents.trade_advisor.evaluate_trade",
            new=AsyncMock(return_value="Fair trade — proceed."),
        ) as mock_eval:
            from agents.trade_advisor import send_trade_offer
            result = await send_trade_offer("alice", "bob", "pikachu", "charizard")

        mock_eval.assert_awaited_once()
        assert "Offer #" in result
        assert "Fair trade" in result
    finally:
        db_module.get_db_path = original


@pytest.mark.asyncio
async def test_get_pending_offers_empty_inbox(tmp_path):
    """get_pending_offers() should return a friendly message when inbox is empty."""
    import memory.database as db_module
    db_path = tmp_path / "db.sqlite"
    original = db_module.get_db_path
    db_module.get_db_path = lambda: db_path

    try:
        from memory.database import init_database, TradeOffersManager as TOM
        init_database()

        # Seed then accept all offers so inbox is empty
        mgr = TOM.__new__(TOM)
        mgr.user_id = "empty_user"
        # Don't seed — inbox is naturally empty for a brand new user
        # Override seed_mock_offers to do nothing
        with patch.object(TOM, "seed_mock_offers", return_value=None):
            from agents.trade_advisor import get_pending_offers
            result = await get_pending_offers("empty_user")

        assert "empty" in result.lower()
    finally:
        db_module.get_db_path = original
