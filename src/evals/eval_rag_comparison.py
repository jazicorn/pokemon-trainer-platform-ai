"""Evaluate RAG vs no-RAG accuracy using pydantic-evals.

Runs the same knowledge questions through two tasks:
  - rag_task: uses the RAG-enabled Pokedex expert (query_pokedex)
  - no_rag_task: uses a plain Claude agent with no retrieval

Prints a side-by-side comparison report showing the keyword_score improvement
from RAG, demonstrating measurable benefit over a simpler baseline.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from agents import query_pokedex
from config import config

from .cases import KNOWLEDGE_CASES


@dataclass
class KnowledgeInputs:
    """Inputs for a Pokemon knowledge evaluation case."""

    question: str


@dataclass
class KeywordEvaluator(Evaluator):
    """Score response based on presence of expected keywords."""

    keywords: tuple[str, ...]

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        response_lower = ctx.output.lower()
        matched = [kw for kw in self.keywords if kw.lower() in response_lower]
        score = len(matched) / len(self.keywords) if self.keywords else 1.0
        return {"keyword_score": score}


# Plain agent without RAG — used as baseline
_no_rag_agent = Agent(
    config.model_id,
    system_prompt="You are a Pokemon expert. Answer questions about Pokemon.",
)


async def rag_task(inputs: KnowledgeInputs) -> str:
    """Task using RAG-enabled Pokedex expert."""
    return await query_pokedex(inputs.question)


async def no_rag_task(inputs: KnowledgeInputs) -> str:
    """Task using a plain agent with no retrieval."""
    result = await _no_rag_agent.run(inputs.question)
    return result.output


knowledge_dataset: Dataset[KnowledgeInputs, str, None] = Dataset(
    cases=[
        Case(
            name=case.id,
            inputs=KnowledgeInputs(case.question),
            evaluators=(KeywordEvaluator(case.expected_keywords),),
        )
        for case in KNOWLEDGE_CASES
    ]
)


async def main() -> None:
    """Run RAG vs no-RAG comparison using pydantic-evals."""
    print("=" * 50)
    print("RAG vs No-RAG Comparison (pydantic-evals)")
    print("=" * 50 + "\n")

    print("Running baseline (no RAG)...")
    baseline = await knowledge_dataset.evaluate(no_rag_task, name="no_rag_baseline")

    print("\nRunning RAG-enabled Pokedex expert...")
    rag_report = await knowledge_dataset.evaluate(rag_task, name="rag_pokedex")

    print("\n--- RAG Report (with no-RAG baseline for comparison) ---")
    rag_report.print(baseline=baseline, include_input=True)


if __name__ == "__main__":
    asyncio.run(main())
