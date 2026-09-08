"""Tests for trade analytics."""

from datetime import datetime

import pytest

from agents.trade_analytics import (
    DEMAND_THRESHOLDS,
    TradeAnalytics,
)
from data.models import PlatformTrades, Trade, TradeStatus


@pytest.fixture
def sample_trades() -> PlatformTrades:
    """Create sample trade data."""
    trades = [
        Trade(
            trade_id="t001",
            timestamp=datetime.now(),
            offered_pokemon="pikachu",
            requested_pokemon="charizard",
            status=TradeStatus.COMPLETED,
            user_a_id="user_001",
            user_b_id="user_002",
        ),
        Trade(
            trade_id="t002",
            timestamp=datetime.now(),
            offered_pokemon="eevee",
            requested_pokemon="charizard",
            status=TradeStatus.REJECTED,
            user_a_id="user_003",
            user_b_id="user_004",
        ),
        Trade(
            trade_id="t003",
            timestamp=datetime.now(),
            offered_pokemon="charizard",
            requested_pokemon="mewtwo",
            status=TradeStatus.COMPLETED,
            user_a_id="user_005",
            user_b_id="user_006",
        ),
    ]
    return PlatformTrades(trades=trades)


class TestDemandThresholds:
    """Tests for demand classification."""

    def test_very_high_demand(self):
        assert DEMAND_THRESHOLDS.classify(3.5) == "very_high"

    def test_high_demand(self):
        assert DEMAND_THRESHOLDS.classify(2.0) == "high"

    def test_balanced_demand(self):
        assert DEMAND_THRESHOLDS.classify(1.0) == "balanced"

    def test_low_demand(self):
        assert DEMAND_THRESHOLDS.classify(0.5) == "low"

    def test_very_low_demand(self):
        assert DEMAND_THRESHOLDS.classify(0.2) == "very_low"


class TestTradeAnalytics:
    """Tests for TradeAnalytics."""

    def test_demand_ratio_high_demand(self, sample_trades: PlatformTrades):
        analytics = TradeAnalytics(trades=sample_trades)
        result = analytics.get_demand_ratio("charizard")

        assert result["times_requested"] == 2
        assert result["times_offered"] == 1
        assert result["demand_ratio"] == 2.0
        assert result["demand_level"] == "high"

    def test_demand_ratio_no_trades(self, sample_trades: PlatformTrades):
        analytics = TradeAnalytics(trades=sample_trades)
        result = analytics.get_demand_ratio("bulbasaur")

        assert result["times_requested"] == 0
        assert result["times_offered"] == 0
        assert result["demand_ratio"] == "∞"

    def test_trade_success_rate(self, sample_trades: PlatformTrades):
        analytics = TradeAnalytics(trades=sample_trades)
        result = analytics.get_trade_success_rate("charizard")

        assert result["total_trades"] == 3
        assert result["completed"] == 2
        assert result["success_rate"] == 66.7

    def test_trade_success_rate_no_trades(self, sample_trades: PlatformTrades):
        analytics = TradeAnalytics(trades=sample_trades)
        result = analytics.get_trade_success_rate("bulbasaur")

        assert result["total_trades"] == 0
        assert result["success_rate"] == 0.0

    def test_most_requested(self, sample_trades: PlatformTrades):
        analytics = TradeAnalytics(trades=sample_trades)
        result = analytics.get_most_requested(limit=5)

        assert len(result) > 0
        assert result[0]["pokemon"] == "charizard"
        assert result[0]["request_count"] == 2

    def test_compare_trade_value(self, sample_trades: PlatformTrades):
        analytics = TradeAnalytics(trades=sample_trades)
        result = analytics.compare_trade_value("charizard", "pikachu")

        assert "pokemon_a" in result
        assert "pokemon_b" in result
        assert "value_comparison" in result
        assert result["pokemon_a"]["name"] == "charizard"


class TestMarketAnalystAgent:
    """Tests for Market Analyst agent configuration."""

    def test_agent_has_system_prompt(self):
        from agents.trade_market_analyst import trade_market_analyst

        assert trade_market_analyst.system_prompt is not None

    def test_agent_model_configured(self):
        from agents.trade_market_analyst import trade_market_analyst

        assert trade_market_analyst.model is not None

    def test_market_dependencies_allows_none(self):
        from agents.trade_market_analyst import MarketDependencies

        deps = MarketDependencies(analytics=None)
        assert deps.analytics is None
