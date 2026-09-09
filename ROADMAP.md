# Roadmap: Web API

Convert the Pokemon Trainer Platform from a CLI + MCP server into a full HTTP web API using
FastAPI, while keeping the existing CLI and MCP interfaces intact.

**Testing policy — applies to every phase below:** a phase isn't done until its own
automated tests exist in `tests/` and pass, written as part of implementing that phase, not
after it. There is no "manually verify with curl or a throwaway script" step in this
project's workflow — if code needs verifying, write the real `pytest`/`TestClient` test for
it; that test *is* how it gets verified, and it's what stays behind to catch the next
regression. This replaced an earlier, weaker version of this policy — see HISTORY.md /
git log for the Phase 3 auth work that prompted the change.

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
- Write `tests/api/test_tenants.py` and `tests/api/test_auth.py` as part of *this* phase, not
  deferred to Phase 7 — every other module in this project (agents, cli, memory, ...) has tests
  written alongside its own code, and API auth logic shouldn't be the one exception. Phase 7 is
  gap-filling and integration coverage across phases, not the sole place tests get written.

**Verification:**

No route protected by `require_api_key` exists yet — that's Phase 4. A `curl` against
`/trade/suggestions` here would 404 before ever reaching auth, which isn't a
meaningful check of anything and would look like a bug when it isn't one. What's
actually verifiable at the end of *this* phase:

```bash
# Provision a real tenant, capture the printed key once
uv run python scripts/provision_tenant.py "test-tenant" "postgresql://user:pass@host/db"
# → API key (shown once): <generated-key>

# The real, permanent test suite — not a forward-reference to an endpoint that
# doesn't exist yet — proves the 401/403/200 behavior against an isolated test
# app (see tests/api/test_auth.py):
uv run pytest tests/api/ -v
# → 16 passed

# Health, the one route that exists so far, still works without a key:
curl http://localhost:8080/health
# → {"status": "ok", "chromadb": true}
```

Once Phase 4 adds real routes, this same 401/403/200 behavior becomes directly
`curl`-able against them too — see Phase 4's own verification section.

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
- Write `tests/api/test_trade_endpoints.py` for these three routes as part of this phase
  (`TestClient`, mocked `evaluate_trade`/`get_trade_suggestions` — same mocking pattern already
  used throughout `tests/agents/`), not deferred to Phase 7

**Endpoints added this phase:** 3 (total: 4 with `/health`)

**Verification:**

This is the first phase where Phase 3's `require_api_key` actually guards a real route —
confirm the full 401/403/200 behavior against one of them (all three share the identical
dependency, so once is representative, not three repetitions of the same check):

```bash
# Missing key → 401
curl -i http://localhost:8080/trade/suggestions
# → HTTP/1.1 401

# Wrong/unknown key → 403
curl -i -H "X-API-Key: wrong" http://localhost:8080/trade/suggestions
# → HTTP/1.1 403

# Correct key → 200, reasoning over THAT tenant's own platform_db_url
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8080/trade/suggestions?user_id=user_001"
```

And the actual functionality across all three new routes:

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
- Write `tests/api/test_offers_endpoints.py` and `tests/api/test_query_endpoints.py` for these
  four routes as part of this phase, same reasoning as Phase 4

**Endpoints added this phase:** 4 (total: 8)

**Verification:**

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/offers?user_id=user_001"

curl -X POST http://localhost:8080/offers/send \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sender_id":"user_001","recipient_id":"user_002",
       "offered_pokemon":"Eevee","requested_pokemon":"Vaporeon"}'

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

**Do this right after Phase 3, before Phase 4/5 — earlier than its number suggests.**
Technically it only needs the FastAPI `app` object, which has existed since Phase 1; there's
no hard dependency on the trade endpoints existing first. Phase 3 is exactly the kind of logic
— tenant lookup, 401/403 auth failures, encrypt/decrypt round-trips — worth having structured
logging in place *while* debugging it, not retrofitted after three more phases of building
blind. Same reasoning as Phase 12/18 already being flagged as earlier-than-numbered.

**Goal:** Wire HTTP request tracing into the existing Logfire + OpenTelemetry stack so every
API call appears in the Phoenix dashboard alongside agent spans — plus dedicated error
tracking, which tracing alone doesn't give you.

**Why:** The project already instruments agent calls via `openinference-instrumentation-pydantic-ai`
and exports traces to Phoenix (`src/observability/`). Without this phase, HTTP-level context
(method, path, status, latency) is invisible in those traces. Separately, Phoenix/Logfire show
you trace *spans* — what a request did — not a dedicated, alertable view of *new* unhandled
exceptions, which is a different job.

**Tooling, chosen for free/low-cost tiers, not just defaults:**

- **Logfire** — already free-tier-friendly for this project's volume, and ships FastAPI
  instrumentation out of the box (no new dependency).
