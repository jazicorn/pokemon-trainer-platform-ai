# Phase 13: Evaluations

## Overview

Phase 13 measures the system's quality using a structured eval framework — running fixed test cases
against the live agents and scoring their outputs. Two evaluations are implemented:

1. **Trade Advisor eval**: Runs each entry in `TRADE_CASES` through the Trade Advisor agent and
   scores the response for keyword presence and recommendation direction (approve vs. reject).
2. **RAG comparison eval**: Runs each entry in `KNOWLEDGE_CASES` through both the RAG-enabled
   Pokedex Expert and a plain baseline agent, then compares accuracy scores side-by-side.

The evals can be run as scripts against a live LLM or exercised fully offline through unit tests
that mock `evaluate_trade` with `AsyncMock`. This separation is the key design decision: the eval
pipeline logic is tested independently of model quality.

## Where It Fits

```text
Phase 5: Pokedex Expert   ─┐  (RAG accuracy is measured here)
Phase 9: Trade Advisor    ─┤  (trade recommendations are scored here)
Phase 10: Multi-Agent     ─┘  (what gets compared against a single-agent baseline)
        ↓
Phase 13: Evaluations
```

## Key Files

- `src/evals/cases.py` — Defines `TradeCase` and `KnowledgeCase` frozen dataclasses, and the
  `TRADE_CASES` and `KNOWLEDGE_CASES` tuples that serve as ground truth. Four trade cases and four
  knowledge cases are currently defined.
- `src/evals/scoring.py` — `score_keywords()` (keyword match rate with configurable threshold),
  `score_trade_recommendation()` (approve/reject direction check using pre-compiled `frozenset`
  indicator sets), `ScoreResult` (holds `score`, `passed`, `matched`, `missing`).
- `src/evals/eval_trade_advisor.py` — Two layers:
  - *pydantic-evals layer* (new): `TradeInputs` dataclass, `KeywordEvaluator` and
    `RecommendationEvaluator` as `Evaluator` subclasses, `trade_dataset` (`Dataset` of 4 cases),
    `trade_task` async function. `main()` runs `trade_dataset.evaluate(trade_task)` and prints the
    pydantic-evals report table.
  - *legacy layer* (kept for tests): `TradeEvalResult`, `evaluate_single_trade()`,
    `run_trade_eval()`, `compute_summary()`, `print_summary()`. These are still imported by
    `test_evals_execution.py` and remain fully functional.
- `src/evals/eval_rag_comparison.py` — Fully rewritten to use pydantic-evals. `KnowledgeInputs`
  dataclass, `KeywordEvaluator`, `rag_task` (calls `query_pokedex`), `no_rag_task` (calls a plain
  `Agent` with no tools), `knowledge_dataset`. `main()` runs both tasks and calls
  `rag_report.print(baseline=baseline)` to produce a side-by-side diff table.
- `src/evals/__init__.py` — Re-exports the public types and scoring functions from `cases` and
  `scoring`.
- `docs/eval_results/README.md` — Captured output from live eval runs with analysis notes.
- `tests/test_evals.py` — Unit tests for case definitions and scoring functions. No LLM calls.
- `tests/test_evals_execution.py` — Pipeline integration tests using `AsyncMock` to patch
  `evaluate_trade`. No LLM calls.

## Key Concepts

**pydantic-evals: task + evaluators + dataset**: The library's three-part model maps cleanly onto
the eval structure. The *task* is the async function under test (e.g., `trade_task`). The
*evaluators* are `@dataclass` subclasses of `Evaluator` that implement `evaluate(ctx)` and return a
`dict[str, float]` of named scores. The *dataset* is a `Dataset` of `Case` objects, each with
typed `inputs`, an optional `expected_output`, and per-case `evaluators`. Calling
`dataset.evaluate(task)` runs all cases concurrently, times each, and returns an `EvaluationReport`.

**Per-case evaluators vs. dataset-level evaluators**: `Case(evaluators=(...))` attaches evaluators
to a single case — useful when each case has different keywords or a different `is_good_trade`
value. `Dataset(evaluators=[...])` attaches evaluators that run on every case — useful for
checks that apply universally (e.g., max latency). The trade eval uses per-case evaluators;
the RAG eval attaches `KeywordEvaluator` per case since each question has different expected words.

**`report.print(baseline=baseline_report)`**: Passing a previously-run report as `baseline` tells
pydantic-evals to render a diff table — each cell shows the new score, the delta, and the
percentage change. This is how `eval_rag_comparison.py` surfaces the RAG improvement (+15.8% avg
keyword accuracy in the captured run).

