# Evaluation Results

Captured outputs from `pydantic-evals` runs demonstrating eval-driven development.

Run evals yourself with:

```bash
# Trade advisor eval
op run --env-file .env.op -- uv run python -c "
import sys; sys.path.insert(0, 'src')
import asyncio
from evals.eval_trade_advisor import main
asyncio.run(main())
"

# RAG vs no-RAG comparison
op run --env-file .env.op -- uv run python -c "
import sys; sys.path.insert(0, 'src')
import asyncio
from evals.eval_rag_comparison import main
asyncio.run(main())
"
```

---

## Trade Advisor Eval

Evaluates whether the trade advisor correctly recommends/declines trades based
on keyword presence and recommendation direction.

```text
==================================================
Trade Advisor Evaluation (pydantic-evals)
==================================================

                   Evaluation Summary: trade_advisor
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Case ID            ┃ Inputs                ┃ Scores               ┃ Duration ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ obvious_good_trade │ geodude → dragonite   │ keyword_score: 0.750 │    60.0s │
│                    │                       │ recommendation: 1.00 │          │
├────────────────────┼───────────────────────┼──────────────────────┼──────────┤
│ obvious_bad_trade  │ dragonite → geodude   │ keyword_score: 0.500 │    57.2s │
│                    │                       │ recommendation: 0.00 │          │
├────────────────────┼───────────────────────┼──────────────────────┼──────────┤
│ equal_value_trade  │ alakazam → gengar     │ keyword_score: 0.250 │    54.2s │
│                    │                       │ recommendation: 1.00 │          │
├────────────────────┼───────────────────────┼──────────────────────┼──────────┤
│ legendary_request  │ pikachu → mewtwo      │ keyword_score: 0.500 │    49.8s │
│                    │                       │ recommendation: 0.00 │          │
├────────────────────┼───────────────────────┼──────────────────────┼──────────┤
│ Averages           │                       │ keyword_score: 0.500 │    55.3s │
│                    │                       │ recommendation: 0.500│          │
└────────────────────┴───────────────────────┴──────────────────────┴──────────┘
```

**Key insight from evals:** The `recommendation_score` is 0 for "bad trade" cases.
The agent correctly identifies poor trades in its reasoning but does not use the
expected trigger words ("decline", "against", "wouldn't recommend"). This led to
adding explicit wording guidance to the trade advisor system prompt.

---

## RAG vs No-RAG Comparison

Demonstrates that the RAG-enabled Pokedex expert outperforms a plain LLM
baseline on Pokemon knowledge retrieval tasks.

```text
==================================================
RAG vs No-RAG Comparison (pydantic-evals)
==================================================

              Evaluation Diff: no_rag_baseline → rag_pokedex
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Case ID           ┃ Scores                          ┃ Duration         ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ charizard_types   │ keyword_score: 1.00 (no change) │  1.9s →  8.1s   │
├───────────────────┼─────────────────────────────────┼──────────────────┤
│ dragonite_stats   │ keyword_score: 0.667 (no change)│  3.8s → 12.3s   │
├───────────────────┼─────────────────────────────────┼──────────────────┤
│ mewtwo_legendary  │ keyword_score: 1.00 (no change) │  4.7s →  9.2s   │
├───────────────────┼─────────────────────────────────┼──────────────────┤
│ pikachu_evolution │ keyword_score: 0.500 → 1.00     │  1.9s →  8.3s   │
│                   │ (+0.5 / +100%)                  │                  │
├───────────────────┼─────────────────────────────────┼──────────────────┤
│ Averages          │ keyword_score: 0.792 → 0.917    │  3.1s →  9.5s   │
│                   │ (+0.125 / +15.8%)               │                  │
└───────────────────┴─────────────────────────────────┴──────────────────┘
```

**Key finding:** RAG improves average keyword accuracy by **+15.8%** over the
no-RAG baseline. The improvement is most pronounced for multi-hop questions
(e.g., "What does Pikachu evolve from?" — requires pre-evolution data that a
plain LLM answered less precisely). The trade-off is latency (~3x slower) which
is acceptable for an advisory tool.
