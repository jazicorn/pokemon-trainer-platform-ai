# Platform Database Integration

The AI project can optionally read live data from the
[Pokemon Trainer Platform](https://github.com/your-org/pokemon-trainer-platform)
web API's PostgreSQL database instead of the bundled mock data.

## Activation

1. Install the optional driver:

   ```bash
   uv sync --group platform-db
   ```

2. Set the connection string:

   ```bash
   export PLATFORM_DB_URL=postgresql://trainer:secret@localhost:5432/pokemon_platform
   ```

When `PLATFORM_DB_URL` is unset, all data sources automatically fall back to
local mock data — no code changes required.

---

## PostgreSQL Schema Contract

The web API database must implement the following tables.

The AI project is **read-only** for `trades`, `user_pokemon`, `user_preferences`,
and `user_trade_history`. The `trade_offers` table is **shared read-write** — the
web API inserts new offers and the AI project writes back acceptance/rejection
status and AI analysis text.

### `trades`

Platform-wide trade history. Queried by `fetch_trades(days=90)`.

```sql
CREATE TABLE trades (
    trade_id          TEXT        PRIMARY KEY,
    traded_at         TIMESTAMPTZ NOT NULL,
    offered_pokemon   TEXT        NOT NULL,
    requested_pokemon TEXT        NOT NULL,
    status            TEXT        NOT NULL
                      CHECK (status IN ('pending', 'completed', 'rejected', 'cancelled')),
    user_a_id         TEXT        NOT NULL,
    user_b_id         TEXT        NOT NULL
);

CREATE INDEX idx_trades_traded_at ON trades (traded_at DESC);
```

### `user_pokemon`

The Pokémon owned by each user. Queried by `fetch_user_collection(user_id)`.

```sql
CREATE TABLE user_pokemon (
    id            BIGSERIAL PRIMARY KEY,
    user_id       TEXT      NOT NULL,
    pokemon_id    TEXT      NOT NULL,     -- e.g. "charizard"
    nickname      TEXT,                   -- nullable
    acquired_date DATE      NOT NULL,
    acquired_via  TEXT      NOT NULL,     -- "trade" | "catch" | "gift" | "evolution"
    tradeable     BOOLEAN   NOT NULL DEFAULT TRUE,
    is_shiny      BOOLEAN   NOT NULL DEFAULT FALSE,
    ball_type     TEXT                    -- nullable; e.g. "cherish", "master"
);

CREATE INDEX idx_user_pokemon_user_id ON user_pokemon (user_id);
```

### `user_preferences`

One row per user. Queried by `fetch_user_collection(user_id)`.

```sql
CREATE TABLE user_preferences (
    user_id        TEXT    PRIMARY KEY,
    favorite_types TEXT[]  NOT NULL DEFAULT '{}',
    goal           TEXT    NOT NULL DEFAULT '',
    trading_style  TEXT    NOT NULL DEFAULT 'balanced',
    never_trade    TEXT[]  NOT NULL DEFAULT '{}',
    seeking        TEXT[]  NOT NULL DEFAULT '{}'
);
```

### `user_trade_history`

Per-user completed trade log. Queried by `fetch_user_collection(user_id)`.

```sql
CREATE TABLE user_trade_history (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT      NOT NULL,
    trade_id   TEXT      NOT NULL,
    traded_at  DATE      NOT NULL,
    gave       TEXT      NOT NULL,
    received   TEXT      NOT NULL,
    satisfied  BOOLEAN   NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_user_trade_history_user_id ON user_trade_history (user_id);
```

### `trade_offers`

Shared read-write table. The web API inserts pending proposals; the AI project
reads them and writes back `status`, `ai_analysis`, and `responded_at`.
Used by `fetch_trade_offers(user_id)`, `fetch_sent_offers(user_id)`,
`update_offer_status()`, `save_offer_analysis()`, and `create_offer()`.

```sql
CREATE TABLE trade_offers (
    id                BIGSERIAL   PRIMARY KEY,
    sender_id         TEXT        NOT NULL,
    recipient_id      TEXT        NOT NULL,
    offered_pokemon   TEXT        NOT NULL,
    requested_pokemon TEXT        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
    ai_analysis       TEXT,                -- written by the AI project
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at      TIMESTAMPTZ          -- set when AI accepts or declines
);

CREATE INDEX idx_trade_offers_recipient ON trade_offers (recipient_id, status);
```

---

## Database Role (Recommended)

Create a dedicated PostgreSQL role. The AI project needs SELECT on all tables,
plus INSERT/UPDATE on `trade_offers` (the shared read-write table):

```sql
CREATE ROLE pokemon_ai WITH LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE pokemon_platform TO pokemon_ai;
GRANT USAGE ON SCHEMA public TO pokemon_ai;

-- Read-only tables
GRANT SELECT ON trades, user_pokemon, user_preferences, user_trade_history
    TO pokemon_ai;

-- Shared read-write table
GRANT SELECT, INSERT, UPDATE ON trade_offers TO pokemon_ai;
GRANT USAGE ON SEQUENCE trade_offers_id_seq TO pokemon_ai;
```

Then set:

```bash
PLATFORM_DB_URL=postgresql://pokemon_ai:choose-a-strong-password@host:5432/pokemon_platform
```

---

## Fallback Behaviour

| Condition | Result |
| --- | --- |
| `PLATFORM_DB_URL` unset | Silent fallback to mock data, no warning |
| `psycopg` not installed | `warnings.warn` once at startup, fallback to mock data |
| Connection refused / auth fails | `warnings.warn` once at startup, fallback to mock data |
| Individual query fails | `warnings.warn` at call time, fallback to mock data for that call |

The application always starts successfully regardless of database availability.

---

## Docker Compose

If the web API runs in Docker, expose the database port or use a shared network:

```yaml
services:
  pokemon-ai:
    environment:
      PLATFORM_DB_URL: postgresql://trainer:secret@db:5432/pokemon_platform
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: trainer
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: pokemon_platform
```

---

## Testing the Connection

```bash
uv sync --group platform-db

PLATFORM_DB_URL=postgresql://trainer:secret@localhost:5432/pokemon_platform \
  uv run python -c "
import sys; sys.path.insert(0, 'src')
from data.platform_db import get_platform_db
db = get_platform_db()
if db:
    trades = db.fetch_trades(days=7)
    print(f'Connected. {len(trades.trades)} trades in the last 7 days.')
else:
    print('Not connected — check PLATFORM_DB_URL and psycopg install.')
"
```