**Frozen dataclasses as ground truth**: `TradeCase` and `KnowledgeCase` use
`@dataclass(frozen=True)`, making them immutable and hashable. This means they can safely be used in
sets or as dict keys — the `test_trade_cases_are_hashable` test verifies this property directly.

**`is_good_trade: bool | None`**: The three-valued field is important. `True` means the advisor
should approve; `False` means it should decline; `None` means the outcome is genuinely ambiguous
(equal-value trades like alakazam for gengar). `RecommendationEvaluator` returns a perfect score of
`1.0` for any response when `is_good_trade=None`, so ambiguous cases never penalize the model.

**Legacy layer kept for tests**: `eval_trade_advisor.py` still contains `TradeEvalResult`,
`evaluate_single_trade()`, `run_trade_eval()`, and `compute_summary()`. These are not used by
`main()` anymore but remain because `test_evals_execution.py` imports and tests them directly.
Removing them would break 15 unit tests.

**Pre-compiled indicator frozensets**: `_POSITIVE_INDICATORS` and `_NEGATIVE_INDICATORS` in both
`scoring.py` and `eval_trade_advisor.py` are module-level `frozenset` constants. This gives O(1)
membership lookup and avoids recompiling on every call. The indicators are phrase-level (e.g.,
`"good trade"`, `"wouldn't recommend"`), not single words, so the scorer can distinguish nuanced
language.

**Mocking strategy in `test_evals_execution.py`**: Tests patch
`evals.eval_trade_advisor.evaluate_trade` (the name as imported in that module, not the original
source location) using `unittest.mock.AsyncMock`. This exercises the full legacy pipeline without a
live API key. The pydantic-evals layer (`trade_dataset`, `trade_task`) is not covered by these
mocked tests — it is exercised by running `main()` against a live LLM.

## Exploring the Code

Start in `cases.py`. Read the four `TRADE_CASES` entries and notice the range of scenarios: an
obvious good trade, an obvious bad trade, an equal-value trade (`is_good_trade=None`), and an
aspirational legendary request. The `expected_keywords` tuple tells you what concepts the agent must
mention — these are the vocabulary of a sound trade recommendation, not just Pokemon names.

In `scoring.py`, read `score_keywords()`. Note that it does a single pass over `expected` and
partitions into `matched`/`missing`, then computes `match_rate` directly from `len(matched) /
len(expected)` — not from `ScoreResult.match_rate` (which divides by `matched + missing`). The two
calculations are equivalent but `ScoreResult.match_rate` is exposed as a convenience property for
callers. Then read `score_trade_recommendation()` — trace through the `is_good_trade=True` branch to
understand what `correct` means: the response must contain a positive indicator AND not contain a
negative one.

In `eval_trade_advisor.py`, read `evaluate_single_trade()` in full. Notice that
`time.perf_counter()` is called before the `try` block so latency is recorded even when an exception
occurs. Then read `compute_summary()` — it accumulates all stats in a single `for` loop (no list
comprehensions, no multiple passes) and returns a plain dict.

In `test_evals_execution.py`, read
`TestEvaluateSingleTrade.test_success_path_passes_with_matching_response`. The canned response is
crafted to contain words from `TRADE_CASES[0].expected_keywords` ("recommend", "accept",
"dragonite", "valuable") and a positive indicator ("recommend"), so both scores should be non-zero
and the result should pass.

## Running the Code

```bash
# Run the trade advisor evaluation (requires API key — makes live LLM calls)
op run --env-file .env.op -- uv run python -c "
import sys; sys.path.insert(0, 'src')
import asyncio
from evals.eval_trade_advisor import main
asyncio.run(main())
"

# Run the RAG comparison evaluation (requires API key + ChromaDB running)
op run --env-file .env.op -- uv run python -c "
import sys; sys.path.insert(0, 'src')
import asyncio
from evals.eval_rag_comparison import main
asyncio.run(main())
"
```

Expected output for the trade advisor eval (pydantic-evals table format):