- **Phoenix** — self-hosted, fully open-source, genuinely free regardless of volume (already
  running via `docker-compose.yml`'s `observability` profile).
- **Sentry** (new to this phase) — dedicated error tracking and alerting on *new* exception
  types, which trace viewers don't really do. Checked its current pricing directly rather than
  assuming: the free "Developer" tier gives 5,000 errors/month, 5M trace spans, and even **1
  free uptime monitor** — small enough overlap with Phase 26 that it's worth checking whether
  Sentry's free monitor covers that need before also paying for a separate uptime tool.

**Tasks:**

- Add `logfire.instrument_fastapi(app)` in `src/api/app.py` after the app is created
- Add a lightweight logging middleware to `src/api/app.py` that writes one structured
  line per request: method, path, status code, and duration in ms
  - Use Python's stdlib `logging` (already used throughout the project)
  - Format: `POST /chat 200 342ms`
- Add Sentry's Python SDK, initialized in `src/api/app.py`'s lifespan, scoped to the free tier's
  limits (single project, no need for its paid integrations yet)
- Verify traces appear in Phoenix at `http://localhost:6006` when `ENABLE_PHOENIX=true`, and a
  deliberately-raised test exception appears in Sentry
- Write a small `tests/api/test_logging_middleware.py` for the request-logging middleware
  itself (method/path/status/duration line gets written) as part of this phase

**Verification:**

```bash
# Start with Phoenix enabled
ENABLE_PHOENIX=true make run-api

# Make a request
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8080/trade/suggestions?user_id=user_001"

# Check server logs show the request line
# Check Phoenix at http://localhost:6006 shows the trace with agent sub-spans
# Trigger a deliberate error and confirm it appears in the Sentry dashboard
```

---

## Phase 7 — API Test Gaps & Integration Coverage

**Originally scoped as "write all the API tests here" — that was the wrong design, not
just a Phase 3 oversight.** Every other module in this project (agents, cli, memory, ...) has
tests written alongside its own code, not batched into one dedicated testing phase at the end.
Phases 3–6 now each write their own tests as part of that phase (`tests/api/test_tenants.py`,
`test_auth.py`, `test_trade_endpoints.py`, `test_offers_endpoints.py`, `test_query_endpoints.py`,
`test_logging_middleware.py`). This phase is what's left *after* that: gaps and
integration-level coverage that don't naturally belong to any single phase.

**Goal:** Full-stack integration tests exercising multiple phases together, plus anything the
per-phase tests reasonably left out.

**Tasks:**

- An end-to-end test hitting a realistic sequence across routes — e.g. provision a tenant,
  send an offer, fetch it back via `GET /offers`, confirm the AI analysis is present —
  something no single phase's own tests would naturally cover in isolation
- Audit `tests/api/` against the endpoint table in Phase 8 — confirm every route has at least
  one test, and file gaps here rather than assuming
- Any cross-cutting auth edge cases not covered by Phase 3's own tests (e.g. a tenant's key
  working correctly across *every* route type, not just the one Phase 3 tested it against)

**Verification:**

