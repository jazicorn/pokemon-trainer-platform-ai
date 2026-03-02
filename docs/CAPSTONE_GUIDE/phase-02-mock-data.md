# Phase 2: Mock Data & Models

## Overview

Phase 2 defines the data contracts the entire system operates on. It provides two things: **Pydantic
models** that give every component a shared, type-safe vocabulary, and **mock data generators** that
produce realistic platform trade history and user collections to develop and test against.

The generated data lives in `data/platform_trades.json` and `data/user_collection.json`. Agents,
memory, and evals all load from these files via the loader — no agent directly reads raw JSON.

## Where It Fits

```text
Phase 1: Infrastructure
        ↓
Phase 2: Mock Data & Models  ←  defines the data contracts
        ↓
All later phases that load trade history or user collections
```

## Key Files

- `src/data/models.py` — Pydantic models: `Trade`, `TradeStatus` (enum), `PlatformTrades`,
  `UserCollection`, `OwnedPokemon`, `UserPreferences`, `UserTradeHistory`. These are the canonical
  types used everywhere.
- `src/data/generator.py` — `generate_platform_trades()` and `generate_user_collection()`. Produces
  mock data with rarity-weighted trade outcomes. Exports the module-level `RARITY` constant used by
  tests.
- `src/data/loader.py` — `load_user_collection(user_id)` and `load_platform_trades()`. Returns typed
  Pydantic models. The platform trades loader is `@lru_cache`'d; the user collection loader raises
  `ValueError` if the requested user ID doesn't match the file.
- `src/data/__init__.py` — Re-exports all public models and loader functions so callers import from
  `data`, not from submodules.
- `data/platform_trades.json` — Generated output: 200 trades with timestamps, status, user IDs, and
  Pokemon pairs, sorted chronologically.
- `data/user_collection.json` — Generated output: a single user's Pokemon inventory and preferences.

## Key Concepts

**Pydantic models as contracts**: Every field in `Trade` and `UserCollection` is typed and validated
at load time. If the JSON has a malformed timestamp or an unrecognized status string, Pydantic
raises `ValidationError` immediately — the error never propagates silently into an agent.

**Rarity-weighted trade outcomes**: `PokemonRarity.get_trade_success_rate()` returns `(statuses,
weights)` pairs. Legendaries are rejected 80% of the time, pseudo-legendaries 60%, and common
Pokemon are completed 70% of the time. This makes the mock data realistic for analyses that examine
demand by rarity.

**Seeking vs. owned separation**: `generate_user_collection()` computes the seeking list as a set
difference — Pokemon the user wants but does not already own. The test `test_seeking_not_in_owned`
verifies this invariant holds.

**`@lru_cache` on platform trades**: `load_platform_trades()` is cached with `maxsize=1`. The
200-trade JSON file is read once per process. Tests that need a fresh load call
`load_platform_trades.cache_clear()` before patching `get_data_dir`.

**Loader raises on user ID mismatch**: `load_user_collection("wrong_id")` raises `ValueError`. The
file was generated for a specific user; loading it under a different ID would be a programming
error.

## Exploring the Code

Read `models.py` first — it's short and gives you the vocabulary for every other file. Pay attention
to `TradeStatus` (a `str` enum with `PENDING`, `COMPLETED`, `REJECTED`, `CANCELLED` values) and
`OwnedPokemon.tradeable` (legendaries often have `tradeable=False`).

In `generator.py`, look at the `PokemonRarity` dataclass. It uses `frozenset` for each tier
(immutable, O(1) membership test), and `all_pokemon` is a property that unions all tiers plus an
extra set of named Pokemon. Then read `get_trade_success_rate()` to see how rarity maps to
`random.choices()` weights. Finally, trace `generate_platform_trades()` → `_create_trade()` to see
exactly how each trade record is built.

In `loader.py`, note that `get_data_dir()` is a standalone function (not a class method) — this
makes it easy to monkeypatch in tests without touching the module-level `@lru_cache`.

## Running the Code

```bash
# Regenerate both data files
uv run python -m data.generator

# Or call save_mock_data directly in a REPL
uv run python -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
from data.generator import save_mock_data
save_mock_data(Path('data'))
"

# Inspect the loader
uv run python -c "
import sys; sys.path.insert(0, 'src')
from data.loader import load_platform_trades, load_user_collection
trades = load_platform_trades()
print(f'{len(trades.trades)} trades loaded')
print(f'First trade: {trades.trades[0]}')
collection = load_user_collection('user_001')
print(f'User: {collection.user_id}, Pokemon owned: {len(collection.pokemon)}')
print(f'Seeking: {collection.preferences.seeking}')
"
```

## Running the Tests

```bash
uv run pytest tests/data/test_data.py -v
```

Test groups:

- `TestPokemonRarity` — verifies `RARITY.legendary` is a `frozenset`, that all legendary Pokemon
  appear in `all_pokemon`, and that `get_trade_success_rate()` returns higher rejection weight for
  legendaries than for commons.
- `TestGeneratePlatformTrades` — checks that `generate_platform_trades(num_trades=N)` returns
  exactly N trades, that trades are sorted by timestamp, that all required fields are present, and
  that `user_a_id != user_b_id`.
- `TestGenerateUserCollection` — checks that the `user_id` field matches the argument, that
  `len(pokemon)` is between 8 and 15, that all preference keys are present, and that `seeking` and
  `pokemon` are disjoint sets.
- `TestDataLoader` — uses `tmp_path` + `monkeypatch` to point `get_data_dir` at generated test data,
  then verifies the loader returns typed Pydantic models and raises `ValueError` for wrong user IDs.
- `TestPydanticModels` — validates `TradeStatus` enum values and that constructing a `Trade` model
  with valid fields succeeds.

## Common Gotchas

**Cache across tests**: `load_platform_trades()` is `@lru_cache`'d. If one test loads from `data/`,
subsequent tests may read the cached result even after patching `get_data_dir`. Always call
`load_platform_trades.cache_clear()` in your test setup when redirecting to a temp directory.

**Non-deterministic generator**: `generate_platform_trades()` uses `random` without a fixed seed.
Two calls produce different data. Tests that check invariants (sort order, field presence, user ID
separation) are designed to pass regardless — but do not write tests that assert specific Pokemon
names or trade counts beyond the generation parameters.

**`data/` directory location**: `get_data_dir()` resolves relative to `loader.py`'s location — it
walks up from `src/data/` to the capstone root, then appends `data/`. If you move `loader.py`,
update this path.