```text
==================================================
Trade Advisor Evaluation (pydantic-evals)
==================================================

                   Evaluation Summary: trade_advisor
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Case ID            ┃ Scores               ┃ Duration ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ obvious_good_trade │ keyword_score: 0.750 │    60.0s │
│                    │ recommendation: 1.00 │          │
├────────────────────┼──────────────────────┼──────────┤
│ obvious_bad_trade  │ keyword_score: 0.500 │    57.2s │
│                    │ recommendation: 0.00 │          │
├────────────────────┼──────────────────────┼──────────┤
│ equal_value_trade  │ keyword_score: 0.250 │    54.2s │
│                    │ recommendation: 1.00 │          │
├────────────────────┼──────────────────────┼──────────┤
│ legendary_request  │ keyword_score: 0.500 │    49.8s │
│                    │ recommendation: 0.00 │          │
├────────────────────┼──────────────────────┼──────────┤
│ Averages           │ keyword_score: 0.500 │    55.3s │
│                    │ recommendation: 0.500│          │
└────────────────────┴──────────────────────┴──────────┘
```

Expected output for the RAG comparison eval (diff table showing improvement over baseline):

```text
==================================================
RAG vs No-RAG Comparison (pydantic-evals)
==================================================

              Evaluation Diff: no_rag_baseline → rag_pokedex
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Case ID           ┃ Scores                          ┃ Duration         ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ pikachu_evolution │ keyword_score: 0.500 → 1.00     │  1.9s → 8.3s     │
│                   │ (+0.5 / +100%)                  │                  │
├───────────────────┼─────────────────────────────────┼──────────────────┤
│ Averages          │ keyword_score: 0.792 → 0.917    │  3.1s → 9.5s     │
│                   │ (+0.125 / +15.8%)               │                  │
└───────────────────┴─────────────────────────────────┴──────────────────┘
```

See `docs/eval_results/README.md` for full captured output with analysis.

## Running the Tests

```bash
# Scoring and case structure unit tests (no LLM calls, no API key needed)
uv run pytest tests/test_evals.py -v

# Pipeline integration tests with mocked LLM (no API key needed)
uv run pytest tests/test_evals_execution.py -v

# Run both together
uv run pytest tests/test_evals.py tests/test_evals_execution.py -v
```

### `test_evals.py` covers

- `TestEvalCases` — `TRADE_CASES` and `KNOWLEDGE_CASES` are non-empty, hashable (frozen dataclass
  property), and have all required fields populated.
- `TestScoreKeywords` — full match (score 1.0, passed), partial match (score 1/3, failed), no match
  (score 0.0), case-insensitive matching, custom threshold override.
- `TestScoreTradeRecommendation` — positive response for good trade passes; negative response for
  good trade fails; negative response for bad trade passes; positive response for bad trade fails;
  `None` is_good_trade always passes regardless of response content.
- `TestScoreResult` — `match_rate` property computes `matched / (matched + missing)`; empty
  matched/missing returns 0.0.

### `test_evals_execution.py` covers

- `TestTradeEvalResult` — `combined_score` is the arithmetic mean of `keyword_score` and
  `recommendation_score`; verified for (0.6, 0.8), (0.0, 0.0), and (1.0, 1.0).
- `TestEvaluateSingleTrade` — success path with a matching canned response passes; wrong-sentiment
  response yields `recommendation_score == 0.0`; `RuntimeError` from the mock produces a failed
  result with `response.startswith("Error:")` and zero scores; neutral (`is_good_trade=None`) always
  yields `recommendation_score == 1.0`.
- `TestRunTradeEval` — returns exactly `len(TRADE_CASES)` results; result `case_id` values match
  case order; a flaky mock that raises on call 2 still returns results for all cases (loop does not
  abort).
- `TestComputeSummary` — empty list returns zero dict; all-passed and all-failed cases; partial pass
  rate (0.5); average latency is correct.

## Common Gotchas

**Module path matters for patching**: `test_evals_execution.py` patches
`evals.eval_trade_advisor.evaluate_trade`, not `agents.evaluate_trade`. If you add a new test that
patches the wrong module path, the real `evaluate_trade` runs and you get a live LLM call (or a
missing API key error).

**ChromaDB required for RAG comparison eval**: `eval_rag_comparison.py` calls `query_pokedex()`,
which opens a `PokemonVectorStore` (ChromaDB client). If ChromaDB is not running, the eval fails at
the first case. Start ChromaDB first or use the trade advisor eval only.

**`is_good_trade=None` is not a bug**: The `equal_value_trade` case intentionally sets
`is_good_trade=None`. This means `score_trade_recommendation()` returns a perfect score no matter
what the agent says. The eval is measuring whether the agent mentions the right vocabulary (keyword
score), not whether it has an opinion.

**Latency is wall-clock, not CPU**: `latency_ms` uses `time.perf_counter()`, which includes network
round-trip time. Expect high variance between runs. The summary reports `avg_latency_ms` for
orientation, not for pass/fail decisions.
