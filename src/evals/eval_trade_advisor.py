"""Evaluate trade advisor recommendations."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from pydantic_evals import Dataset, Case
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from agents import evaluate_trade
from .cases import TRADE_CASES, TradeCase
from .scoring import score_keywords, score_trade_recommendation

# ---------------------------------------------------------------------------
# pydantic-evals: Inputs, Evaluators, Dataset
# ---------------------------------------------------------------------------

@dataclass
class TradeInputs:
    """Inputs for a trade evaluation case."""
    offered: str
    requested: str


_POSITIVE_INDICATORS: frozenset[str] = frozenset({
    "accept", "recommend", "good trade", "fair trade", "go for it",
})
_NEGATIVE_INDICATORS: frozenset[str] = frozenset({
    "decline", "against", "bad trade", "don't trade", "wouldn't recommend",
})


@dataclass
class KeywordEvaluator(Evaluator):
    """Score response based on presence of expected keywords."""
    keywords: tuple[str, ...]

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        response_lower = ctx.output.lower()
        matched = [kw for kw in self.keywords if kw.lower() in response_lower]
        score = len(matched) / len(self.keywords) if self.keywords else 1.0
        return {"keyword_score": score}


@dataclass
class RecommendationEvaluator(Evaluator):
    """Score whether the recommendation direction is correct."""
    is_good_trade: bool | None

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        if self.is_good_trade is None:
            return {"recommendation_score": 1.0}
        response_lower = ctx.output.lower()
        has_positive = any(ind in response_lower for ind in _POSITIVE_INDICATORS)
        has_negative = any(ind in response_lower for ind in _NEGATIVE_INDICATORS)
        if self.is_good_trade:
            correct = has_positive and not has_negative
        else:
            correct = has_negative and not has_positive
        return {"recommendation_score": 1.0 if correct else 0.0}


async def trade_task(inputs: TradeInputs) -> str:
    """Task function for pydantic-evals: runs the trade advisor."""
    return await evaluate_trade(inputs.offered, inputs.requested)


trade_dataset: Dataset[TradeInputs, str, None] = Dataset(
    cases=[
        Case(
            name=case.id,
            inputs=TradeInputs(case.offered, case.requested),
            evaluators=(
                KeywordEvaluator(case.expected_keywords),
                RecommendationEvaluator(case.is_good_trade),
            ),
        )
        for case in TRADE_CASES
    ]
)


@dataclass
class TradeEvalResult:
    """Result of a trade evaluation."""

    case_id: str
    response: str
    keyword_score: float
    recommendation_score: float
    latency_ms: float
    passed: bool

    @property
    def combined_score(self) -> float:
        return (self.keyword_score + self.recommendation_score) / 2


async def evaluate_single_trade(case: TradeCase) -> TradeEvalResult:
    """Evaluate a single trade case."""
    start = time.perf_counter()

    try:
        response = await evaluate_trade(case.offered, case.requested)
        latency = (time.perf_counter() - start) * 1000

        keyword_result = score_keywords(response, case.expected_keywords)
        rec_result = score_trade_recommendation(response, case.is_good_trade)

        return TradeEvalResult(
            case_id=case.id,
            response=response,
            keyword_score=keyword_result.score,
            recommendation_score=rec_result.score,
            latency_ms=latency,
            passed=keyword_result.passed and rec_result.passed,
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return TradeEvalResult(
            case_id=case.id,
            response=f"Error: {e}",
            keyword_score=0.0,
            recommendation_score=0.0,
            latency_ms=latency,
            passed=False,
        )


async def run_trade_eval() -> list[TradeEvalResult]:
    """Run all trade evaluation cases."""
    results = []

    for case in TRADE_CASES:
        print(f"Evaluating: {case.id} - {case.description}")
        result = await evaluate_single_trade(case)
        results.append(result)

        status = "✓" if result.passed else "✗"
        print(f"  {status} Keywords: {result.keyword_score:.0%}")
        print(f"  {status} Recommendation: {result.recommendation_score:.0%}")
        print(f"  Latency: {result.latency_ms:.0f}ms")
        print()

    return results


def compute_summary(results: list[TradeEvalResult]) -> dict[str, float]:
    """Compute summary statistics in single pass."""
    total = len(results)
    if total == 0:
        return {"total": 0, "passed": 0, "pass_rate": 0.0}

    passed = 0
    keyword_sum = 0.0
    rec_sum = 0.0
    latency_sum = 0.0

    for r in results:
        if r.passed:
            passed += 1
        keyword_sum += r.keyword_score
        rec_sum += r.recommendation_score
        latency_sum += r.latency_ms

    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total,
        "avg_keyword": keyword_sum / total,
        "avg_recommendation": rec_sum / total,
        "avg_latency_ms": latency_sum / total,
    }


def print_summary(results: list[TradeEvalResult]) -> None:
    """Print evaluation summary."""
    stats = compute_summary(results)

    print("=" * 50)
    print("TRADE ADVISOR EVALUATION SUMMARY")
    print("=" * 50)
    print(f"Total Cases: {stats['total']}")
    print(f"Passed: {stats['passed']}/{stats['total']} ({stats['pass_rate']:.0%})")
    print(f"Avg Keyword Score: {stats['avg_keyword']:.0%}")
    print(f"Avg Recommendation Score: {stats['avg_recommendation']:.0%}")
    print(f"Avg Latency: {stats['avg_latency_ms']:.0f}ms")


async def main() -> None:
    """Run trade advisor evaluation using pydantic-evals."""
    print("=" * 50)
    print("Trade Advisor Evaluation (pydantic-evals)")
    print("=" * 50 + "\n")

    report = await trade_dataset.evaluate(trade_task, name="trade_advisor")
    report.print(include_input=True)


if __name__ == "__main__":
    asyncio.run(main())
    