```bash
make test
# → tests/api/ tests all pass, full suite still green
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

## Phase 13 — Managed PostgreSQL Provisioning (Default Database Option)

**Goal:** Let a tenant register without bringing their own `PLATFORM_DB_URL` — provision a
dedicated managed Postgres database for them automatically, using the exact same schema
contract self-hosted tenants use (`docs/REFERENCE/PLATFORM_DB.md`), so there's one code path
either way. Per your direction, this becomes the **default** choice at registration — bringing
your own database becomes the opt-out, not the opt-in.

**Requires explicit disclosure, not just a technical default:** the whole point of encouraging
the managed option is so tenant data lives on infrastructure you control — which only becomes
Phase 14's cross-tenant analytics if tenants have actually agreed to that. A checkbox default
doesn't substitute for a terms-of-service / privacy-policy tenants see and accept. Phase 16 is
where those actual pages get built — this phase links to them, not duplicates them.

**Database hosting and analytics consent are two separate toggles, not one.** Where a tenant's
database lives (`use_managed_db`) and whether their data feeds Phase 14's cross-tenant
analytics (`analytics_opt_in`) don't have to be the same decision. You already receive a
self-hosted tenant's `platform_db_url` and use it on every request regardless — there's no
technical reason to hard-exclude opted-in self-hosted tenants from analytics, only a consent
one, and consent is exactly what an explicit second flag is for. Sensible defaults, both
tenant-overridable given the same disclosure either way: `analytics_opt_in` defaults `true` for
managed tenants (matching the stated intent of that option), `false` for self-hosted ones
(matching the more private-by-default posture of bringing your own database).

**Migrate `TENANT_DB_ENCRYPTION_KEY` to envelope encryption via cloud KMS here, not later.**
Phase 3's single static Fernet key is a reasonable pre-launch starting point, but it's a real
single point of failure: one leak decrypts every tenant's `platform_db_url` at once, one loss
destroys every tenant's at once, and there's no way to rotate it without a risky decrypt-and-
re-encrypt-everything operation. This phase is the natural point to fix that — you're standing
up real cloud infrastructure for managed Postgres anyway, so adopting that same provider's KMS
(AWS KMS, GCP Cloud KMS, or Vault) is a small incremental step, not a separate project:

- Each tenant's `platform_db_url` gets its own randomly-generated Data Encryption Key (DEK).
  The KMS's master key never leaves the KMS — it's used only to "wrap" (encrypt) each tenant's
  DEK, and it's the *wrapped* DEK that gets stored in `tenants.db`, not a key that can decrypt
  everyone at once.
- Decrypting a tenant's URL means asking the KMS to unwrap that one DEK — an authenticated,
  logged API call, not a local operation — so you also get a real audit trail ("who/what
  decrypted tenant X's credentials, and when") that the current design has no equivalent of.
- Key rotation becomes tractable: rotate the KMS master key and re-wrap the (small) DEKs,
  instead of decrypting and re-encrypting every tenant's actual data by hand.
- `_get_fernet()` (Phase 3) gets replaced by an envelope-encryption equivalent in
  `api/tenants.py`; existing rows need a one-time migration (decrypt with the old static key,
  re-encrypt via the new per-tenant DEK path) rather than a schema change.

**Design:**

- One Postgres **server**, one **database per tenant** (not a shared database with a
  `tenant_id` column) — isolation by default: a bug or bad query affecting one tenant's data
  can't touch another's. Doesn't block Phase 14's cross-tenant analytics, which reads across
  many tenant databases via ETL regardless of how they're separated.
- A managed cloud Postgres (RDS, Cloud SQL, Supabase, etc.) rather than self-hosting the
  `postgres` service from `docker-compose.yml` for this — that service is a dev convenience;
  other people's data now needs real backups and durability guarantees.
- Schema migration: a SQL migration script (the exact schema from `PLATFORM_DB.md`) runs
  automatically against each new tenant database at provisioning time — `create_tenant()`
  (Phase 3) gains a `managed: bool` path that provisions the database first, then stores the
  resulting connection string exactly like a self-hosted one (encrypted, same `tenants` table).
- Phase 10's `POST /accounts/register` gains a `use_managed_db: bool` field (**defaulting to
  `true`**, per your direction) — when true, `platform_db_url` in the request is ignored/omitted
  entirely and a database is provisioned instead — plus the independent `analytics_opt_in: bool`
  field described above.
- Sets up Phase 15 naturally: a paid tier can later mean "your own dedicated Postgres instance"
  vs. free tier's shared server, many-databases model.

**Tasks:**

- Choose and provision a managed Postgres provider/account (outside this repo's scope to pick
  for you — cost and existing cloud relationships matter here)
- Write the tenant-database provisioning function: create database, run schema migration,
  return the connection string
- Extend `create_tenant()` (Phase 3) and `POST /accounts/register` (Phase 10) with the
  `use_managed_db` and `analytics_opt_in` fields
- Link the registration flow to Phase 16's Privacy Policy / Terms pages — the actual disclosure
  tenants see and accept, not duplicated here
- Add a database-per-tenant quota/cleanup story for deactivated tenants (Phase 11's
  deactivate action) — decide whether a deactivated tenant's managed database is dropped,
  retained, or archived
- Migrate `TENANT_DB_ENCRYPTION_KEY` to KMS-backed envelope encryption: set up the KMS master
  key, implement per-tenant DEK generation/wrapping, migrate existing `tenants.db` rows from
  the Phase 3 static-key scheme, and write down the actual rotation procedure (not just that
  one should exist)

**Verification:**

```bash
curl -X POST https://<your-public-domain>/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"name": "new-tenant"}'
# → {"api_key": "<shown once>", "tenant_id": "...", "database": "managed"}

# Confirm the provisioned database actually has the full schema:
psql "<the provisioned connection string>" -c "\dt"
# → trades, user_pokemon, user_preferences, user_trade_history, trade_offers

# Confirm envelope encryption is actually in effect post-migration — no single
# key in tenants.db (or anywhere in app config) can decrypt more than one tenant:
sqlite3 data/tenants.db "SELECT platform_db_url_encrypted FROM tenants LIMIT 2"
# → each row's wrapped DEK differs; decrypting one via the KMS doesn't yield the other

