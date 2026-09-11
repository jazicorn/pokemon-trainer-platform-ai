# Roadmap: Web API

Convert the Pokemon Trainer Platform from a CLI + MCP server into a full HTTP web API using
FastAPI, while keeping the existing CLI and MCP interfaces intact.

Covers Phases 1-16 — the API itself: dependencies through admin tooling. What happens once
it's real (hosting, billing, the public website, security, ops maturity, growth) continues in
[ROADMAP_PLATFORM.md](ROADMAP_PLATFORM.md), Phases 17 onward. Phase numbers are shared and
continuous across both files, not reset.

Phases here aren't in their original numbering — four phases explicitly said, in their own
text, that their number was wrong (Observability, the Docs Site, the Interim Landing Page,
Support Tooling), and one more's own goal made the same point without saying so directly (API
Versioning must precede any real external tenant). They've been moved to where they actually
belong in the build sequence; everything else's relative order is unchanged.

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
Phase 15) once this foundation exists and is trusted.

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
  deferred to Phase 8 — every other module in this project (agents, cli, memory, ...) has tests
  written alongside its own code, and API auth logic shouldn't be the one exception. Phase 8 is
  gap-filling and integration coverage across phases, not the sole place tests get written.

**Verification:**

No route protected by `require_api_key` exists yet — that's Phase 5. A `curl` against
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

Once Phase 5 adds real routes, this same 401/403/200 behavior becomes directly
`curl`-able against them too — see Phase 5's own verification section.

---

## Phase 4 — Observability & Request Logging

**Do this right after Phase 3, before real routes exist — earlier than its original number
suggested.** Technically it only needs the FastAPI `app` object, which has existed since
Phase 1; there's no hard dependency on the trade endpoints existing first. Phase 3 is exactly
the kind of logic — tenant lookup, 401/403 auth failures, encrypt/decrypt round-trips — worth
having structured logging in place *while* debugging it, not retrofitted after building blind.

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
  free uptime monitor** — small enough overlap with Phase 27 that it's worth checking whether
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

## Phase 5 — Core Trade Endpoints

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
  used throughout `tests/agents/`), not deferred to Phase 8

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

## Phase 6 — Offers & Query Endpoints

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
  four routes as part of this phase, same reasoning as Phase 5

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

## Phase 7 — API Versioning Strategy

**Moved well ahead of its original number:** the whole point is introducing versioning
*before* any external tenant integrates, so a future breaking change doesn't silently break
existing integrations — retrofitting versioning onto a live API with real callers is far more
painful than deciding this now, while Phase 14 (deployment) and Phase 15 (self-serve
registration) haven't happened yet and there are still zero real callers. Doing this here also
means Phase 8's integration tests and Phase 9's docs are written against the final `/v1/...`
paths directly, with no rework later.

**Goal:** Introduce versioning before the API is ever publicly reachable.

**Design:**

- URL-path versioning (`/v1/chat`, `/v1/trade/evaluate`, ...) — simplest and most discoverable
  for API consumers, versus a header-based scheme.
- `/health` stays unversioned — it's infrastructure-level, not business logic, matching its
  existing exemption from API-key auth (Phase 3).
- Decide (not necessarily exercise yet) a deprecation policy: how long `/v1` stays supported
  once a `/v2` exists.

**Tasks:**

- Mount Phase 5/6's routes under an `APIRouter(prefix="/v1")` in `src/api/app.py`
- Write a short versioning/deprecation policy doc

**Verification:**

```bash
curl -H "X-API-Key: $KEY" https://<domain>/v1/trade/suggestions   # → 200
curl https://<domain>/trade/suggestions                            # → 404, forcing explicitness
```

---

## Phase 8 — API Test Gaps & Integration Coverage

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
- Audit `tests/api/` against the endpoint table in Phase 9 — confirm every route has at least
  one test, and file gaps here rather than assuming
- Any cross-cutting auth edge cases not covered by Phase 3's own tests (e.g. a tenant's key
  working correctly across *every* route type, not just the one Phase 3 tested it against)

**Verification:**

