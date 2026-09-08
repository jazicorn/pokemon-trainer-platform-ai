"""Tests for data models, generator, and loader."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from data.generator import (
    RARITY,
    generate_platform_trades,
    generate_user_collection,
)

from data import (
    PlatformTrades,
    Trade,
    TradeStatus,
    UserCollection,
    load_platform_trades,
    load_user_collection,
)


@pytest.fixture(autouse=True)
def no_platform_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force the JSON/mock path for all tests in this module.

    Patched at the source (data.platform_db) so that both loader.py and
    database.py — which each do ``from data.platform_db import get_platform_db``
    inside function bodies — see the mock.

    Also clears the lru_cache on load_platform_trades so a cached PG result
    from a previous test in the same process cannot bleed through.
    """
    monkeypatch.setattr("data.platform_db.get_platform_db", lambda: None)
    load_platform_trades.cache_clear()
    yield
    load_platform_trades.cache_clear()  # clean up after the test too


class TestPokemonRarity:
    """Tests for PokemonRarity data structure."""

    def test_legendary_is_frozenset(self):
        assert isinstance(RARITY.legendary, frozenset)

    def test_all_pokemon_returns_list(self):
        result = RARITY.all_pokemon
        assert isinstance(result, list)
        assert len(result) > 0

    def test_legendary_in_all_pokemon(self):
        all_pokemon = set(RARITY.all_pokemon)
        for pokemon in RARITY.legendary:
            assert pokemon in all_pokemon

    def test_trade_success_rate_legendary(self):
        statuses, weights = RARITY.get_trade_success_rate("mewtwo")
        assert "rejected" in statuses
        assert weights[statuses.index("rejected")] > weights[statuses.index("completed")]

    def test_trade_success_rate_common(self):
        statuses, weights = RARITY.get_trade_success_rate("pikachu")
        assert "completed" in statuses
        assert weights[statuses.index("completed")] > weights[statuses.index("rejected")]


class TestGeneratePlatformTrades:
    """Tests for platform trade generation."""

    def test_generates_correct_count(self):
        result = generate_platform_trades(num_trades=50)
        assert len(result["trades"]) == 50

    def test_trades_are_sorted_by_timestamp(self):
        result = generate_platform_trades(num_trades=100)
        timestamps = [t["timestamp"] for t in result["trades"]]
        assert timestamps == sorted(timestamps)

    def test_trade_has_required_fields(self):
        result = generate_platform_trades(num_trades=1)
        trade = result["trades"][0]
        assert "trade_id" in trade
        assert "timestamp" in trade
        assert "offered_pokemon" in trade
        assert "requested_pokemon" in trade
        assert "status" in trade
        assert "user_a_id" in trade
        assert "user_b_id" in trade

    def test_user_ids_are_different(self):
        result = generate_platform_trades(num_trades=100)
        for trade in result["trades"]:
            assert trade["user_a_id"] != trade["user_b_id"]


class TestGenerateUserCollection:
    """Tests for user collection generation."""

    def test_user_id_matches(self):
        result = generate_user_collection("test_user")
        assert result["user_id"] == "test_user"

    def test_has_pokemon(self):
        result = generate_user_collection()
        assert len(result["pokemon"]) >= 8
        assert len(result["pokemon"]) <= 15

    def test_has_preferences(self):
        result = generate_user_collection()
        prefs = result["preferences"]
        assert "favorite_types" in prefs
        assert "goal" in prefs
        assert "trading_style" in prefs
        assert "never_trade" in prefs
        assert "seeking" in prefs

    def test_seeking_not_in_owned(self):
        result = generate_user_collection()
        owned_ids = {p["pokemon_id"] for p in result["pokemon"]}
        seeking = set(result["preferences"]["seeking"])
        assert owned_ids.isdisjoint(seeking)


class TestDataLoader:
    """Tests for data loading functions."""

    data_dir: Path

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        """Generate test data before each test."""
        from data.generator import save_mock_data

        self.data_dir = tmp_path / "data"
        save_mock_data(self.data_dir)

    def test_load_platform_trades_returns_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("data.loader.get_data_dir", lambda: self.data_dir)
        result = load_platform_trades()
        assert isinstance(result, PlatformTrades)

    def test_load_user_collection_returns_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("data.loader.get_data_dir", lambda: self.data_dir)
        result = load_user_collection("user_001")
        assert isinstance(result, UserCollection)

    def test_load_user_collection_wrong_id_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("data.loader.get_data_dir", lambda: self.data_dir)
        with pytest.raises(ValueError, match="not found"):
            load_user_collection("nonexistent_user")


class TestPydanticModels:
    """Tests for Pydantic model validation."""

    def test_trade_status_enum(self):
        assert TradeStatus.COMPLETED.value == "completed"
        assert TradeStatus.REJECTED.value == "rejected"

    def test_trade_model_validates(self):
        trade = Trade(
            trade_id="t001",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            offered_pokemon="pikachu",
            requested_pokemon="eevee",
            status=TradeStatus.COMPLETED,
            user_a_id="user_001",
            user_b_id="user_002",
        )
        assert trade.trade_id == "t001"
        assert trade.status == TradeStatus.COMPLETED