# Rotate the KMS master key and confirm existing tenants still resolve correctly afterward
```

---

## Phase 14 — Cross-Tenant Analytics via ClickHouse

**Goal:** Platform-wide insights ("which Pokemon are trending across every tenant this week")
fed from every tenant database that's actually opted in, using ClickHouse as the analytics layer.

**Why ClickHouse specifically:** the tenant-facing schema in `PLATFORM_DB.md` is an OLTP
workload — point lookups by `user_id`, and `trade_offers` needs real row-level UPDATEs — which
ClickHouse handles poorly (its `ALTER TABLE ... UPDATE` is an async batch "mutation," not a
routine per-row write). It's the right tool for a different job: append-heavy aggregation over
large volumes, which is exactly what cross-tenant trend analysis is. That's why this is a
separate, additive layer fed *from* Postgres, not a replacement for it.

**Scope boundary — this is the load-bearing part:** this pipeline only reads from tenants with
`analytics_opt_in == true` (Phase 13), regardless of whether their database is managed or
self-hosted — hosting location and analytics consent are independent flags, not the same
decision (see Phase 13's design note). A tenant who hasn't opted in never has their data touch
this pipeline at all, no matter where their database lives.

**Design:**

- Add a `clickhouse` service to `docker-compose.yml`, behind a new `analytics` profile —
  matching the existing `observability`/`platform-db` profile pattern.
- A scheduled ETL job (nightly cron, or a simple scheduled script) connects to each
  `analytics_opt_in` tenant's database — managed or self-hosted, using the same
  `platform_db_url` already on file for either — and appends new rows into a denormalized
  ClickHouse fact table — e.g.
  `trades_fact(tenant_id, traded_at, offered_pokemon, requested_pokemon, status, ...)` — rather
  than querying live tenant databases directly for analytics (keeps analytical query load off
  the OLTP databases actually serving trade requests).
- A read path for the aggregated data — initially internal/admin-only (queried from Phase 11's
  admin web UI), with a public `/market/insights`-style endpoint as a later, natural Phase 15
  paid-tier feature rather than something every tenant gets by default.

**Tasks:**

- Add `clickhouse` to `docker-compose.yml` under the `analytics` profile
- Write the ETL script: per-opted-in-tenant extraction into the shared ClickHouse fact table
- Schedule it (cron, or a scheduled GitHub Actions workflow / external scheduler)
- Add a query module (e.g. `src/analytics/clickhouse_client.py`) exposing the aggregate queries
  the platform actually wants (trending Pokemon, tier distribution shifts, etc.)
- Surface a first read of this data in Phase 11's admin web UI before exposing it publicly

**Verification:**

```bash
docker compose --profile analytics up -d clickhouse
uv run python scripts/run_analytics_etl.py   # or whatever the ETL entrypoint ends up named
# → confirms rows land in ClickHouse for each opted-in tenant, none for opted-out ones —
#   test both a managed and a self-hosted tenant with analytics_opt_in=true

# Query the aggregate directly to sanity-check the ETL:
docker compose exec clickhouse clickhouse-client \
  --query "SELECT offered_pokemon, count() FROM trades_fact GROUP BY offered_pokemon ORDER BY count() DESC LIMIT 10"
```

---

## Phase 15 — Account Plans (Free & Paid Tiers)

**Goal:** Differentiate tenant capability by plan, and monetize the public API.

**Design:**

- Extend the `tenants` table (Phase 3) with a `plan` column (`free` | `paid` to start — leave
  room for more tiers later rather than hardcoding a boolean).
- **Free tier**: rate-limited (requests/day), managed-database tenants share the pooled
  Postgres server from Phase 13, no access to Phase 14's aggregate market-insights endpoint.
- **Paid tier**: higher/no rate limits, a **dedicated** managed Postgres instance instead of a
  shared server (a direct, natural use of Phase 13's per-tenant-database design — "dedicated
  database" becomes a concrete paid-tier feature, not just an isolation detail), and access to
  Phase 14's `/market/insights` endpoint as a premium feature.
- Billing via Stripe (or an equivalent processor) — hosted Checkout for the actual payment
  flow, webhooks for subscription created/upgraded/downgraded/cancelled events updating the
  tenant's `plan` column. This is ordinary SaaS billing integration code — building the
  webhook handlers and checkout flow isn't something I'd hold back on — but the Stripe account,
  pricing, and business terms are yours to set, not something to default here.
- Rate limiting (mentioned as a nice-to-have back in Phase 9/10) becomes a real requirement
  here, since it's now how free-tier limits are actually enforced, not just abuse prevention.

**Tasks:**

- Add `plan` (and any plan-specific limit fields) to the `tenants` schema
- Set up a Stripe account, products/prices for the paid tier
- Add `POST /billing/checkout` (redirects to Stripe Checkout) and `POST /billing/webhook`
  (verifies Stripe's signature, updates `plan` on subscription events)
- Implement rate limiting keyed by tenant + plan (a reverse-proxy layer or in-app middleware —
  whichever fits wherever Phase 9 actually deploys this)
- Gate Phase 14's `/market/insights` endpoint behind `plan == "paid"`
- Surface plan and usage in Phase 11's admin web UI

**Verification:**

```bash
# Free-tier tenant hits the rate limit:
for i in $(seq 1 200); do curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-API-Key: <free-tier-key>" https://<domain>/trade/suggestions; done | sort | uniq -c
# → some requests eventually return 429

