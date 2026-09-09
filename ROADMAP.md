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

## Phase 3 — Tenant Accounts & API Key Authentication

**Goal:** Protect all routes (except `/health`) with a per-tenant API key, where each key
maps server-side to that tenant's own `PLATFORM_DB_URL` — not a single shared secret.

**Why not a static key:** this API is meant to be public, with different callers each bringing
their own Postgres database (per `docs/REFERENCE/PLATFORM_DB.md`'s schema contract). A single
`API_KEY` env var can't express "which database does *this* caller's data live in" — so
authentication and tenant DB routing have to be the same lookup, not two separate concerns.

**Provisioning for this phase: admin-only.** No public signup endpoint yet — you provision each
tenant yourself via a console script. Self-serve registration is its own later phase (see
Phase 10) once this foundation exists and is trusted.

**Design:**

- New local store, `data/tenants.db` (SQLite — separate from `data/memory.db`, which is the
  CLI's own single-user local data, a different concept from operator-owned tenant accounts):
  - `tenants` table: `id`, `name` (a label — e.g. the tenant's contact email), `api_key_hash`
    (SHA-256 of the raw key; the raw key itself is never stored, logged, or retrievable again
    after issuance — same convention as GitHub/Stripe tokens), `platform_db_url_encrypted`,
    `created_at`, `is_active`
- New required env var: `TENANT_DB_ENCRYPTION_KEY` — a `cryptography.fernet.Fernet` key,
  generated once (`Fernet.generate_key()`) and held only in the server's own secret store.
  Encrypts every tenant's `platform_db_url` at rest. **Back this up outside the deployment
  itself** — losing it makes every stored `PLATFORM_DB_URL` permanently unrecoverable, not just
  hard to find.
- `scripts/provision_tenant.py <name> <platform_db_url>` — admin console script (same
  "review before you run it" spirit as `scripts/release.sh`). Generates a new random key via
  `secrets.token_urlsafe(32)`, hashes it for storage, encrypts the DB URL, inserts the row,
  and prints the **raw key once** for you to hand to that tenant.
- `src/api/auth.py`:
  - `APIKeyHeader(name="X-API-Key", auto_error=False)`
  - `require_api_key` dependency: hashes the incoming header, looks up `tenants` by
    `api_key_hash` + `is_active`; raises `HTTPException(401)` if the header is absent,
    `HTTPException(403)` if no active tenant matches. On success, decrypts that tenant's
    `platform_db_url` and returns a `TenantContext(tenant_id, platform_db_url)` via FastAPI's
    dependency injection — every protected route receives it as a parameter, not a global.
- The existing global `PLATFORM_DB_URL` env var / `config.platform_db_url` is **unchanged and
  keeps working exactly as it does today** — but only for the CLI (`app.py`), which stays
  genuinely single-user/local. The HTTP API never reads that global; it only ever uses the
  per-request `TenantContext` resolved above.
- `src/data/platform_db.py` needs a DSN-parameterized sibling to today's singleton
  `get_platform_db()` (which reads `os.environ` once for the CLI's one connection) — e.g.
  `get_platform_db_for(dsn: str)`, backed by a small LRU cache keyed by DSN so repeated calls
  from the same tenant reuse a connection instead of reconnecting every request.

**Tasks:**

- Add `cryptography` dependency (Fernet)
- Create `src/api/tenants.py`: `data/tenants.db` schema, `create_tenant()`,
  `get_tenant_by_key_hash()`
- Create `scripts/provision_tenant.py`
- Create `src/api/auth.py` with `require_api_key` as described above
- Add `TENANT_DB_ENCRYPTION_KEY` to `src/config.py`'s accepted env vars
- Add `get_platform_db_for(dsn)` to `src/data/platform_db.py`, alongside (not replacing) the
  existing singleton the CLI uses
- Apply `Depends(require_api_key)` as a router-level or app-level dependency, excluding
  `/health`

**Verification:**

```bash
# Provision a tenant, capture the printed key once
uv run python scripts/provision_tenant.py "test-tenant" "postgresql://user:pass@host/db"
# → API key (shown once): <generated-key>

# Missing key → 401
curl -i http://localhost:8080/trade/suggestions
# → HTTP/1.1 401

# Wrong/unknown key → 403
curl -i -H "X-API-Key: wrong" http://localhost:8080/trade/suggestions
# → HTTP/1.1 403

# Correct key → 200, reasoning over THAT tenant's own platform_db_url
curl -H "X-API-Key: <generated-key>" http://localhost:8080/trade/suggestions
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

## Phase 9 — Deployment

**Goal:** Run the API as a persistent, publicly-reachable service — this is a genuinely public
API (per Phase 3's design decision), not a private backend-to-backend link, so real TLS and
public-network hardening are required here, not optional.

**Tasks:**

- Add a long-running `api` service to `docker-compose.yml` (alongside the existing `chromadb`,
  `phoenix`, `postgres`, `app` services) — `docker compose up api`, not `run --rm` like the
  interactive CLI's `app` service:
  - `command: uv run python api_server.py` (overrides the image's CLI `CMD`)
  - `healthcheck` against `GET /health`, matching the `chromadb` service's pattern
  - `volumes:` must include `./data:/app/data` (already true for `app`) so `data/tenants.db`
    (Phase 3) persists across restarts/redeploys instead of living in ephemeral container
    storage — losing this file means every provisioned tenant loses access
- Confirm `image-publish.yml`'s existing GHCR image (built for the CLI's `CMD`) still works
  for the API: since `docker-compose.yml` overrides `command:`, no separate image/Dockerfile
  is needed — same published image, different command per service
- Put a reverse proxy or the hosting platform's own load balancer in front for TLS —
  Caddy/nginx on a VPS, or built-in HTTPS on Fly.io/Railway/Render/a cloud container service.
  Never expose uvicorn's plain HTTP directly to the internet.
- Document the actual target host in `docs/DEPLOYMENT.md` (new) once one is chosen, covering
  how secrets (`ANTHROPIC_API_KEY`, `TENANT_DB_ENCRYPTION_KEY`) are injected as real environment
  variables via that platform's own secret store — never a committed `.env` — and where
  `TENANT_DB_ENCRYPTION_KEY`'s backup copy lives (see Phase 3's warning: losing it is
  unrecoverable, not just inconvenient)
- Consider basic rate limiting per API key at this layer (or the reverse proxy) — a public,
  unauthenticated-until-keyed surface is a realistic abuse target once `/health` and
  registration-adjacent endpoints are reachable by anyone

**Verification:**

```bash
curl https://<your-public-domain>/health
# → {"status": "ok", "chromadb": true}

curl -X POST https://<your-public-domain>/trade/evaluate \
  -H "X-API-Key: <a tenant's provisioned key>" \
  -H "Content-Type: application/json" \
  -d '{"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard", "user_id": "<a real user id in that tenant'"'"'s database>"}'
# → reasoning grounded in that tenant's own platform_db_url collection, not mock data

# Restart the api service and confirm tenants.db survived (persistent volume check):
docker compose restart api
curl -H "X-API-Key: <the same tenant key>" https://<your-public-domain>/health
```

---

## Phase 10 — Self-Serve Tenant Registration

**Goal:** Let a new tenant register and get an API key without you provisioning them by hand —
extends Phase 3's tenant store rather than replacing it.

**Tasks:**

- `POST /accounts/register` (unauthenticated by definition — it's how a caller *gets* a key):
  accepts `{name, platform_db_url}`, returns a newly generated API key **once** in the response
  body, and inserts the same `tenants` row shape `scripts/provision_tenant.py` creates today
- Before storing, validate the submitted `platform_db_url` actually connects and matches
  `docs/REFERENCE/PLATFORM_DB.md`'s schema contract (e.g. a `SELECT 1` against each expected
  table) — reject with a clear 4xx and which table/column is missing, rather than silently
  storing a DSN that will fail on first real use
- Rate-limit this endpoint specifically — it's the one surface an anonymous caller can hit
  with no key at all, making it the obvious abuse target
- `POST /accounts/rotate-key` and `DELETE /accounts` (both behind the tenant's own current
  key) — self-serve means tenants can no longer ask you to do this manually, so they need a
  way to do it themselves
- Update `scripts/provision_tenant.py`'s docstring to note it's now the *admin override* path
  (support/manual cases), not the only way in

**Verification:**

```bash
curl -X POST https://<your-public-domain>/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"name": "new-tenant", "platform_db_url": "postgresql://user:pass@host/db"}'
# → {"api_key": "<shown once>", "tenant_id": "..."}

# A platform_db_url that doesn't match the schema contract is rejected up front:
curl -X POST https://<your-public-domain>/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"name": "bad-tenant", "platform_db_url": "postgresql://user:pass@host/empty_db"}'
# → HTTP 4xx, naming the missing table
```

---

## Phase 11 — Local Admin Web UI (Tenant Management Dashboard)

**Goal:** A local, operator-only web UI for viewing and managing tenants (Phase 3's
`data/tenants.db`) — list, create, deactivate, and rotate keys — without hand-running
`scripts/provision_tenant.py` or raw SQL for every change.

**Why local, not part of the public API:** this surface can see and act on every tenant's
account — activating/deactivating access, rotating keys, and (if ever revealed) their
`platform_db_url`. That's a different trust level than the public trade-advisor endpoints
entirely, so it deliberately stays out of `api_server.py`'s public surface:

- Ships as its own entry point, `admin_server.py`, bound to `127.0.0.1` by default — not
  started by `docker-compose.yml`'s public `api` service, and never given a public route
  through Phase 9's reverse proxy.
- To manage a remote/production deployment, run it on that host directly, or reach it over an
  SSH tunnel to `127.0.0.1` — the same operational pattern as a database admin tool, not
  something exposed alongside the public API.
- Gated by its own `ADMIN_TOKEN` env var — a separate secret from any tenant's API key and
  from `TENANT_DB_ENCRYPTION_KEY` — since "local" isn't a substitute for authentication if the
  host is ever shared or a tunnel ever left open.

**Design:**

- `src/admin/app.py` — a second, small FastAPI app with Jinja2-templated server-rendered pages
  (no SPA/build step needed for an internal tool this size), reusing Phase 3's
  `src/api/tenants.py` functions rather than duplicating tenant logic
- Pages:
  - `GET /` — table of tenants: name, created_at, active/inactive, masked key (last 4 chars
    only) — never the decrypted `platform_db_url` on this listing page
  - `GET /tenants/{id}` — detail view; `platform_db_url` shown as host/database only
    (credentials redacted) by default, with a "reveal" action that re-checks `ADMIN_TOKEN`
    before showing the full DSN, for the rare case you need it to debug a tenant's connection
  - `POST /tenants/new` — same two inputs as `scripts/provision_tenant.py`, shows the new key
    once on success
  - `POST /tenants/{id}/deactivate`, `POST /tenants/{id}/rotate-key`
- `admin_server.py` at project root, mirroring `api_server.py`'s structure, except `API_HOST`
  defaults to `127.0.0.1` here (not `0.0.0.0` like the public API) and it uses its own
  `ADMIN_PORT`, distinct from `API_PORT`

**Tasks:**

- Add `jinja2` dependency
- Extend `src/api/tenants.py` with `list_tenants()`, `deactivate_tenant(id)`,
  `rotate_tenant_key(id)` — Phase 3 only needed `create_tenant`/`get_tenant_by_key_hash`;
  this phase is what needs the rest of the CRUD surface
- Create `src/admin/app.py` and `src/admin/templates/*.html`
- Create `admin_server.py`
- Add `ADMIN_TOKEN` to `src/config.py`'s accepted env vars, and a simple auth dependency
  (compare a header/cookie to `config.admin_token`) guarding every route in this app
- Add a `run-admin` Makefile target

**Verification:**

```bash
make run-admin
# → serving on http://127.0.0.1:8090 — confirm it's NOT reachable from another machine
#   (unlike make run-api, which binds 0.0.0.0)

open http://127.0.0.1:8090
# → tenant list page, prompts for ADMIN_TOKEN

# Create a tenant through the UI, then confirm the key it shows actually works
# against the real public API:
curl -H "X-API-Key: <key shown in the admin UI>" http://localhost:8080/health
# → {"status": "ok", "chromadb": true}

# Deactivate that tenant through the UI, then confirm the API rejects it on a
# protected route (not /health, which needs no key at all):
curl -i -H "X-API-Key: <same key>" http://localhost:8080/trade/suggestions
# → HTTP/1.1 403
```

---

## Phase 12 — Project Documentation Site (GitHub Pages)

**Goal:** A browsable docs/landing site at `https://jazicorn.github.io/pokemon-trainer-platform-ai/`,
built from the project's existing `README.md` and `docs/` markdown — no new content authored
just for this, just a better way to browse what's already written.

**Independent of the other phases:** unlike Phases 4–8 (which build on each other), this one
has no dependency on the API work at all — it's just documentation tooling. It can be done any
time, including before Phase 2, without blocking or being blocked by anything else here.

**Design:**

- **MkDocs + the Material theme**, not Docusaurus (JS/React — heavier tooling for a Python
  project) or hand-written HTML (loses search/nav for free, and means maintaining content in
  two places). MkDocs renders the existing markdown files directly, is itself just a
  `uv`-installable Python tool consistent with the rest of this project, and gets full-text
  search + navigation with no extra work.
- Site structure mirrors the existing docs layout: Home (`README.md`), Getting Started
  (`docs/GETTING_STARTED.md`), Reference (`docs/REFERENCE/*.md`), Roadmap (`ROADMAP.md`),
  History (`HISTORY.md` — Commitizen's auto-generated changelog from Phase-adjacent release work)
- Deployed via a new `.github/workflows/docs-publish.yml`, building and pushing to a
  `gh-pages` branch on every push to `main` that touches `docs/**`, `README.md`, `ROADMAP.md`,
  `HISTORY.md`, or `mkdocs.yml` — the same narrowly-scoped path-filtering `image-build.yml`
  already uses elsewhere in this repo
- GitHub Pages itself (repo Settings → Pages, serving from the `gh-pages` branch) is a
  one-time manual step in the GitHub UI — no workflow file can do that part

**Tasks:**

- Add `mkdocs` + `mkdocs-material` as a new `docs` dependency group in `pyproject.toml`
  (not `dev` — it's not needed for development or CI testing, only for building the site)
- Create `mkdocs.yml` at the project root: site name, nav structure mapping to the files above,
  Material theme config
- Create `.github/workflows/docs-publish.yml` (`mkdocs gh-deploy`, path-filtered as above)
- One-time: enable GitHub Pages in repo settings, pointed at the `gh-pages` branch
- Add a badge/link in `README.md`'s header pointing at the published Pages URL, matching the
  existing badge-row style

**Verification:**

```bash
uv sync --group docs
uv run mkdocs serve
# → http://127.0.0.1:8000 — confirm the nav renders every docs/ page and README/ROADMAP/HISTORY

git push origin main   # touching docs/**, README.md, ROADMAP.md, HISTORY.md, or mkdocs.yml
# → docs-publish.yml runs, gh-pages branch updates
# → https://jazicorn.github.io/pokemon-trainer-platform-ai/ reflects the change
```

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