```bash
make test
# → tests/api/ tests all pass, full suite still green
```

---

## Phase 9 — Polish & Documentation

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
| POST   | `/v1/chat`              | Yes  | Free-text natural language agent query |
| POST   | `/v1/trade/evaluate`    | Yes  | Structured trade evaluation            |
| GET    | `/v1/trade/suggestions` | Yes  | Proactive trade suggestions            |
| GET    | `/v1/offers`            | Yes  | Pending trade offer inbox              |
| POST   | `/v1/offers/send`       | Yes  | Send a trade offer                     |
| POST   | `/v1/pokedex/query`     | Yes  | Pokedex knowledge question             |
| POST   | `/v1/market/query`      | Yes  | Market demand & trend query            |

---

## Phase 10 — Project Documentation Site (GitHub Pages)

**Goal:** A browsable docs/landing site at `https://jazicorn.github.io/pokemon-trainer-platform-ai/`,
built from the project's existing `README.md` and `docs/` markdown — no new content authored
just for this, just a better way to browse what's already written.

**Independent of the other phases:** unlike the sequential build-up in the phases before it,
this one has no dependency on the API work at all — it's just documentation tooling. It can be
done any time, including before Phase 2, without blocking or being blocked by anything else
here.

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

## Phase 11 — Interim Landing Page (Roadmap + Newsletter Signup)

**Despite the original number, this is early work, not late.** It depends only on Phase 10's
GitHub Pages setup existing — nothing from the phases between them. The full marketing/signup
site (Phase 20) is a long way off, since it needs most of the API actually built first; this
exists to close that gap, so it belongs right alongside or shortly after Phase 10, not at the
end of the list.

**Goal:** A minimal public page — the roadmap, in readable form, plus an email signup for
updates — so there's *something* to point people at and start building an audience during the
gap before Phase 20 exists, rather than nothing at all until then.

**Design:**

- Reuse Phase 10's MkDocs/GitHub Pages site rather than standing up separate hosting — this
  can be that site's homepage, with `ROADMAP.md` rendered below the fold (Phase 10 already
  renders it as its own page; surface it prominently here too).
- Email capture needs *some* backend, and GitHub Pages is static-only. For a stopgap like this,
  don't build custom infrastructure for it — use an existing newsletter provider (Buttondown,
  ConvertKit, ListMonk, etc.) with a simple embeddable form. The tradeoff is real (your
  subscriber data lives on their platform, not yours) but building a custom signup backend for
  something explicitly meant to be temporary is over-engineering the wrong thing. Revisit if
  Phase 20 wants to own this list directly later — exporting from any mainstream provider is
  standard.
- Needs a one-line privacy note next to the signup form (what the email is used for, how to
  unsubscribe) — a lightweight preview of Phase 20's real Privacy Policy, not a substitute for
  it once that exists.

**Tasks:**

- Pick a newsletter provider and create the list
- Add the landing content + embedded signup form to Phase 10's MkDocs site
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

## Phase 12 — Dependency & Vulnerability Scanning

**Moved up from its original position — no dependency on any other phase**, and there's no
reason to wait: it applies to whatever the repo looks like at any point.

**Goal:** Automated detection of vulnerable dependencies, using tooling that's free on GitHub.

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

## Phase 13 — Support Tooling

