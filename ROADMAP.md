# Roadmap: Web API

Convert the Pokemon Trainer Platform from a CLI + MCP server into a full HTTP web API using
FastAPI, while keeping the existing CLI and MCP interfaces intact.

Covers Phases 1-11 — the API itself: dependencies through admin tooling. What happens once
it's real (hosting, billing, the public website, security, ops maturity, growth) continues in
[ROADMAP_PLATFORM.md](ROADMAP_PLATFORM.md), Phases 12 onward. Phase numbers are shared and
continuous across both files, not reset.

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

**This phase isn't done until its security checklist passes too, not just deployment
mechanics.** These five items were originally written up as ROADMAP_PLATFORM.md Phase 17's
"P0 — required before Phase 9" tier — but a security checklist that only *lives* in a later,
separate phase is exactly the mistake this project already made once with testing (the
original Phase 3/Phase 7 split, where a separate later "testing phase" let Phase 3 look done
without ever having tests). Moved here for the same reason: nothing should be able to call
this phase complete without them.

**Tasks:**

- Add a long-running `api` service to `docker-compose.yml` (alongside the existing `chromadb`,
  `phoenix`, `postgres`, `app` services) — `docker compose up api`, not `run --rm` like the
  interactive CLI's `app` service:
  - `command: uv run python api_server.py` (overrides the image's CLI `CMD`)
  - `healthcheck` against `GET /health`, matching the `chromadb` service's pattern
  - `volumes:` must include `./data:/app/data` (already true for `app`) so `data/tenants.db`
    (Phase 3) persists across restarts/redeploys instead of living in ephemeral container
    storage — losing this file means every provisioned tenant loses access
  - Resolve the container's non-root UID against the actual host's ownership of `./data`
    once that host is chosen (see `Dockerfile`'s own note on this) — a UID mismatch means
    the container can't write `data/tenants.db` at all; a world-writable host directory
    avoids that but is broad. `data/tenants.db` holds every real tenant's encrypted
    `platform_db_url`, so this is a real decision here, not a local-dev nicety
- Confirm `image-publish.yml`'s existing GHCR image (built for the CLI's `CMD`) still works
  for the API: since `docker-compose.yml` overrides `command:`, no separate image/Dockerfile
  is needed — same published image, different command per service
- Document the actual target host in `docs/DEPLOYMENT.md` (new) once one is chosen, covering
  how secrets (`ANTHROPIC_API_KEY`, `TENANT_DB_ENCRYPTION_KEY`) are injected as real environment
  variables via that platform's own secret store — never a committed `.env` — and where
  `TENANT_DB_ENCRYPTION_KEY`'s backup copy lives (see Phase 3's warning: losing it is
  unrecoverable, not just inconvenient)

**Security checklist (required, not optional — this phase isn't done without these):**

- **TLS/HTTPS sitewide** — a reverse proxy or the hosting platform's own load balancer in
  front, Caddy/nginx on a VPS or built-in HTTPS on Fly.io/Railway/Render/a cloud container
  service. Never expose uvicorn's plain HTTP directly to the internet. (OWASP: [Transport
  Layer Protection Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html))
- **Rate limiting / DoS protection** — required, not "consider it": a genuinely public,
  unauthenticated-until-keyed surface (plus Phase 10's registration endpoint, reachable with
  *no* key at all) is a realistic abuse target from day one, not a hypothetical one. (OWASP:
  [Denial of Service Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html))
- **Input validation at every boundary** — Phase 2's Pydantic request models already provide
  this; confirm the discipline held: every route validates through a typed model, never a raw
  dict. (OWASP: [Input Validation Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html))
- **SQL injection prevention** — already verified safe (every `platform_db.py` query uses
  psycopg's `%s` parameterization, confirmed by direct inspection, not assumption). Re-check
  this holds for any query code added since. (OWASP: [SQL Injection Prevention Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html))
- **Secrets management** — already largely built: Phase 3's Fernet-encrypted
  `platform_db_url`, env-var-only secrets, nothing committed in plaintext. Confirm it stays
  true for whatever this phase's own deployment adds. (OWASP: [Secrets Management Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html))
- **HTTP security response headers** — HSTS, hiding the `Server:` version header, `X-Content-
  Type-Options: nosniff`, and similar. Configure these at the same reverse-proxy layer as the
  TLS setup above — same file, same moment, no reason to defer something this cheap to a
  later phase. (OWASP: [HTTP Security Response Headers Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html))

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

# Confirm TLS is actually enforced — plain HTTP should not serve the API at all:
curl -i http://<your-public-domain>/health
# → connection refused, or a redirect to https://, never a 200 over plain HTTP

# Confirm rate limiting actually triggers, not just configured:
for i in $(seq 1 200); do curl -s -o /dev/null -w "%{http_code}\n" \
  https://<your-public-domain>/health; done | sort | uniq -c
# → some requests eventually return 429

# Confirm security headers are actually present, not just configured:
curl -sI https://<your-public-domain>/health | grep -iE "strict-transport-security|x-content-type-options|^server:"
# → HSTS and X-Content-Type-Options present; Server header absent or generic
#   (not leaking framework/version)
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
- **Cookie-based session, not a header** — resolved here rather than left open: this is a
  browser UI with a login form, not a machine client like the public API (which is genuinely
  header-based, `X-API-Key`). A plain HTML form can't easily attach a custom header, so a
  login page that checks `ADMIN_TOKEN` once and sets a session cookie is the realistic
  design, not a hypothetical alternative. That decision is what makes **Secure + HttpOnly
  cookie flags and CSRF protection real requirements for this phase**, not a deferred "once
  some future cookie-based feature ships" item. (OWASP: [Session Management Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
  [Cross-Site Request Forgery Prevention Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html))

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
- Create `src/admin/app.py`, `src/admin/templates/*.html`, and a `GET/POST /login` page
- Create `admin_server.py`
- Add `ADMIN_TOKEN` to `src/config.py`'s accepted env vars; `POST /login` checks it and sets
  a `Secure`, `HttpOnly`, `SameSite=Strict` session cookie — never a raw comparison against a
  header on every request
- Add CSRF protection on every state-changing route (`POST /tenants/new`, `/deactivate`,
  `/rotate-key`) — a hidden per-session token in each form, checked server-side, matching the
  OWASP CSRF cheat sheet's synchronizer-token pattern
- Add a `run-admin` Makefile target

**Verification:**

```bash
make run-admin
# → serving on http://127.0.0.1:8090 — confirm it's NOT reachable from another machine
#   (unlike make run-api, which binds 0.0.0.0)

open http://127.0.0.1:8090
# → tenant list page, prompts for ADMIN_TOKEN

# Confirm the session cookie is actually flagged correctly, not just set:
curl -i -X POST http://127.0.0.1:8090/login -d "token=$ADMIN_TOKEN" | grep -i "set-cookie"
# → Secure; HttpOnly; SameSite=Strict all present

# Confirm a state-changing request without the CSRF token is rejected:
curl -i -X POST http://127.0.0.1:8090/tenants/new -b "<session cookie from above>" \
  -d "name=test&platform_db_url=postgresql://u:p@h/db"
# → 403, missing/invalid CSRF token — not a silently-accepted request

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