# Paid-tier tenant can reach the insights endpoint; free-tier cannot:
curl -i -H "X-API-Key: <paid-tier-key>" https://<domain>/market/insights   # → 200
curl -i -H "X-API-Key: <free-tier-key>" https://<domain>/market/insights  # → 403
```

---

## Phase 16 — Marketing/Signup Website & Launch Checklist

**Goal:** A real product website — distinct from Phase 12's GitHub Pages docs site — covering
signup, pricing (Phase 15), and the legal pages Phase 13 already links to. Phase 12 renders
existing docs as-is; this phase is new, purpose-built content: a landing page, a pricing page,
the registration flow's front end, and the Privacy Policy / Terms of Service tenants actually
read and accept.

**This is the concrete home for Phase 13's disclosure requirement** — the Privacy Policy here
is where "what managed-tenant and opted-in data is used for" actually gets written down and
shown to a tenant before they accept it, not a task deferred indefinitely.

**Tasks**, grouped and adapted from a general pre-launch checklist to what actually applies here:

*Legal & compliance:*
- Privacy Policy page — covers what tenant data is collected, how `analytics_opt_in` data
  feeds Phase 14, and how managed-database hosting (Phase 13) works
- Terms of Service page — API usage terms, billing terms for Phase 15's paid tier

*Security:*
- Secrets off the frontend — no API keys, Stripe secret keys, or admin tokens ever reach
  client-side code on this site (the registration flow only ever talks to `POST
  /accounts/register`, which returns a key to display once, not embed in page source)
- Force HTTPS (already required by Phase 9 for the API; applies here too)

*Discoverability & SEO:*
- Meta titles + descriptions, per page
- Social preview image (Open Graph) for link sharing
- Favicon
- Sitemap + `robots.txt`
- Alt text on images

*Performance & accessibility:*
- Compress images
- Check page load speed (Lighthouse or similar)
- Fix color contrast (WCAG)
- Mobile-friendly / responsive layout
- Custom 404 page
- Fix broken links (a QA pass before launch)

*Conversion:*
- Form validation on the signup form
- Spam/abuse protection on signup — the same concern Phase 10's `POST /accounts/register`
  already flags as needing rate limiting; a CAPTCHA or honeypot on the front-end form is the
  other half of that
- Site analytics (visits, signup conversion) — a *different* thing from Phase 14's product
  analytics: this is ordinary web analytics for the marketing site itself (e.g. Plausible or
  similar), not tenant trade data
- One clear call to action (e.g. "Get your API key") — cookie consent banner only needed if
  this analytics tool or anything else on the site actually sets non-essential cookies

**Verification:**

```bash
# Lighthouse (or equivalent) audit before launch:
npx lighthouse https://<your-site> --view
# → checks performance, accessibility, SEO, best-practices scores together

# Confirm no secrets leak into shipped frontend code:
curl -s https://<your-site> | grep -iE "sk_live|api[_-]?key|secret"
# → no matches
```

---

## Phase 17 — Security Hardening

**Goal:** Systematic security hardening across transport, application, and infrastructure
layers, prioritized by what's load-bearing for a public multi-tenant API versus genuine
defense-in-depth. Cross-references [OWASP's cheat sheet
series](https://cheatsheetseries.owasp.org/index.html) per item rather than treating "read
OWASP" as one task — it's a reference library, not a checklist itself.

**Two things already checked against the real codebase, not assumed:**
- **SQL injection — already safe.** Every query in `src/data/platform_db.py` uses psycopg's
  `%s` parameterized placeholders, never string interpolation (verified across all 9
  `cur.execute()` calls). The task below is keeping this true as Phase 13/15 add more queries,
  not fixing something broken.
- **The Docker container runs as root.** No `USER` directive in `Dockerfile` — a real, current
  gap, independent of any other phase.

### P0 — required before Phase 9's public deployment, not optional hardening

- **TLS/HTTPS sitewide** — already Phase 9's requirement; restated here as a security
  baseline, not a new task. (OWASP: [Transport Layer Protection Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html))
- **Rate limiting / DoS protection** — Phase 9/15 currently list this as a nice-to-have;
  elevate it to required. A genuinely public, unauthenticated-until-keyed surface (plus Phase
  10's registration endpoint, reachable with *no* key at all) is a realistic abuse target from
  day one. (OWASP: [Denial of Service Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html))
- **Input validation at every boundary** — Phase 2's Pydantic request models already provide
  this; the task is discipline, not new code: every future endpoint validates through a typed
  model, never a raw dict. (OWASP: [Input Validation Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html))
- **SQL injection prevention** — verified safe above; task is a review-checklist line item
  for any new query code (Phase 13's provisioning, Phase 14's ETL, Phase 15's billing), not a
  fix. (OWASP: [SQL Injection Prevention Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html))
- **Secrets management** — largely built already: Phase 3's Fernet-encrypted
  `platform_db_url`, env-var-only secrets, nothing committed in plaintext. Formalize as an
  explicit review point rather than assuming it stays true by default. (OWASP: [Secrets
  Management Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html))

### P1 — land shortly after launch, not blocking it

- **Non-root Docker user** — confirmed gap above; add a `USER` directive to `Dockerfile`. Small
  and isolated enough to do independent of phase sequencing. (OWASP: [Docker Security Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html))
- **HTTP security response headers** — HSTS, hiding the `Server:` version header, `X-Content-
  Type-Options: nosniff`, and similar — mostly configured once at Phase 9's reverse-proxy
  layer rather than per-endpoint. (OWASP: [HTTP Security Response Headers Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html))
- **Secure + HttpOnly cookies, CSRF protection** — not applicable to the tenant-facing API
  itself (stateless, API-key only, no cookies) — only relevant once *any* cookie-based session
  exists: Phase 11's admin web UI, or a future tenant dashboard in Phase 16. Scope the task to
  whichever of those actually ships first. (OWASP: [Session Management Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
  [Cross-Site Request Forgery Prevention Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html))
- **TLS certificate expiry monitoring** — most managed platforms (Let's Encrypt via Caddy,
  Fly.io, Render) auto-renew, but silent auto-renewal failure is a real failure mode worth an
  explicit alert, not just trust.

### P2 — ongoing hardening, not one-time tasks

- **Explicit cipher suite verification** — check via an SSL Labs (or equivalent) scan rather
  than assuming the reverse proxy's defaults are sufficient; re-check periodically, since
  "secure today" doesn't mean "secure in a year" as ciphers age out.
- **Recurring security review cadence** — this environment already has a `security-review`
  skill available; run it before releases that touch auth/payment/data-access code (Phases 3,
  13, 15 especially), not just once at the end of this whole roadmap.

**Tasks:**

- Add `USER` directive to `Dockerfile` (P1, no dependency on other phases — can happen now)
- Add rate limiting to Phase 9/15's deployment (promote from "nice to have" to required)
- Add a query-safety note to `CONTRIBUTING`-style guidance (or a lint rule, if one exists for
  this) flagging string-interpolated SQL as a blocker in review
- Configure HSTS + security headers at the Phase 9 reverse-proxy layer
- Set up TLS expiry monitoring/alerting once Phase 9's domain exists
- Schedule recurring `security-review` runs tied to Phases 3/13/15 landing, not just ad hoc

**Verification:**

```bash
# Confirm the container doesn't run as root once the Dockerfile fix lands:
docker run --rm ghcr.io/jazicorn/pokemon-trainer-platform-ai:latest whoami
# → NOT "root"

