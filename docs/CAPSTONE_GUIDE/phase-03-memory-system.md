# Phase 3: Memory System

## Overview

Phase 3 is the persistence layer. It gives every agent a way to remember things across sessions:
user preferences (what they're seeking, what they'll never trade, their goal), conversation history
(recent messages for context), and past recommendations (for feedback loops).

All storage uses a local **SQLite** database at `data/memory.db`. The schema is initialized
automatically on startup — you never need to create tables manually. All classes in this phase use
per-user isolation: `ConversationMemory("user_001")` and `ConversationMemory("user_002")` never see
each other's data.

## Where It Fits

```text
Phase 1: Infrastructure (init_database called during startup)
Phase 2: Mock Data (user IDs referenced)
        ↓
Phase 3: Memory System
        ↓
Later phases that read/write conversation history, preferences, or trade offers
```

## Key Files

- `src/memory/database.py` — SQLite schema, `get_connection()`, `init_database()`,
  `is_chromadb_running()`, `ensure_services()`, and `TradeOffersManager`. The `get_connection()`
  context manager sets `row_factory = sqlite3.Row` so all queries return dict-like rows.
- `src/memory/user_preferences.py` — `UserPreferencesManager`: save/load preferences, update
  `seeking` and `never_trade` lists atomically.
- `src/memory/conversation_memory.py` — `ConversationMemory` (add/get/clear messages, trim history)
  and `RecommendationMemory` (save recommendations, record user feedback).
- `src/memory/__init__.py` — Re-exports all public classes so callers import from `memory`, not from
  submodules.

## Key Concepts

**Per-user isolation**: Every manager takes a `user_id` in its constructor and filters all queries
by that ID. Two users writing to the same database never collide. The persistence tests verify this
with a `test_different_users_are_isolated` case.

**Row factory as dicts**: `get_connection()` sets `conn.row_factory = sqlite3.Row`. This means
`cursor.fetchall()` returns rows that behave like dicts — you access `row["content"]` rather than
`row[0]`. The `[dict(row) for row in cursor.fetchall()]` pattern appears throughout the codebase to
convert these to plain Python dicts.

**JSON-in-TEXT columns**: `favorite_types`, `seeking`, and `never_trade` are stored as JSON strings
in SQLite TEXT columns. `UserPreferencesManager` calls `json.dumps()` on write and `json.loads()` on
read. If you query the database directly with a SQL tool, you'll see `'["fire", "dragon"]'` —
remember to parse it.

**Atomic list updates**: `UserPreferencesManager.update_seeking()` reads the current list, modifies
it in Python as a `set`, then writes back the entire JSON field with `save_preferences()`. There is
no database-level list append — the whole column is replaced each time.

**History trimming**: `ConversationMemory.add_message()` calls `_trim_history()` after every write.
`_trim_history()` deletes rows not in the top-N by `created_at`, keeping at most `max_history` rows
(default: 20). This prevents unbounded database growth.

**Five-table schema**: `init_database()` creates: `user_preferences`, `conversation_history`,
`recommendations`, `learned_preferences`, and `trade_offers`. All use `CREATE TABLE IF NOT EXISTS`,
so the call is safe to repeat on every startup.

**`TradeOffersManager`**: Handles the trade inbox/outbox workflow — creating offers, seeding mock
inbox data on first view, updating offer status (accepted/declined), and saving AI analysis text. It
lives in `database.py` because it works directly with the `trade_offers` table schema.

## Exploring the Code

Start with `database.py`: read `init_database()` to see the full five-table schema and column types.
Then read `get_connection()` to understand the context manager and row factory pattern. Note that
`TradeOffersManager.__init__()` calls `init_database()` defensively — it's safe to call multiple
times.

In `user_preferences.py`, read `save_preferences()` to see `INSERT OR REPLACE` — the whole row is
replaced on every save, not merged column by column. Then read `update_seeking()` to see the
read-modify-write pattern using a Python `set` for deduplication.

