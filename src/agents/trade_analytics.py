"""Trade analytics functions for market analysis with forecasting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.models import PlatformTrades, Trade

from data import load_platform_trades
from data.models import TradeStatus


@dataclass(frozen=True)
class DemandThresholds:
    """Thresholds for demand classification."""

    very_high: float = 3.0
    high: float = 1.5
    balanced: float = 0.8
    low: float = 0.4

    def classify(self, ratio: float) -> str:
        """Classify demand level based on ratio."""
        if ratio >= self.very_high:
            return "very_high"
        if ratio >= self.high:
            return "high"
        if ratio >= self.balanced:
            return "balanced"
        if ratio >= self.low:
            return "low"
        return "very_low"


DEMAND_THRESHOLDS = DemandThresholds()


class TradeAnalytics:
    """Analyze platform trade data with forecasting capabilities."""

    def __init__(self, trades: PlatformTrades | None = None):
        """Initialize with trade data."""
        self.trades = trades or load_platform_trades()
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build indexes for O(1) lookups."""
        self._requested_counts: Counter[str] = Counter()
        self._offered_counts: Counter[str] = Counter()
        self._trades_by_pokemon: dict[str, list[Trade]] = {}

        for trade in self.trades.trades:
            req = trade.requested_pokemon.lower()
            off = trade.offered_pokemon.lower()

            self._requested_counts[req] += 1
            self._offered_counts[off] += 1

            self._trades_by_pokemon.setdefault(req, []).append(trade)
            self._trades_by_pokemon.setdefault(off, []).append(trade)

    def get_demand_ratio(self, pokemon: str, days: int | None = None) -> dict:
        """Calculate demand ratio, optionally filtered by recent days."""
        name = pokemon.lower()
        
        if days:
            cutoff = datetime.now() - timedelta(days=days)
            trades = [t for t in self._trades_by_pokemon.get(name, []) 
                     if self._parse_timestamp(t.timestamp) > cutoff]
            requested = sum(1 for t in trades if t.requested_pokemon.lower() == name)
            offered = sum(1 for t in trades if t.offered_pokemon.lower() == name)
        else:
            requested = self._requested_counts[name]
            offered = self._offered_counts[name]

        ratio = requested / offered if offered > 0 else float("inf")

        return {
            "pokemon": pokemon,
            "times_requested": requested,
            "times_offered": offered,
            "demand_ratio": round(ratio, 2) if ratio != float("inf") else "∞",
            "demand_level": DEMAND_THRESHOLDS.classify(ratio),
        }

    def get_market_forecast(self, pokemon: str) -> dict:
        """
        Forecast market direction by comparing 7-day vs 30-day momentum.
        """
        short_term = self.get_demand_ratio(pokemon, days=7)
        long_term = self.get_demand_ratio(pokemon, days=30)

        st_ratio = self._to_float(short_term["demand_ratio"])
        lt_ratio = self._to_float(long_term["demand_ratio"])

        # Calculate momentum (percentage change)
        if lt_ratio == 0 or lt_ratio == float("inf"):
            momentum = 0.0
        else:
            momentum = round(((st_ratio - lt_ratio) / lt_ratio) * 100, 1)

        # Determine sentiment
        if momentum > 15:
            sentiment = "Bullish (Rapidly Rising)"
        elif momentum < -15:
            sentiment = "Bearish (Declining)"
        else:
            sentiment = "Stable"

        return {
            "pokemon": pokemon,
            "momentum_score": momentum,
            "sentiment": sentiment,
            "short_term_ratio": short_term["demand_ratio"],
            "long_term_ratio": long_term["demand_ratio"],
            "recommendation": "Hold/Buy" if sentiment == "Bullish" else "Sell/Trade Away" if sentiment == "Bearish" else "Neutral"
        }

    def get_trade_success_rate(self, pokemon: str) -> dict:
        """Calculate trade success rate for a Pokemon."""
        name = pokemon.lower()
        relevant_trades = self._trades_by_pokemon.get(name, [])

        if not relevant_trades:
            return {
                "pokemon": pokemon,
                "total_trades": 0,
                "completed": 0,
                "success_rate": 0.0,
            }

        completed = sum(1 for t in relevant_trades if t.status == TradeStatus.COMPLETED)

        return {
            "pokemon": pokemon,
            "total_trades": len(relevant_trades),
            "completed": completed,
            "success_rate": round(completed / len(relevant_trades) * 100, 1),
        }

    def get_trending_pokemon(self, days: int = 30, limit: int = 10) -> list[dict]:
        """Get Pokemon with most trade activity recently."""
        cutoff = datetime.now() - timedelta(days=days)

        pokemon_counts: Counter[str] = Counter()
        for trade in self.trades.trades:
            trade_time = self._parse_timestamp(trade.timestamp)
            if trade_time > cutoff:
                pokemon_counts[trade.offered_pokemon] += 1
                pokemon_counts[trade.requested_pokemon] += 1

        return [
            {
                "pokemon": pokemon,
                "trade_mentions": count,
                **self._get_demand_summary(pokemon),
            }
            for pokemon, count in pokemon_counts.most_common(limit)
        ]

    def _parse_timestamp(self, timestamp: datetime) -> datetime:
        """Parse timestamp to naive datetime."""
        return timestamp.replace(tzinfo=None)

    def _get_demand_summary(self, pokemon: str) -> dict:
        """Get demand ratio and level for a Pokemon."""
        demand = self.get_demand_ratio(pokemon)
        return {
            "demand_ratio": demand["demand_ratio"],
            "demand_level": demand["demand_level"],
        }

    def get_most_requested(self, limit: int = 10) -> list[dict]:
        """Get most frequently requested Pokemon."""
        return [{"pokemon": p, "request_count": c} for p, c in self._requested_counts.most_common(limit)]

    def get_most_offered(self, limit: int = 10) -> list[dict]:
        """Get most frequently offered Pokemon."""
        return [{"pokemon": p, "offer_count": c} for p, c in self._offered_counts.most_common(limit)]

    def compare_trade_value(self, pokemon_a: str, pokemon_b: str) -> dict:
        """Compare relative trade value of two Pokemon."""
        demand_a = self.get_demand_ratio(pokemon_a)
        demand_b = self.get_demand_ratio(pokemon_b)
        success_a = self.get_trade_success_rate(pokemon_a)
        success_b = self.get_trade_success_rate(pokemon_b)

        ratio_a = self._to_float(demand_a["demand_ratio"])
        ratio_b = self._to_float(demand_b["demand_ratio"])

        value_comparison = self._compare_values(pokemon_a, pokemon_b, ratio_a, ratio_b)

        return {
            "pokemon_a": {
                "name": pokemon_a,
                "demand_ratio": demand_a["demand_ratio"],
                "demand_level": demand_a["demand_level"],
                "success_rate": success_a["success_rate"],
            },
            "pokemon_b": {
                "name": pokemon_b,
                "demand_ratio": demand_b["demand_ratio"],
                "demand_level": demand_b["demand_level"],
                "success_rate": success_b["success_rate"],
            },
            "value_comparison": value_comparison,
        }

    def _to_float(self, value: float | str) -> float:
        """Convert demand ratio to float."""
        return float("inf") if value == "∞" else float(value)

    def _compare_values(self, name_a: str, name_b: str, ratio_a: float, ratio_b: float) -> str:
        """Compare two demand ratios."""
        threshold = 1.2
        if ratio_a > ratio_b * threshold:
            return f"{name_a} is more valuable"
        if ratio_b > ratio_a * threshold:
            return f"{name_b} is more valuable"
        return "approximately equal value"
    