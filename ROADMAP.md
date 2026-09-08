# Roadmap: Web API

Convert the Pokemon Trainer Platform from a CLI + MCP server into a full HTTP web API using
FastAPI, while keeping the existing CLI and MCP interfaces intact.

---

## Phase 1 — Dependencies & Entry Point

**Goal:** Get a runnable FastAPI server that starts up cleanly and responds to a health check.

**Tasks:**

- Add `fastapi>=0.115.0` and `uvicorn[standard]>=0.34.0` to `pyproject.toml` dependencies
- Run `uv sync` to install
- Create `src/api/__init__.py` (empty package init)
- Create `api_server.py` at project root — mirrors `app.py` but launches uvicorn
- Create `src/api/app.py` with:
  - FastAPI `app` instance
  - `lifespan` context manager calling
    `startup(phoenix=False, chromadb=True, telemetry=True, database=True)`
  - `GET /health` endpoint returning service status (no auth required)
- Add `run-api` target to `Makefile`

**Verification:**

```bash
make run-api
curl http://localhost:8080/health
# → {"status": "ok", "chromadb": true}
```

---

## Phase 2 — Request & Response Models

**Goal:** Define all typed API contracts before any routes are wired.

**Tasks:**

- Create `src/api/models.py` with Pydantic models:
  - `ChatRequest` — `message`, `user_id`, `conversation_context`
  - `EvaluateTradeRequest` — `offered_pokemon`, `requested_pokemon`, `user_id`,
    `conversation_context`
  - `SendOfferRequest` — `sender_id`, `recipient_id`, `offered_pokemon`, `requested_pokemon`
  - `QueryRequest` — `question`, `user_id`
  - `ApiResponse` — `result`, `status`
- Run `uv run pyright src/api/models.py` to confirm no type errors

**Verification:**

```bash
uv run pyright src/api/models.py
# → 0 errors, 0 warnings
```

---

## Phase 3 — API Key Authentication

**Goal:** Protect all routes (except `/health`) with a static API key check.

**Design:**

- Callers pass their key in the `X-API-Key` request header
- The server reads the expected key from the `API_KEY` environment variable at startup
- `/health` is exempt — unauthenticated probes must always work
- Missing header → HTTP 401; wrong key → HTTP 403

**Tasks:**

- Add `API_KEY` to the accepted env vars in `src/config.py`
  (alongside the existing model provider keys)
- Create `src/api/auth.py`:
  - Use FastAPI's `APIKeyHeader(name="X-API-Key", auto_error=False)`
  - Dependency function `require_api_key` reads `config.api_key`, raises:
    - `HTTPException(401)` if header is absent
    - `HTTPException(403)` if header value does not match
- Apply `Depends(require_api_key)` as a router-level or app-level dependency,
  excluding `/health`

**Verification:**

```bash
# Missing key → 401
curl -i http://localhost:8080/trade/suggestions
# → HTTP/1.1 401

# Wrong key → 403
curl -i -H "X-API-Key: wrong" http://localhost:8080/trade/suggestions
# → HTTP/1.1 403

# Correct key → 200
curl -H "X-API-Key: $API_KEY" http://localhost:8080/trade/suggestions
# → {"result": "...", "status": "ok"}

# Health always passes without a key
curl http://localhost:8080/health
# → {"status": "ok", "chromadb": true}
```

---

## Phase 4 — Core Trade Endpoints

**Goal:** Expose the primary agent functionality over HTTP.

**Tasks:**

- Add to `src/api/app.py`, importing from `agents.trade_advisor_api`:
  - `POST /chat` → `evaluate_trade(raw_query=request.message, user_id=...,
    conversation_context=...)`
  - `POST /trade/evaluate` → `evaluate_trade(offered_pokemon, requested_pokemon, user_id, ...)`
  - `GET /trade/suggestions` (query param: `user_id`) → `get_trade_suggestions(user_id)`
- All handlers are `async def` and wrapped in `try/except Exception` → HTTP 500 on failure
- All routes protected by `require_api_key` dependency from Phase 3

**Endpoints added this phase:** 3 (total: 4 with `/health`)

**Verification:**

```bash
curl -X POST http://localhost:8080/chat \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "Should I trade my Pikachu for their Charizard?"}'

curl -X POST http://localhost:8080/trade/evaluate \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard"}'

curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8080/trade/suggestions?user_id=user_001"
```

---

## Phase 5 — Offers & Query Endpoints

**Goal:** Complete the full API surface — inbox management and knowledge queries.

**Tasks:**

- Add to `src/api/app.py`, all protected by `require_api_key`:
  - `GET /offers` (query param: `user_id`) → `get_pending_offers(user_id)`
    from `agents.trade_advisor_api`
  - `POST /offers/send` →
    `send_trade_offer(sender_id, recipient_id, offered_pokemon, requested_pokemon)`
  - `POST /pokedex/query` → `query_pokedex(question, user_id)` from `agents`
  - `POST /market/query` → `query_market(question)` from `agents.trade_market_analyst`

**Endpoints added this phase:** 4 (total: 8)

