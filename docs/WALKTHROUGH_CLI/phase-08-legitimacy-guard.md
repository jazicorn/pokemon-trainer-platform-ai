# Phase 8: Legitimacy Guard

## Overview

Phase 8 introduces the **Legitimacy Guard** — a compliance and fraud-detection agent. It verifies
whether a Pokemon in a specific PokeBall is legal, checks whether a claimed-shiny Pokemon is
shiny-locked, validates origin regions, and classifies the Pokemon's rarity tier. The result
includes a Risk Level (Low, Medium, High).

Unlike the other agents, the Legitimacy Guard is **fully deterministic** for its core decisions. Its
rule tables (`_LEGAL_BALL_MAP`, `_SHINY_LOCKED`, `_ORIGIN_MARKS`) are hardcoded Python data
structures. The LLM interprets the question and formats the response, but the actual legality
verdict comes from dict lookups — not model reasoning. This makes the guard highly reliable and
auditable.

## Where It Fits

```text
Phase 1: Infrastructure
        |
Phase 8: Legitimacy Guard (standalone compliance agent)
        |
Phase 11: Multi-Agent Orchestration (Trade Advisor calls Legitimacy Guard via tool)
Phase 8:  Evaluations (legitimacy check accuracy is measured)
```

## Key Files

| File | Role |
| --- | --- |
| `src/agents/legitimacy_guard.py` | The entire implementation: `_LEGAL_BALL_MAP`, `_SHINY_LOCKED`, `_ORIGIN_MARKS`, `_MYTHICALS`, `_LEGENDARIES`, `LegitimacyDependencies`, the `legitimacy_guard` agent, and the `verify_provenance` tool |
| `tests/agents/test_legitimacy_guard.py` | Three async tests using `FunctionModel` to drive the agent without a live LLM |

## Key Concepts

### One tool, four checks in sequence

`verify_provenance(pokemon, ball, is_shiny, origin_region)` performs all four checks in order:

1. **Ball check** — looks up `pokemon` in `legal_ball_map`. If the Pokemon is listed and the given
   `ball` is not in its allowed list, appends an `ILLEGAL BALL` flag.
2. **Shiny-lock check** — if `is_shiny=True` and the Pokemon is in `shiny_locked`, appends a `SHINY
   LOCK` flag.
3. **Origin check** — if `origin_region` is provided and not in `origin_marks`, appends an `UNKNOWN
   ORIGIN` warning.
4. **Rarity classification** — classifies as Mythical, Legendary, or Standard; prepends "Shiny " if
   `is_shiny=True`.

Risk level is `"High"` if any flags were raised, `"Medium"` if no flags but the rarity starts with
"Shiny", and `"Low"` otherwise.

### Ball legality: why this matters

Many legendary and mythical Pokemon can only legally exist in specific PokeBalls due to how they
were distributed. For example:

- Mew can only be in a Cherish Ball (event) or regular Poke Ball (Pokeball Plus) — `["cherish",
  "poke"]`
- Box legendaries like Mewtwo, Lugia, Ho-Oh can be in Master Ball, Cherish Ball, Poke Ball, or Ultra
  Ball
- Cosmog was always gifted by an NPC — only a Poke Ball is legal, never a catch ball

A "Mew in a Great Ball" is physically impossible in any legitimate game — the guard flags it as
`ILLEGAL BALL: HIGH RISK`.

### Shiny-locked list covers 32 Pokemon

The `_SHINY_LOCKED` frozenset includes all mythicals in their primary distributions, box legendaries
shiny-locked in their native games (Zacian, Zamazenta, Eternatus, Calyrex, Koraidon, Miraidon), and
gifted starters (Kubfu, Urshifu). A shiny version of any of these is a clear indicator of a hacked
Pokemon.

### `LegitimacyDependencies` makes rule tables injectable

The `LegitimacyDependencies` model holds `legal_ball_map`, `shiny_locked`, and `origin_marks` as
fields with defaults pointing at the module-level rule tables. This means tests can override
individual tables — `test_legitimacy_scam_detection` passes `legal_ball_map={"mew": ["cherish"]}` to
simplify the Mew case without loading the full table.

### The agent's system prompt enforces tool-first behavior

The system prompt includes an explicit checklist (BALL CHECK, SHINY CHECK, ORIGIN CHECK, RARITY
TIERING) and instructs the model to use the tool results — not its training data — for all legality
decisions. If the Pokemon is not in `_LEGAL_BALL_MAP`, the tool reports "no ball restriction found"
rather than guessing.

## Exploring the Code

