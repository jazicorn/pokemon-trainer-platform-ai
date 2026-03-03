# Phase 12: Trade Offers

## Overview

Phase 12 extends the system with a **peer-to-peer trade offer workflow**. Users can now view
incoming trade offers (with AI evaluation attached to each one), send offers to other users (with AI
pre-screening before the offer is persisted), and accept or decline specific offers by ID.

This phase adds to three existing layers simultaneously: a new `trade_offers` table and
`TradeOffersManager` class (memory layer), two new async agent functions `get_pending_offers()` and
`send_trade_offer()` (agent layer), and four new CLI commands `offers`, `offer`, `accept`, `decline`
(CLI layer). The table lives in SQLite by default; when `PLATFORM_DB_URL` is set it is shared with
the web API's PostgreSQL database instead (see `docs/REFERENCE/PLATFORM_DB.md`).

## Where It Fits

```text
Phase 3: Memory System    (new table added to existing schema)
Phase 9: Trade Advisor    (evaluate_trade reused for AI pre-screening and inbox evaluation)
Phase 11: CLI Interface   (new commands wired into the existing parser and dispatch)
        ↓
Phase 12: Trade Offers
        ↓
Phase 13: Evaluations     (offers flow can be included in evaluation scenarios)
```

## Key Files

- `src/memory/database.py` — `trade_offers` table schema (in `init_database()`) and the
  `TradeOffersManager` class with six methods: `seed_offers()`, `create_offer()`,
  `get_inbox()`, `get_sent()`, `update_status()`, `save_ai_analysis()`. All methods
  dispatch to PostgreSQL when `PLATFORM_DB_URL` is configured.
- `src/data/platform_db.py` — optional PostgreSQL client (`PlatformDBClient`) and
  `get_platform_db()` singleton; returns `None` silently when `PLATFORM_DB_URL` is unset.
- `src/agents/trade_advisor.py` — `get_pending_offers(user_id)` and `send_trade_offer(sender_id,
  recipient_id, offered, requested)` — two new module-level async functions. Both reuse the existing
  `evaluate_trade()`.
- `src/cli/commands.py` — `OFFERS`, `OFFER_SEND`, `OFFER_ACCEPT`, `OFFER_DECLINE` added to
  `CommandType`; `OfferParams` named tuple; `_parse_offer()` helper added.
- `src/cli/app.py` — `handle_offers()`, `handle_offer_send()`, `handle_offer_accept()`,
  `handle_offer_decline()` added to `TradeCLI`.
- `tests/agents/test_trade_offers.py` — CRUD tests for `TradeOffersManager` and async tests for the two
  agent functions.

## Key Concepts

**The `trade_offers` table schema**:

```sql
CREATE TABLE IF NOT EXISTS trade_offers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id        TEXT NOT NULL,
    recipient_id     TEXT NOT NULL,
    offered_pokemon  TEXT NOT NULL,
    requested_pokemon TEXT NOT NULL,
    status           TEXT DEFAULT 'pending',
    ai_analysis      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at     TIMESTAMP
)
```

The `ai_analysis` column starts as `NULL` and is written later by `save_ai_analysis()`. The
`responded_at` column is set by `update_status()`.

**Status machine**: Offers have three states: `pending` → `accepted` or `declined`. The
`update_status()` method uses `WHERE status = 'pending'` as a guard — you cannot accept or decline
an offer that has already been responded to, and you cannot update an offer you did not receive. It
returns `True` if a row was changed, `False` otherwise.

**Parallel AI evaluation in `get_pending_offers()`**: The function fetches all pending inbox offers,
then evaluates each one concurrently using `asyncio.gather()`. If an offer already has a saved
`ai_analysis`, it is returned immediately without calling the agent. New analyses are saved back to
the database with `save_ai_analysis()` so subsequent inbox views are fast.

```python
async def _analyze(offer: dict) -> str:
    analysis = offer.get("ai_analysis")
    if not analysis:
        analysis = await evaluate_trade(
            offer["offered_pokemon"], offer["requested_pokemon"], user_id
        )
        mgr.save_ai_analysis(offer["id"], analysis)
    return analysis

analyses = await asyncio.gather(*[_analyze(o) for o in offers])
```

**AI pre-screening in `send_trade_offer()`**: Before an offer is inserted into the database,
`evaluate_trade()` runs on the proposed trade. The analysis text is saved alongside the offer row.
This means the recipient sees an AI verdict when they open their inbox — the sender's pre-screen
result is re-used rather than evaluated again.

**Lazy mock seeding**: `seed_mock_offers()` checks whether any offers already exist for
`recipient_id` before inserting the five hardcoded mock offers. The count check is the idempotency
guard — subsequent calls for the same user are no-ops.

```python
cursor.execute("SELECT COUNT(*) FROM trade_offers WHERE recipient_id = ?", (self.user_id,))
if cursor.fetchone()[0] > 0:
    return  # Already seeded
```

**`OfferParams` grammar — `offer {pokemon} to {user} for {their-pokemon}`**: `_parse_offer()` strips
the leading `"offer "` keyword, splits on `" to "` (giving `offered` + remainder), then splits the
remainder on `" for "` (giving `recipient` + `requested`). Because splitting is on full delimiter
strings rather than individual words, multi-word Pokemon names like `"mr mime"` work without any
special handling.

## Exploring the Code

