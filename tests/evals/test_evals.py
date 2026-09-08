"""Tests for evaluation framework."""

import pytest

from evals.cases import KNOWLEDGE_CASES, TRADE_CASES
from evals.scoring import ScoreResult, score_keywords, score_trade_recommendation


class TestEvalCases:
    """Tests for evaluation case definitions."""

    def test_trade_cases_not_empty(self):
        assert len(TRADE_CASES) > 0

    def test_trade_cases_are_hashable(self):
        """Frozen dataclasses are hashable."""
        case = TRADE_CASES[0]
        # Frozen dataclasses can be used in sets/dicts
        case_set = {case}
        assert case in case_set

    def test_trade_cases_have_required_fields(self):
        for case in TRADE_CASES:
            assert case.id
            assert case.offered
            assert case.requested
            assert case.expected_keywords

    def test_knowledge_cases_not_empty(self):
        assert len(KNOWLEDGE_CASES) > 0

    def test_knowledge_cases_have_required_fields(self):
        for case in KNOWLEDGE_CASES:
            assert case.id
            assert case.question
            assert case.expected_keywords
            assert case.pokemon


class TestScoreKeywords:
    """Tests for keyword scoring."""

    def test_all_keywords_present(self):
        response = "Charizard is a fire and flying type Pokemon"
        result = score_keywords(response, ("fire", "flying"))

        assert result.score == 1.0
        assert result.passed is True
        assert len(result.matched) == 2
        assert len(result.missing) == 0

    def test_some_keywords_missing(self):
        response = "Charizard is a fire type"
        result = score_keywords(response, ("fire", "flying", "dragon"))

        assert result.score == pytest.approx(1 / 3)
        assert result.passed is False
        assert "fire" in result.matched
        assert "flying" in result.missing

    def test_no_keywords_present(self):
        response = "Hello world"
        result = score_keywords(response, ("fire", "water"))

        assert result.score == 0.0
        assert result.passed is False

    def test_case_insensitive(self):
        response = "FIRE type FLYING"
        result = score_keywords(response, ("fire", "flying"))

        assert result.score == 1.0

    def test_custom_threshold(self):
        response = "fire type"
        result = score_keywords(response, ("fire", "flying"), threshold=0.25)

        assert result.passed is True  # 50% >= 25%


class TestScoreTradeRecommendation:
    """Tests for trade recommendation scoring."""

    def test_good_trade_positive_recommendation(self):
        response = "I recommend accepting this trade"
        result = score_trade_recommendation(response, is_good_trade=True)

        assert result.passed is True
        assert result.score == 1.0

    def test_good_trade_negative_recommendation(self):
        response = "I would decline this trade"
        result = score_trade_recommendation(response, is_good_trade=True)

        assert result.passed is False
        assert result.score == 0.0

    def test_bad_trade_negative_recommendation(self):
        response = "I would advise against this trade"
        result = score_trade_recommendation(response, is_good_trade=False)

        assert result.passed is True
        assert result.score == 1.0

    def test_bad_trade_positive_recommendation(self):
        response = "This is a good trade, accept it"
        result = score_trade_recommendation(response, is_good_trade=False)

        assert result.passed is False
        assert result.score == 0.0

    def test_neutral_trade_any_recommendation(self):
        result1 = score_trade_recommendation("accept", is_good_trade=None)
        result2 = score_trade_recommendation("decline", is_good_trade=None)

        assert result1.passed is True
        assert result2.passed is True


class TestScoreResult:
    """Tests for ScoreResult dataclass."""

    def test_match_rate_calculation(self):
        result = ScoreResult(
            score=0.5,
            passed=True,
            matched=("a", "b"),
            missing=("c", "d"),
        )

        assert result.match_rate == 0.5

    def test_match_rate_empty(self):
        result = ScoreResult(
            score=1.0,
            passed=True,
            matched=(),
            missing=(),
        )

        assert result.match_rate == 0.0