Read `src/agents/legitimacy_guard.py` top to bottom. The data tables come first — spend time with
`_LEGAL_BALL_MAP` to understand the coverage (30+ Pokemon across all generations) and the ball
categories (cherish for events, master for in-game legendaries, poke for gifts). Then look at
`_SHINY_LOCKED` and `_LEGENDARIES` frozensets.

Read `LegitimacyDependencies` — note that `shiny_locked` is typed as `frozenset[str]` and the
`model_config` includes `arbitrary_types_allowed: True` so Pydantic accepts it.

Read `verify_provenance()` — it is the only tool. Pay attention to the guard conditions: ball check
only runs when `allowed_balls` is found AND `ball_type` is not `"unknown"` or `""`. This means
unknown balls do not raise a false positive.

In `tests/agents/test_legitimacy_guard.py`, read the `is_tool_result_in_history()` helper — it inspects
`ModelRequest` parts for any `ToolReturnPart`. This two-turn structure is the standard
`FunctionModel` pattern: turn 1 returns a `ToolCallPart`, turn 2 (once the tool result is in
history) returns a `TextPart` to end the loop.

## Running the Code

```bash
# Check legitimacy directly via a Python script (requires API key)
uv run python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from agents.legitimacy_guard import legitimacy_guard, LegitimacyDependencies

async def check():
    deps = LegitimacyDependencies()
    result = await legitimacy_guard.run(
        'Is a Mew in a Master Ball legitimate?',
        deps=deps
    )
    print(result.output)

asyncio.run(check())
"

# Inspect the rule tables directly without the agent
uv run python -c "
import sys; sys.path.insert(0, 'src')
from agents.legitimacy_guard import _LEGAL_BALL_MAP, _SHINY_LOCKED, _LEGENDARIES, _MYTHICALS
print('Mew legal balls:', _LEGAL_BALL_MAP.get('mew'))
print('Mewtwo legal balls:', _LEGAL_BALL_MAP.get('mewtwo'))
print('Is Zamazenta shiny-locked?', 'zamazenta' in _SHINY_LOCKED)
print('Is Pikachu a legendary?', 'pikachu' in _LEGENDARIES)
print('Is Mew a mythical?', 'mew' in _MYTHICALS)
"

# In the CLI, Trade Advisor calls this automatically via multi-agent orchestration
# To exercise it directly in the app: the advisor's check_legitimacy tool invokes it
```

## Running the Tests

```bash
uv run pytest tests/agents/test_legitimacy_guard.py -v
```

All three tests are `async` and use `FunctionModel` to mock the LLM. No API key is required.

### `test_legitimacy_scam_detection`

Passes a minimal `legal_ball_map={"mew": ["cherish"]}` as a dependency override. The mock model
always calls `verify_provenance` with `pokemon="mew", ball="great"`. Asserts that the tool output
contains `"ILLEGAL BALL"` and `"Mew"`.

### `test_rarity_classification`

Uses the default `LegitimacyDependencies()`. The mock model calls `verify_provenance` with
`pokemon="celebi", is_shiny=True`. Asserts the tool output contains `"Celebi"`, `"Mythical"`, and
`"Shiny"`.

### `test_agent_tool_routing`

The mock model calls `verify_provenance` with `pokemon="pikachu"`. Instead of inspecting tool
output, this test inspects `result.new_messages()` to confirm a `ToolCallPart` with
`tool_name="verify_provenance"` was generated during the run. This verifies that the agent-to-tool
dispatch path was actually executed.

## Common Gotchas

### `FunctionModel` requires a `TextPart` to end the loop

The mock model function must return a `ModelResponse(parts=[TextPart(content="...")])` when the tool
result is already in history, otherwise the agent loops indefinitely. An empty `parts=[]` raises
`UnexpectedModelBehavior`. See the `is_tool_result_in_history()` helper pattern used in all three
tests.

### `pytestmark = pytest.mark.asyncio` is module-level

`test_legitimacy_guard.py` sets `pytestmark = pytest.mark.asyncio` at module scope. This marks all
test functions in the file as asyncio tests. If you add new sync tests to the file, they will also
be run as coroutines and may behave unexpectedly.

### Ball check skips "unknown" ball values

Passing `ball="unknown"` or `ball=""` to `verify_provenance` suppresses the ball check entirely.
This is intentional — the tool should not raise a false positive when ball information is simply
missing. Only a known-bad combination (e.g. Mew in a Great Ball) should be flagged.

### Agent uses tool results, not training data

If you ask the agent about a Pokemon not in `_LEGAL_BALL_MAP` (e.g. a common Pokemon like Pikachu),
the tool will report no ball restriction and classify it as "Standard". The LLM will not guess that
Pikachu is always in a Poke Ball from its training data — it reports exactly what the tool returned.