In `database.py`, read the `trade_offers` table schema inside `init_database()` first to understand
the data shape. Then read each `TradeOffersManager` method in order: `seed_mock_offers()`
(idempotency pattern), `create_offer()` (returns `cursor.lastrowid`), `get_inbox()` (filters by
`recipient_id` and `status='pending'`), `get_sent()` (filters by `sender_id` with no status filter),
`update_status()` (the `WHERE recipient_id = ?` guard prevents cross-user tampering),
`save_ai_analysis()` (plain UPDATE by ID).

In `trade_advisor.py`, compare `get_pending_offers()` and `send_trade_offer()`:

- `get_pending_offers()` seeds, fetches, evaluates in parallel, formats output
- `send_trade_offer()` evaluates once, creates offer, saves analysis, formats confirmation

In `commands.py`, trace `_parse_offer()` with the input `"offer mr mime to user_003 for mr rime"`:

1. Strip `"offer "` → `"mr mime to user_003 for mr rime"`
2. Split on `" to "` → `offered="mr mime"`, remainder=`"user_003 for mr rime"`
3. Split remainder on `" for "` → `recipient="user_003"`, `requested="mr rime"`

In `app.py`, read `handle_offer_accept()` to see the two code paths: `"all"` (bulk accept with a
loop) vs. numeric string (single accept with `int()` conversion and a helpful error if parsing
fails).

## Running the Code

```bash
# Launch the app and try the offers flow
op run --env-file .env.op -- uv run python app.py

# Inside the CLI:
# > offers
# View inbox — seeds 5 mock offers on first run, runs AI evaluation on each.
# Output shows offer ID, sender, Pokemon pair, and AI verdict.

# > offers sent
# View offers you have sent, with status indicators (pending/accepted/declined).

# > offer gengar to user_002 for alakazam
# AI pre-screens the trade, then persists the offer. Shows offer ID and analysis.

# > accept 1
# Accept offer #1. Returns error message if already responded or wrong user.

# > decline 2
# Decline offer #2.

# > accept all
# Accept every pending offer in your inbox in one command.
```

## Running the Tests

```bash
# All trade offers tests
uv run pytest tests/agents/test_trade_offers.py -v

# Specific test classes
uv run pytest tests/agents/test_trade_offers.py::TestTradeOffersManager -v

# CLI parsing for offer commands is in test_cli.py
uv run pytest tests/cli/test_cli.py::TestParseOffers -v
uv run pytest tests/cli/test_cli.py::TestParseOffer -v

# Full relevant suite
uv run pytest tests/agents/test_trade_offers.py tests/cli/test_cli.py::TestParseOffers -v
```

`test_trade_offers.py` test groups:

| Test | What it verifies |
| --- | --- |
| `test_create_offer_returns_positive_id` | `create_offer()` returns an int > 0 |
| `test_get_inbox_filters_by_recipient` | Inbox shows only offers addressed to `self.user_id`, not offers sent by them |
| `test_get_sent_filters_by_sender` | Sent view shows only offers from `self.user_id` |
| `test_update_status_accepted` | After accepting, offer no longer appears in inbox |
| `test_update_status_declined` | After declining, offer no longer appears in inbox |
| `test_update_status_wrong_user_returns_false` | A bystander cannot accept an offer addressed to someone else |
| `test_seed_mock_offers_idempotent` | Calling `seed_mock_offers()` twice produces the same count as calling it once |
| `test_save_ai_analysis_persists` | `ai_analysis` column is written and readable via raw query |
| `test_get_pending_offers_calls_evaluate_trade` | `evaluate_trade` is called for each inbox offer (async, mocked) |
| `test_send_trade_offer_calls_evaluate_trade` | `evaluate_trade` is awaited before `create_offer` (async, mocked) |
| `test_get_pending_offers_empty_inbox` | Returns a friendly "empty" message when inbox has no pending offers |

All database tests use `tmp_path` + a monkey-patched `get_db_path()` for complete isolation — they
never touch `data/memory.db`.

## Common Gotchas

**Mock offers are seeded once per user, permanently**: After the first `offers` command for a user,
the 5 mock offers are in `data/memory.db` permanently. If you want a clean inbox for manual testing,
run `make reset-db` (or `rm data/memory.db`) and restart the app. The test suite uses a fresh
`tmp_path` fixture instead and never touches the real database.

**`asyncio.gather()` fails fast on any exception**: If `evaluate_trade()` raises for any single
offer in `get_pending_offers()`, the entire `gather()` call raises and the inbox is not shown. In
the current implementation there is no per-offer error handling. For production use, consider
wrapping each `_analyze(offer)` call in `try/except` with a fallback string like `"Analysis
unavailable."`.

**`update_status()` checks `recipient_id`**: The WHERE clause is `WHERE id = ? AND recipient_id = ?
AND status = 'pending'`. This means a user cannot accept or decline an offer sent to someone else,
and they cannot re-respond to an already-resolved offer. The method returns `False` in both cases —
`handle_offer_accept()` and `handle_offer_decline()` display a helpful message when they see
`False`.

**`get_sent()` has no status filter**: Unlike `get_inbox()` which only returns `pending` offers,
`get_sent()` returns all offers sent by the user regardless of status. The CLI formats each with a
status icon (`pending`, `accepted`, `declined`). This is intentional — sent offers are a historical
record, not an action queue.

**`TradeOffersManager.__new__` in tests**: Several tests construct `TradeOffersManager` using
`__new__` then manually set `user_id` to avoid calling `__init__` (which calls `init_database()`
against the live db path before the monkey-patch is in place). This is a test isolation pattern
specific to how `init_database()` is called in `__init__`. When using the manager in application
code, always use the normal constructor.
