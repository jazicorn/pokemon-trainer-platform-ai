"""Tests for the end-to-end evaluation pipeline.

These tests verify that the eval loop (run_trade_eval → evaluate_single_trade →
evaluate_trade → scoring → compute_summary) is correctly wired together,
using a patched evaluate_trade to avoid live LLM calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from evals.cases import TRADE_CASES
from evals.eval_trade_advisor import (
    TradeEvalResult,
    compute_summary,
    evaluate_single_trade,
    run_trade_eval,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    case_id: str = "test_case",
    keyword_score: float = 1.0,
    recommendation_score: float = 1.0,
    latency_ms: float = 42.0,
    passed: bool = True,
    response: str = "accept this trade",
) -> TradeEvalResult:
    return TradeEvalResult(
        case_id=case_id,
        response=response,
        keyword_score=keyword_score,
        recommendation_score=recommendation_score,
        latency_ms=latency_ms,
        passed=passed,
    )


# ---------------------------------------------------------------------------
# TradeEvalResult unit tests
# ---------------------------------------------------------------------------


class TestTradeEvalResult:
    def test_combined_score_is_average_of_keyword_and_recommendation(self):
        result = _make_result(keyword_score=0.6, recommendation_score=0.8)
        assert result.combined_score == pytest.approx(0.7)

    def test_combined_score_both_zero(self):
        result = _make_result(keyword_score=0.0, recommendation_score=0.0)
        assert result.combined_score == pytest.approx(0.0)

    def test_combined_score_both_one(self):
        result = _make_result(keyword_score=1.0, recommendation_score=1.0)
        assert result.combined_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# evaluate_single_trade
# ---------------------------------------------------------------------------


class TestEvaluateSingleTrade:
    """evaluate_single_trade should score a mocked agent response correctly."""

    @pytest.mark.asyncio
    async def test_success_path_passes_with_matching_response(self):
        """A response containing expected keywords and positive sentiment passes."""
        # obvious_good_trade expects: accept, recommend, dragonite, valuable
        case = TRADE_CASES[0]  # obvious_good_trade, is_good_trade=True
        canned_response = "I recommend you accept this trade. Dragonite is extremely valuable compared to Geodude."

        with patch(
            "evals.eval_trade_advisor.evaluate_trade",
            new=AsyncMock(return_value=canned_response),
        ):
            result = await evaluate_single_trade(case)

        assert result.case_id == case.id
        assert result.keyword_score > 0.0
        assert result.recommendation_score == 1.0
        assert result.latency_ms > 0
        assert result.passed

    @pytest.mark.asyncio
    async def test_success_path_fails_with_wrong_sentiment(self):
        """A response with negative sentiment for a good trade does not pass."""
        case = TRADE_CASES[0]  # obvious_good_trade, is_good_trade=True
        wrong_response = "I would decline and not recommend this bad trade at all."

        with patch(
            "evals.eval_trade_advisor.evaluate_trade",
            new=AsyncMock(return_value=wrong_response),
        ):
            result = await evaluate_single_trade(case)

        # recommendation_score should be 0 (wrong direction)
        assert result.recommendation_score == 0.0

    @pytest.mark.asyncio
    async def test_exception_handling_yields_failed_result(self):
        """A RuntimeError from evaluate_trade produces a failed TradeEvalResult."""
        case = TRADE_CASES[1]  # obvious_bad_trade

        with patch(
            "evals.eval_trade_advisor.evaluate_trade",
            new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
        ):
            result = await evaluate_single_trade(case)

        assert result.passed is False
        assert result.response.startswith("Error:")
        assert "LLM unavailable" in result.response
        assert result.keyword_score == 0.0
        assert result.recommendation_score == 0.0
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_neutral_case_always_passes_recommendation(self):
        """Cases with is_good_trade=None always score 1.0 for recommendation."""
        case = TRADE_CASES[2]  # equal_value_trade, is_good_trade=None
        any_response = "These are similar Pokemon with equal value and preference matters."

        with patch(
            "evals.eval_trade_advisor.evaluate_trade",
            new=AsyncMock(return_value=any_response),
        ):
            result = await evaluate_single_trade(case)

        assert result.recommendation_score == 1.0


# ---------------------------------------------------------------------------
# run_trade_eval
# ---------------------------------------------------------------------------


class TestRunTradeEval:
    """run_trade_eval should iterate over all TRADE_CASES and return results."""

    @pytest.mark.asyncio
    async def test_returns_result_for_every_case(self):
        """One TradeEvalResult is returned per TRADE_CASE."""
        with patch(
            "evals.eval_trade_advisor.evaluate_trade",
            new=AsyncMock(return_value="accept this trade, recommend dragonite"),
        ):
            results = await run_trade_eval()

        assert len(results) == len(TRADE_CASES)
        assert all(isinstance(r, TradeEvalResult) for r in results)

    @pytest.mark.asyncio
    async def test_case_ids_match_trade_cases(self):
        """Returned result IDs match the original case IDs in order."""
        with patch(
            "evals.eval_trade_advisor.evaluate_trade",
            new=AsyncMock(return_value="accept the trade recommendation"),
        ):
            results = await run_trade_eval()

        result_ids = [r.case_id for r in results]
        expected_ids = [c.id for c in TRADE_CASES]
        assert result_ids == expected_ids

    @pytest.mark.asyncio
    async def test_exceptions_do_not_abort_loop(self):
        """If one case raises, the loop continues and returns results for all cases."""
        call_count = 0

        async def flaky(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Transient failure")
            return "accept this trade, recommend dragonite as valuable"

        with patch("evals.eval_trade_advisor.evaluate_trade", new=flaky):
            results = await run_trade_eval()

        assert len(results) == len(TRADE_CASES)
        # Second result should be the error case
        assert not results[1].passed
        assert results[1].response.startswith("Error:")


# ---------------------------------------------------------------------------
# compute_summary
# ---------------------------------------------------------------------------


class TestComputeSummary:
    def test_empty_list_returns_zeroes(self):
        stats = compute_summary([])
        assert stats == {"total": 0, "passed": 0, "pass_rate": 0.0}

    def test_all_passed(self):
        results = [
            _make_result(passed=True, keyword_score=0.8, recommendation_score=1.0, latency_ms=100.0) for _ in range(4)
        ]
        stats = compute_summary(results)
        assert stats["total"] == 4
        assert stats["passed"] == 4
        assert stats["pass_rate"] == pytest.approx(1.0)
        assert stats["avg_keyword"] == pytest.approx(0.8)
        assert stats["avg_recommendation"] == pytest.approx(1.0)
        assert stats["avg_latency_ms"] == pytest.approx(100.0)

    def test_none_passed(self):
        results = [_make_result(passed=False, keyword_score=0.0, recommendation_score=0.0) for _ in range(3)]
        stats = compute_summary(results)
        assert stats["passed"] == 0
        assert stats["pass_rate"] == pytest.approx(0.0)

    def test_partial_pass_rate(self):
        results = [
            _make_result(passed=True),
            _make_result(passed=False),
            _make_result(passed=True),
            _make_result(passed=False),
        ]
        stats = compute_summary(results)
        assert stats["pass_rate"] == pytest.approx(0.5)

    def test_average_latency_is_correct(self):
        results = [
            _make_result(latency_ms=100.0),
            _make_result(latency_ms=200.0),
            _make_result(latency_ms=300.0),
        ]
        stats = compute_summary(results)
        assert stats["avg_latency_ms"] == pytest.approx(200.0)