# External TLS/header scan once Phase 9's domain exists:
curl -sI https://<your-public-domain>/health | grep -iE "strict-transport-security|server:"
# → HSTS present, Server header absent or generic (not leaking framework/version)
```

---

## Phase 18 — Interim Landing Page (Roadmap + Newsletter Signup)

**Despite the number, treat this as early work, not late.** It depends only on Phase 12's
GitHub Pages setup existing — nothing from Phases 2–17. Phase 16's full marketing/signup site
is a long way off, since it needs most of the API actually built first; this exists to close
that gap, so it belongs right alongside or shortly after Phase 12, not at the end of the list.

**Goal:** A minimal public page — the roadmap, in readable form, plus an email signup for
updates — so there's *something* to point people at and start building an audience during the
gap before Phase 16 exists, rather than nothing at all until then.

**Design:**

- Reuse Phase 12's MkDocs/GitHub Pages site rather than standing up separate hosting — this
  can be that site's homepage, with `ROADMAP.md` rendered below the fold (Phase 12 already
  renders it as its own page; surface it prominently here too).
- Email capture needs *some* backend, and GitHub Pages is static-only. For a stopgap like this,
  don't build custom infrastructure for it — use an existing newsletter provider (Buttondown,
  ConvertKit, ListMonk, etc.) with a simple embeddable form. The tradeoff is real (your
  subscriber data lives on their platform, not yours) but building a custom signup backend for
  something explicitly meant to be temporary is over-engineering the wrong thing. Revisit if
  Phase 16 wants to own this list directly later — exporting from any mainstream provider is
  standard.
- Needs a one-line privacy note next to the signup form (what the email is used for, how to
  unsubscribe) — a lightweight preview of Phase 16's real Privacy Policy, not a substitute for
  it once that exists.

**Tasks:**

- Pick a newsletter provider and create the list
- Add the landing content + embedded signup form to Phase 12's MkDocs site
- Add the one-line privacy note near the form
- Link it from the main README

**Verification:**

```bash
uv run mkdocs serve
# → homepage shows roadmap summary + signup form, both render correctly