In `conversation_memory.py`, compare `ConversationMemory.add_message()` with
`RecommendationMemory.save_recommendation()`. The former stores free-text `(role, content)` pairs.
The latter stores structured data with separate columns for offered/requested pokemon,
recommendation text, reasoning, and feedback — enabling future analytics on recommendation accuracy.

## Running the Code

```bash
# Start a REPL with src on the path
cd /Users/jasmineanderson/Code/TW-Beach/katas-exercises/capstone
uv run python -c "
import sys; sys.path.insert(0, 'src')
from memory.database import init_database
from memory import UserPreferencesManager

init_database()

mgr = UserPreferencesManager('user_001')
mgr.save_preferences(
    favorite_types=['fire', 'dragon'],
    goal='Complete Dragon collection',
    trading_style='value_focused',
    seeking=['dragonite', 'salamence'],
    never_trade=['charizard'],
)
prefs = mgr.get_preferences()
print(prefs)
"

# Add and retrieve conversation messages
uv run python -c "
import sys; sys.path.insert(0, 'src')
from memory.database import init_database
from memory import ConversationMemory

init_database()

mem = ConversationMemory('user_001')
mem.add_message('user', 'Should I trade Pikachu for Charizard?')
mem.add_message('assistant', 'Charizard has higher market demand.')
print(mem.get_context_string())
"

# Save a recommendation and record feedback
uv run python -c "
import sys; sys.path.insert(0, 'src')
from memory.database import init_database
from memory import RecommendationMemory

init_database()

rec_mem = RecommendationMemory('user_001')
rec_id = rec_mem.save_recommendation(
    offered_pokemon='pikachu',
    requested_pokemon='gengar',
    recommendation='accept',
    reasoning='Gengar has stronger competitive value.',
)
rec_mem.record_feedback(rec_id, followed=True, feedback='Great advice!')
print(rec_mem.get_past_recommendations())
"
```

## Running the Tests

```bash
# Unit tests: CRUD operations, trimming, per-user isolation
uv run pytest tests/test_memory.py -v

# Persistence tests: data survives across new class instances
uv run pytest tests/test_memory_persistence.py -v

# Run both
uv run pytest tests/test_memory.py tests/test_memory_persistence.py -v
```

`test_memory.py` uses an `autouse` fixture that patches `memory.database.get_db_path` to point at a
`tmp_path` temp file for every test. It then verifies CRUD operations within a single instance:
save/get preferences, add/get/clear/trim messages, save recommendation, record feedback.

`test_memory_persistence.py` uses an `isolated_db` fixture (also redirecting to `tmp_path`) but
creates **two separate instances** of each manager class and verifies that data written by instance
A is visible to instance B. This is the critical test: it proves the database actually persists to
disk rather than just holding state in memory. Test groups:

- `TestConversationPersistence` — messages, clear, trim, user isolation, context string
- `TestPreferencesPersistence` — full preferences, seeking add/remove, never_trade, empty user
- `TestRecommendationPersistence` — save, positive row ID, feedback, multiple records

## Common Gotchas

**Stale database between test runs**: If tests accidentally use the real `data/memory.db` instead of
a temp file, they can interfere with each other. The memory tests always patch `get_db_path` — look
at `test_memory.py`'s `setup_test_db` fixture and `test_memory_persistence.py`'s `isolated_db`
fixture before writing new memory tests. For manual app testing (not unit tests), run
`make reset-db` to wipe the database and start fresh.

**`JSON-in-TEXT` columns**: `favorite_types`, `seeking`, and `never_trade` are stored as JSON
strings in TEXT columns. If you query `data/memory.db` directly with a SQL client, you'll see
`'["fire", "dragon"]'` — use `json.loads()` to parse it.

**`TradeOffersManager` auto-inits schema**: `TradeOffersManager.__init__()` calls `init_database()`.
This is intentional for convenience, but means constructing a `TradeOffersManager` in a test that is
not using a temp DB will touch the real `data/memory.db`. Always use the patching pattern from the
existing tests.

**`get_history` returns chronological order**: `get_history()` queries with `ORDER BY created_at
DESC LIMIT ?` and then reverses the result in Python — so the list you get back is oldest-first.
This matters if you're testing the order of returned messages.
