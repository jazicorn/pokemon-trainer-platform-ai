"""Scoring utilities for evaluations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreResult:
    """Result of scoring a response."""

    score: float
    passed: bool
    matched: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def match_rate(self) -> float:
        """Calculate keyword match rate."""
        total = len(self.matched) + len(self.missing)
        return len(self.matched) / total if total > 0 else 0.0


def score_keywords(
    response: str,
    expected: tuple[str, ...],
    threshold: float = 0.5,
) -> ScoreResult:
    """Score response based on keyword presence.

    Args:
        response: The response text to score.
        expected: Keywords that should be present.
        threshold: Minimum match rate to pass.

    Returns:
        ScoreResult with score and details.
    """
    if not expected:
        return ScoreResult(score=1.0, passed=True, matched=(), missing=())

    response_lower = response.lower()

    # Single pass: partition into matched/missing
    matched: list[str] = []
    missing: list[str] = []
    for kw in expected:
        if kw.lower() in response_lower:
            matched.append(kw)
        else:
            missing.append(kw)

    match_rate = len(matched) / len(expected)

    return ScoreResult(
        score=match_rate,
        passed=match_rate >= threshold,
        matched=tuple(matched),
        missing=tuple(missing),
    )


# Pre-compiled indicator sets for O(1) lookup
_POSITIVE_INDICATORS: frozenset[str] = frozenset({
    "accept", "recommend", "good trade", "fair trade", "go for it",
})
_NEGATIVE_INDICATORS: frozenset[str] = frozenset({
    "decline", "against", "bad trade", "don't trade", "wouldn't recommend",
})


def score_trade_recommendation(
    response: str,
    is_good_trade: bool | None,
) -> ScoreResult:
    """Score a trade recommendation for correctness.

    Args:
        response: The recommendation response.
        is_good_trade: Whether the trade should be recommended.

    Returns:
        ScoreResult based on recommendation alignment.
    """
    if is_good_trade is None:
        return ScoreResult(
            score=1.0,
            passed=True,
            matched=("neutral_case",),
            missing=(),
        )

    response_lower = response.lower()

    # Check indicators in single pass through response
    has_positive = any(ind in response_lower for ind in _POSITIVE_INDICATORS)
    has_negative = any(ind in response_lower for ind in _NEGATIVE_INDICATORS)

    if is_good_trade:
        correct = has_positive and not has_negative
        label = "positive_recommendation"
    else:
        correct = has_negative and not has_positive
        label = "negative_recommendation"

    return ScoreResult(
        score=1.0 if correct else 0.0,
        passed=correct,
        matched=(label,) if correct else (),
        missing=() if correct else (label,),
    )