**Verification:**

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/offers?user_id=user_001"

curl -X POST http://localhost:8080/offers/send \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d `{"sender_id":"user_001","recipient_id":"user_002",
       "offered_pokemon":"Eevee","requested_pokemon":"Vaporeon"}`

curl -X POST http://localhost:8080/pokedex/query \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are Charizards weaknesses?"}'

curl -X POST http://localhost:8080/market/query \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Which Pokemon are trending bullish right now?"}'

# Swagger UI (key can be set via the Authorize button)
open http://localhost:8080/docs
```

---

## Phase 6 — Observability & Request Logging

**Goal:** Wire HTTP request tracing into the existing Logfire + OpenTelemetry stack so
every API call appears in the Phoenix dashboard alongside agent spans.

**Why:** The project already instruments agent calls via `openinference-instrumentation-pydantic-ai`
and exports traces to Phoenix (`src/observability/`). Without this phase, HTTP-level context
(method, path, status, latency) is invisible in those traces.

**Tasks:**

- Add `logfire.instrument_fastapi(app)` in `src/api/app.py` after the app is created
  — Logfire ships FastAPI instrumentation out of the box, no new dependency needed
- Add a lightweight logging middleware to `src/api/app.py` that writes one structured
  line per request: method, path, status code, and duration in ms
  - Use Python's stdlib `logging` (already used throughout the project)
  - Format: `POST /chat 200 342ms`
- Verify traces appear in Phoenix at `http://localhost:6006` when `ENABLE_PHOENIX=true`

**Verification:**

```bash
# Start with Phoenix enabled
ENABLE_PHOENIX=true make run-api

# Make a request
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8080/trade/suggestions?user_id=user_001"

# Check server logs show the request line
# Check Phoenix at http://localhost:6006 shows the trace with agent sub-spans
```

---

## Phase 7 — API Tests

**Goal:** Extend the existing pytest suite with tests for all new API routes, consistent
with the project's mocked-LLM testing pattern (`make test`).

**Why:** The project has a strong testing culture with `pytest`, `pytest-asyncio`, and
mocked LLMs. The new API layer needs the same coverage, and FastAPI's `TestClient` makes
this straightforward without spinning up a real server.

**Tasks:**

- Create `tests/api/__init__.py` (matches every other test subdirectory's mirroring of `src/`)
- Create `tests/api/test_api.py` using FastAPI's `TestClient` (synchronous, no server needed)
- Mock the agent functions (`evaluate_trade`, `get_trade_suggestions`, etc.) using
  `unittest.mock.patch` — same pattern as existing agent tests
- Set `API_KEY=test-key` in test fixtures via `monkeypatch`
- Test cases to cover:
  - `GET /health` → 200 with no key
  - `POST /chat` with valid key → 200, result string in body
  - `POST /trade/evaluate` with valid key → 200
  - `GET /trade/suggestions` with valid key → 200
  - `GET /offers` with valid key → 200
  - `POST /offers/send` with valid key → 200
  - `POST /pokedex/query` with valid key → 200
  - `POST /market/query` with valid key → 200
  - Any protected route without key → 401
  - Any protected route with wrong key → 403
- Run with `make test` (no live APIs, no API costs)

**Verification:**

```bash
make test
# → tests/api/test_api.py ... passed (10+ new tests)
```

---

## Phase 8 — Polish & Documentation

**Goal:** Make the API discoverable and easy to run.

**Tasks:**

- Update `README.md` with a **Web API** section covering:
  - Quick start (`make run-api`, setting `API_KEY`)
  - Full endpoint table (method, path, auth required, description)
  - Example curl commands with `X-API-Key` header
- Confirm `make test` still passes (CLI unaffected)

**Final endpoint summary:**

| Method | Path                 | Auth | Description                            |
| ------ | -------------------- | ---- | -------------------------------------- |
| GET    | `/health`            | No   | Service health check                   |
| POST   | `/chat`              | Yes  | Free-text natural language agent query |
| POST   | `/trade/evaluate`    | Yes  | Structured trade evaluation            |
| GET    | `/trade/suggestions` | Yes  | Proactive trade suggestions            |
| GET    | `/offers`            | Yes  | Pending trade offer inbox              |
| POST   | `/offers/send`       | Yes  | Send a trade offer                     |
| POST   | `/pokedex/query`     | Yes  | Pokedex knowledge question             |
| POST   | `/market/query`      | Yes  | Market demand & trend query            |

---

## Source Mapping

| API Function | Source File |
| --- | --- |
| `evaluate_trade`, `get_trade_suggestions` | `src/agents/trade_advisor_api.py` |
| `get_pending_offers`, `send_trade_offer` | `src/agents/trade_advisor_api.py` |
| `query_pokedex` | `src/agents/__init__.py` |
| `query_market` | `src/agents/trade_market_analyst.py` |
| `startup()` | `src/startup.py` |
| `is_chromadb_running()` | `src/utils.py` |
| `require_api_key` | `src/api/auth.py` (new) |
| request logging middleware | `src/api/app.py` (new) |
| API route tests | `tests/api/test_api.py` (new) |