**Set this up before Phase 15 ships, not after.** Self-serve registration means strangers can
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
- Link it from Phase 20's marketing site and Phase 11's interim landing page
- Revisit around Phase 19 (paid tiers) — billing questions (refunds, disputes, "why was I
  charged") raise support expectations; re-evaluate whether Plain still fits or whether it's
  time to consider a heavier tool, rather than assuming the day-one choice holds forever

**Verification:**

```bash
# Send a real test email to the support address and confirm it lands in the shared inbox
```

---

## Phase 14 — Deployment

**Goal:** Run the API as a persistent, publicly-reachable service — this is a genuinely public
API (per Phase 3's design decision), not a private backend-to-backend link, so real TLS and
public-network hardening are required here, not optional.

**Host: [Fly.io](https://fly.io).** Docker-native (deploys this repo's own `Dockerfile`
directly), free built-in TLS at its edge, persistent volumes, no reverse-proxy layer to run or
maintain ourselves. Full runbook: `docs/DEPLOYMENT.md`.

**This phase isn't done until its security checklist passes too, not just deployment
mechanics.**

**Architecture.** One Fly app:

- **`<name>-api`** — public. This repo's `Dockerfile`, deployed via `fly.toml`. `force_https`
  at Fly's edge handles TLS (no Caddy/nginx). A persistent Fly volume holds `/app/data`, so
  `data/tenants.db` survives redeploys.

RAG's vector storage is **Chroma Cloud** (managed, not something this deploy runs itself) — a
second, private `<name>-chromadb` Fly app (self-hosted ChromaDB) was the original plan, dropped
in favor of Chroma Cloud before it was ever deployed. See "Vector storage: Chroma Cloud" below.

**Tasks:**

- ~~Fix a lifespan bug found while researching Fly~~ **done** — `api/app.py`'s `lifespan()`
  called `startup(chromadb=True, ...)`, which shells out to `docker run` when ChromaDB isn't
  reachable. A Fly Machine has no Docker daemon of its own, so that call would fail and
  `start_chromadb()` responds to a failed start with `raise SystemExit(0)` — killing the API
  before it serves a single request. Fixed to `chromadb=False`, mirroring the guard Phase 4
  already has for Phoenix. `/health`'s own `is_vector_store_running()` check (`src/utils.py`)
  still reports reachability truthfully for whichever RAG backend is actually active.
- ~~Add a long-running `api` service to `docker-compose.yml`~~ **done** — for local dev/testing
  parity (`docker compose up api` runs the exact command/healthcheck Fly runs), **not** the
  production deploy path — `fly.toml` is.
- ~~Resolve the non-root-user/volume-permission conflict~~ **done** — a Fly (or Docker) volume
  is created empty and root-owned; the image's non-root `appuser` can't write to it as-is. Fixed
  via `docker-entrypoint.sh`: runs as root, `chown`s `/app/data`, then `exec gosu appuser "$@"`
  (`gosu`, not a wrapping shell, so container signals still reach the app process directly).
  `Dockerfile`'s `USER appuser` line moved into this entrypoint.
- ~~Write `fly.toml`~~ **done** — `force_https = true`, health check against `/health`, a
  `[mounts]` entry for the data volume. Built from this repo's `Dockerfile` directly via
  `fly deploy` for this first pass; wiring CI to auto-deploy `image-publish.yml`'s already
  -published GHCR image on release is a clean fast-follow, not bundled in here.
- ~~Write `docs/DEPLOYMENT.md`~~ **done** — the Fly runbook: creating the app, its volume,
  `fly secrets set` for `ANTHROPIC_API_KEY` / `TENANT_DB_ENCRYPTION_KEY` / `SENTRY_DSN` /
  Chroma Cloud's three vars, deploy commands, and the `TENANT_DB_ENCRYPTION_KEY` backup
  reminder Phase 3 already established.

**Vector storage: Chroma Cloud.** Replaces self-hosted ChromaDB (`src/rag/vector_store.py`)
with managed storage — no self-hosted infra to run or back up, and it's what the "Architecture"
section above deploys instead of a second Fly app.

*Originally scoped as full hybrid search* (dense + sparse embeddings, Reciprocal Rank Fusion)
using Chroma Cloud's hosted Qwen (dense) and Splade (sparse) embedding functions. Blocked: both
depend on a JSON schema-validation file that's missing from every published `chromadb-client`
wheel checked (1.5.6 through 1.5.9) *and* from Chroma's own GitHub source — a genuine upstream
bug, not fixable client-side. **Shipped as dense-only instead**, embeddings computed
client-side (the same `get_simple_embedding`/`get_ollama_embedding` self-hosted mode already
used) — Chroma Cloud is used purely for storage/search, not its hosted embedding functions.
Revisit hybrid search once the upstream bug is fixed.

Design:

- `PokemonVectorStore` picks its backend by whether `config.chroma_api_key` is set — same
  "presence of the value is the switch" idiom as `platform_db_url`/`sentry_dsn`. Set: Chroma
  Cloud via the official `chromadb` client (`CloudClient`, no schema — see above). Unset (local
  dev/tests default): self-hosted ChromaDB, unchanged from before.
- Documents over Chroma's 16 KiB per-document limit are chunked (`src/rag/chunking.py`,
  line-span splitting — not one of Chroma's own named strategies, just a simple starting
  point; none of this project's current documents are anywhere near the limit) and tagged with
  `source_document_id`/`chunk_index` metadata, deduped back to one result per source document
  via `GroupBy` at query time. A chunked document currently reuses its whole-document embedding
  for every chunk — correct today only because nothing actually gets chunked; revisit (embed
  each chunk's own text) if that changes.
- No per-tenant/per-org sharding: the `pokemon`/`smogon_strategy` collections hold shared,
  static reference data — every tenant queries the same knowledge base, nothing here is
  tenant-owned. Would apply if a future phase embeds tenant-specific documents.
- No real data migration: this project holds no irreplaceable embedded content —
  `scripts/migrate_to_chroma_cloud.py` just re-runs the existing PokeAPI/Smogon ingestion
  (`rag/ingest.py`) against whichever backend is now configured.

Tasks:

- ~~Bump `chromadb-client` to `>=1.5.9`~~ **done** — `1.5.1` (the prior pin) fails to even
  `import chromadb` on this project's Python 3.14 runtime (a `pydantic.v1` incompatibility);
  `1.5.9` fixes this cleanly.
- ~~Add `chroma_api_key`/`chroma_tenant`/`chroma_database`/`chroma_host` to `src/config.py`~~
  **done** — `chroma_host` is optional, only needed for a non-default/dedicated deployment.
- ~~Rewrite `PokemonVectorStore` for the two-backend design above~~ **done**.
- ~~Write `src/rag/chunking.py`~~ **done**.
- ~~Write `scripts/migrate_to_chroma_cloud.py`~~ **done**, and run for real against a live
  Chroma Cloud account — 40 Pokemon plus their Smogon strategy documents ingested and
  query-verified end-to-end.
- ~~Update `.env.example` / `.env.op` / `docs/1PASSWORD.md`~~ **done**.
- ~~Update `docker-compose.yml`'s `api` service~~ **done** — `RATE_LIMIT_STORAGE_URI` was
  missing from an earlier task's own env passthrough; added alongside these.

**A real secret-hygiene incident, during this work's own test-isolation:** a test monkeypatched
`config.config`'s attributes to fake values, but `rag/vector_store.py`/`utils.py` had already
bound their own `from config import config` reference *before* an unrelated test file's
`importlib.reload(cfg_module)` replaced `config.config` with a new object elsewhere in the same
session — verified directly (`config.config is vector_store.config` is `True` before that
reload, `False` after). The monkeypatch silently affected the wrong object; the code under test
kept reading the stale one, which still held a real `CHROMA_API_KEY` from the local `.env`, and
that value surfaced in a test failure message. Fixed by patching the attribute on each
consuming module's own bound reference, not `config.config` generically — see
`tests/conftest.py`'s `_isolate_chroma_api_key` for the full explanation. The exposed key was
rotated.

Tests (mocked by default, matching this project's standing policy — no live external service
required for `make test`):

- `tests/rag/test_chunking.py` — pure unit tests, no live service.
- `tests/rag/test_vector_store_cloud.py` — `chromadb`'s own classes mocked throughout.
- `tests/memory/test_memory.py`'s `TestIsVectorStoreRunning` — both branches of
  `is_vector_store_running()`.
- A new `requires_chroma_cloud` pytest marker (`pytest.ini`, mirroring `requires_chromadb`) for
  live-service coverage (`tests/rag/test_chroma_cloud_live.py`) — deselected from `make test`
  by default (`make test-chroma-cloud` runs it explicitly, against a real account).

**Security checklist (required, not optional — this phase isn't done without these):**

- ~~**TLS/HTTPS sitewide**~~ **done** — Fly's edge (`force_https = true` in `fly.toml`); no
  reverse proxy of our own. (OWASP: [Transport Layer Protection Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html))
- ~~**Rate limiting / DoS protection**~~ **done, app-level, Redis-backed** — Fly's edge is a
  load balancer, not a WAF, so this has to live in the app regardless of host: `slowapi`, keyed
  by client IP, `default_limits` applied globally so it also covers `/health` and Phase 15's
  future no-key registration endpoint. `RATE_LIMIT_STORAGE_URI` (Upstash Redis) is the counter
  store — a shared count across however many instances are running, and one that survives a
  redeploy (an in-memory counter, the fallback when this is unset, does neither).
  `in_memory_fallback_enabled=True` is set explicitly so a Redis outage degrades to per-instance
  counting instead of 500ing every request (not slowapi's own default — verified by reading its
  source). Tests: `tests/api/test_rate_limiting.py`. (OWASP: [Denial of Service Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html))
- **Input validation at every boundary** — re-confirmed true: every route still validates
  through a typed Pydantic model or a typed `Query(...)` param, never a raw dict. (OWASP:
  [Input Validation Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html))
- **SQL injection prevention** — re-confirmed true: every `platform_db.py` query still uses
  psycopg's `%s` parameterization, no f-strings/`.format()` building SQL. (OWASP: [SQL
  Injection Prevention Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html))
- **Secrets management** — re-confirmed true: Phase 3's Fernet-encrypted `platform_db_url`,
  env-var/`fly secrets`-only secrets, nothing committed in plaintext. (OWASP: [Secrets
  Management Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html))
- ~~**HTTP security response headers**~~ **done, app-level** — HSTS, `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY` via a FastAPI middleware (`api/app.py`'s
  `security_headers`), not reverse-proxy config — Fly gives no such layer to configure. The
  `Server: uvicorn` header is dropped separately via `uvicorn.run(..., server_header=False)`
  (`api_server.py`). Tests: `tests/api/test_security_headers.py`. (OWASP: [HTTP Security
  Response Headers Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html))

**Explicitly out of scope here** (not forgotten — just not this phase): CI auto-deploy to Fly
on release.

**Verification:** live curl checks against the real deployment — see `docs/DEPLOYMENT.md`'s own
Verification section for the exact commands (health, TLS-redirect, 429-under-load, security
headers, persistent-volume-survives-restart). Chroma Cloud specifically:

```bash
uv run python scripts/migrate_to_chroma_cloud.py
# → "Done — N Pokemon (+ their Smogon strategy documents) ingested into Chroma Cloud."

uv run python -c "
from rag.vector_store import PokemonVectorStore
store = PokemonVectorStore()
for r in store.query('electric mouse pokemon', n_results=3):
    print(r['document'][:80], r['distance'])
"
# → real results back from Chroma Cloud, not local ChromaDB
```

---

## Phase 15 — Self-Serve Tenant Registration

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

## Phase 16 — Local Admin Web UI (Tenant Management Dashboard)

**Goal:** A local, operator-only web UI for viewing and managing tenants (Phase 3's
`data/tenants.db`) — list, create, deactivate, and rotate keys — without hand-running
`scripts/provision_tenant.py` or raw SQL for every change.

**Why local, not part of the public API:** this surface can see and act on every tenant's
account — activating/deactivating access, rotating keys, and (if ever revealed) their
`platform_db_url`. That's a different trust level than the public trade-advisor endpoints
entirely, so it deliberately stays out of `api_server.py`'s public surface:

- Ships as its own entry point, `admin_server.py`, bound to `127.0.0.1` by default — not
  started by `docker-compose.yml`'s public `api` service, and never given a public route
  through Phase 14's reverse proxy.
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
| `is_chromadb_running()`, `is_vector_store_running()` | `src/utils.py` |
| `require_api_key` | `src/api/auth.py` (new) |
| request logging middleware | `src/api/app.py` (new) |
| API route tests | `tests/api/test_api.py` (new) |