# Submit a test signup, confirm it actually lands in the provider's list
# (manual check — this is a third-party integration, not something to script here)
```

---

## Phase 19 — Backups & Disaster Recovery

**Goal:** Tenant data survives infrastructure failure, with a *tested* restore path — not just
an assumption that the managed Postgres provider "probably handles it."

**Design:**

- Enable the managed Postgres provider's (Phase 13) automated snapshots, with an explicit
  retention window and point-in-time recovery if the provider offers it.
- `data/tenants.db` (Phase 3's SQLite tenant/API-key store) is a **separate** risk — it's not
  in managed Postgres, it's a local file on whatever host runs the API. Losing it means every
  tenant loses the ability to authenticate, even if their own trade data in Postgres is fine.
  Needs its own backup (periodic snapshot to object storage), independent of the Postgres story.
- Document RPO (how much data loss is acceptable) and RTO (how long a restore takes) explicitly
  — "we don't know" is the actual current answer, and that's the gap this phase closes.
- Actually perform one test restore into a scratch environment and write down what happened —
  an untested backup is a hypothesis, not a plan.

**Tasks:**

- Enable and configure automated Postgres backups/retention on the Phase 13 provider
- Set up periodic backup of `data/tenants.db` to object storage
- Write a restore runbook
- Perform one real test restore; record actual timing against the documented RTO

**Verification:**

```bash
cp data/tenants.db /tmp/tenants-backup-test.db
rm data/tenants.db
# follow the restore runbook
cp /tmp/tenants-backup-test.db data/tenants.db
# confirm a known tenant's API key still authenticates afterward
```

---

## Phase 20 — Per-Tenant Cost/Usage Tracking

**Goal:** Track real LLM spend per tenant — independent of Phase 15's request-count rate
limiting, which caps *how often* someone calls the API, not *how much each call costs*.

**Why this is a separate concern from rate limiting:** a free-tier tenant sending long
conversations could rack up real API spend well before hitting a request-count limit. Verified
this is straightforward to build, not speculative: every `pydantic-ai` agent run already
returns a `RunUsage` via `result.usage()` (input/output/cache tokens, request count), and
`genai_prices` — already installed as a `pydantic-ai` dependency — maintains a real,
cross-provider pricing snapshot to convert that into actual dollar cost. No need to hand-roll
or hand-maintain a pricing table that goes stale the moment a provider changes prices.

**Design:**

- Capture `result.usage()` after every `trade_advisor.run()` call (in
  `agents/trade_advisor_api.py`), tagged by `tenant_id`, and persist a running total (new table
  — `tenants.db` or a dedicated `usage` table, resettable per billing period).
- Convert usage to cost via `genai_prices` rather than a hand-maintained table.
- Free tier: hard cap — block further requests once the period budget is hit, with a clear
  4xx response naming the limit, not a generic failure.
- Paid tier: soft cap — alert, don't block (they're paying for what they use).
- Tenant-facing `GET /account/usage` so tenants see their own consumption without asking you,
  plus a surfaced view in Phase 11's admin web UI.

**Tasks:**

- Wire usage capture into every agent-run call site
- Add the usage-tracking table/schema
- Integrate `genai_prices` for cost conversion
- Enforce the free-tier hard cap; implement the paid-tier alert
- Add `GET /account/usage` and the Phase 11 admin surface

**Verification:**

```bash
curl -H "X-API-Key: <free-tier-key>" -X POST https://<domain>/v1/chat -d '...'
# repeated until the period budget is hit
# → a clear "usage limit reached" response, not a generic 500 or silent overspend

curl -H "X-API-Key: <key>" https://<domain>/account/usage
# → {"tokens_used": ..., "estimated_cost_usd": ..., "period": "..."}
```

---

## Phase 21 — API Versioning Strategy

**Goal:** Introduce versioning *before* any external tenant integrates, so a future breaking
change doesn't silently break existing integrations — retrofitting versioning onto a live API
with real callers is far more painful than deciding this now, while there are still zero of them.

**Design:**

- URL-path versioning (`/v1/chat`, `/v1/trade/evaluate`, ...) — simplest and most discoverable
  for API consumers, versus a header-based scheme.
- `/health` stays unversioned — it's infrastructure-level, not business logic, matching its
  existing exemption from API-key auth (Phase 3).
- Decide (not necessarily exercise yet) a deprecation policy: how long `/v1` stays supported
  once a `/v2` exists.

**Tasks:**

- Mount Phase 4/5's routes under an `APIRouter(prefix="/v1")` in `src/api/app.py`
- Update all docs/examples (Phase 8, Phase 16, any client code) to the `/v1/...` paths
- Write a short versioning/deprecation policy doc

**Verification:**

```bash
curl -H "X-API-Key: $KEY" https://<domain>/v1/trade/suggestions   # → 200
curl https://<domain>/trade/suggestions                            # → 404, forcing explicitness
```

---

## Phase 22 — Dependency & Vulnerability Scanning

**Goal:** Automated detection of vulnerable dependencies, using tooling that's free on GitHub
and hasn't come up despite Phase 17's whole focus on security.

**Tasks:**

- Add `.github/dependabot.yml` for the `pip` (uv-compatible) and `github-actions` ecosystems —
  security alerts plus version-update PRs
- Add a `pip-audit` step to `ci-quality.yml`
- Decide the policy: block CI on critical/high findings, warn (don't block) on medium/low

**Verification:**

```bash
uv run pip-audit
# → 0 known vulnerabilities, or a clear actionable list
```

Also confirm Dependabot opens its first PR automatically once the config is merged.

---

## Phase 23 — Client SDKs

**Goal:** Lower integration friction for tenants with a thin client wrapping the versioned API
(Phase 21) — directly relevant to the original "would I be calling the FastAPI endpoints from
my platform's backend" question this whole roadmap started from.

**Design:**

- FastAPI generates a complete OpenAPI spec for free from Phase 2's Pydantic models
  (`/openapi.json`) — generate a client from that (e.g. via `openapi-python-client`) rather
  than hand-writing and hand-maintaining every method.
- A Python client first; a TypeScript client is a natural second target if the sister
  platform's own React frontend ever wants to call this API more directly than through its
  backend.

**Tasks:**

- Confirm the generated OpenAPI spec is complete and accurate against Phase 2's models
- Generate (or hand-write, if generation proves awkward) a Python client package
- Consider a TypeScript client once there's a concrete consumer for it

**Verification:**

```python
from pokemon_trade_advisor_client import Client
client = Client(api_key="...", base_url="https://<domain>")
result = client.evaluate_trade(offered_pokemon="Pikachu", requested_pokemon="Charizard")
```

---

## Phase 24 — Outbound Webhooks

**Goal:** Let tenants receive events (e.g., "trade offer analysis complete") instead of polling
`GET /offers`.

**Design:**

- Tenant registers a webhook URL (new field on `tenants`, or a dedicated `webhooks` table for
  multiple event subscriptions).
- Signed payload delivery — HMAC using a per-tenant secret, so tenants can verify authenticity,
  the same pattern Stripe itself uses for its own webhooks (fitting, given Phase 15 already
  integrates Stripe).
- Fire-and-forget with retry/backoff — never block the triggering request on webhook delivery.

**Tasks:**

- Add webhook URL + secret fields to tenant config (surfaced in Phase 11's admin UI)
- Implement signed delivery + retry logic
- Document the payload schema and signature verification for tenants

**Verification:**

```bash
# Using a local test receiver or a tool like webhook.site:
# trigger an offer analysis, confirm a signed POST arrives with the expected event payload
```

---

## Phase 25 — Staging Environment

**Goal:** A pre-production environment mirroring Phase 9's real deployment, so changes touching
tenant data or billing get exercised before they reach real tenants.

**Design:**

- A second instance of the same image (Phase 9), not a separate codebase — separate
  `TENANT_DB_ENCRYPTION_KEY`, separate managed Postgres instance, Stripe **test-mode** keys.
- Decide the promotion flow deliberately: auto-deploy every merge to staging, with production
  requiring a manual trigger/approval, is a reasonable default — but this is a real process
  decision, not something to default silently.

**Tasks:**

- Stand up a second Phase 9 deployment target pointed at staging config
- Implement the chosen promotion flow
- Use Stripe test-mode keys in staging so Phase 15 billing can be exercised safely

**Verification:**

```bash
curl https://staging.<your-domain>/health
# → confirms staging is live and isolated from production tenant data
```

---

## Phase 26 — Status Page & Uptime Monitoring

**Goal:** External visibility into uptime for tenants, and alerting for you when something is
actually down — from outside your own infrastructure, so it still works when that infrastructure
doesn't.

**Design:**

- An external uptime monitor (UptimeRobot, Better Uptime, etc. — free tiers exist) hitting the
  public `/health` endpoint on a schedule, alerting you on failure.
- A public status page (many uptime tools include a hosted one) linked from Phase 16's site and
  Phase 18's interim landing page.

**Tasks:**

- Set up an external monitor against `/health`
- Configure alerting to wherever you actually want to be notified
- Link the public status page from Phases 16 and 18

**Verification:**

```bash
# In a safe/staging context, temporarily return non-200 from /health and confirm
# the monitor actually fires an alert within its configured check interval.
```

---

## Phase 27 — LLM Provider Fallback

**Goal:** Graceful degradation if the primary LLM provider has an outage, using multi-provider
support `src/config.py` already has (Ollama, OpenAI, Gemini alongside Anthropic).

**No need to hand-roll this:** `pydantic_ai.models.fallback.FallbackModel` already exists and
does exactly this — retries against a secondary model if the primary fails — confirmed present
in this project's installed `pydantic-ai` version. This phase is wiring it in and deciding
policy, not building new retry logic.

**Design:**

- Wrap `trade_advisor`'s model in a `FallbackModel` chain: primary provider, then a configured
  secondary (e.g. Anthropic → OpenAI, or → a local/cloud Ollama model already supported).
- Treat this as a **paid-tier** differentiator (Phase 15) — the free tier can reasonably just
  fail during a primary-provider outage; reliability is a fair thing to charge for.

**Tasks:**

- Configure a `FallbackModel` chain using existing `ModelConfig` entries
- Gate fallback behavior behind `plan == "paid"`
- Document which provider is primary vs. fallback, and why

**Verification:**

```bash
# Simulate primary provider failure (e.g. temporarily invalid ANTHROPIC_API_KEY in a test env)
# and confirm a paid-tier request still succeeds via the fallback provider.
```

---

## Phase 28 — Support Tooling

**Set this up before Phase 10 ships, not after.** Self-serve registration means strangers can
become tenants without you ever touching the process — the first one who hits a problem
shouldn't be the reason you're scrambling to set up a support inbox that day.

**Goal:** A working support channel ready before self-serve signup goes live, sized to actual
early-stage volume rather than to what a support team would eventually need.

**Tool: Plain (joinplain.com).** Built specifically for B2B/API companies talking to technical
users — Slack-based triage, issue-linking — which fits this audience (developers integrating
against an API) better than a general-purpose shared inbox. Help Scout remains the fallback if
Plain's workflow ends up being more than needed day one: simpler, more generic, also cheap.

**Tasks:**

- Set up a Plain account and connect the support address (e.g. `support@<your-domain>`)
- Link it from Phase 16's marketing site and Phase 18's interim landing page
- Revisit around Phase 15 (paid tiers) — billing questions (refunds, disputes, "why was I
  charged") raise support expectations; re-evaluate whether Plain still fits or whether it's
  time to consider a heavier tool, rather than assuming the day-one choice holds forever

**Verification:**

```bash
# Send a real test email to the support address and confirm it lands in the shared inbox
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
