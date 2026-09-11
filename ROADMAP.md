# Roadmap: Web API

Convert the Pokemon Trainer Platform from a CLI + MCP server into a full HTTP web API using
FastAPI, while keeping the existing CLI and MCP interfaces intact.

Covers Phases 1-16 — the API itself: dependencies through admin tooling. What happens once
it's real (hosting, billing, the public website, security, ops maturity, growth) continues in
[ROADMAP_PLATFORM.md](ROADMAP_PLATFORM.md), Phases 17 onward. Phase numbers are shared and
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
`/v1/trade/suggestions` here would 404 before ever reaching auth, which isn't a
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
  - Format: `POST /v1/chat 200 342ms`
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
  "http://localhost:8080/v1/trade/suggestions?user_id=user_001"

# Check server logs show the request line
# Check Phoenix at http://localhost:6006 shows the trace with agent sub-spans
# Trigger a deliberate error and confirm it appears in the Sentry dashboard
```

---

## Phase 5 — Core Trade Endpoints

**Goal:** Expose the primary agent functionality over HTTP.

**Tasks:**

- Add to `src/api/app.py`, importing from `agents.trade_advisor_api`:
  - `POST /v1/chat` → `evaluate_trade(raw_query=request.message, user_id=...,
    conversation_context=...)`
  - `POST /v1/trade/evaluate` → `evaluate_trade(offered_pokemon, requested_pokemon, user_id, ...)`
  - `GET /v1/trade/suggestions` (query param: `user_id`) → `get_trade_suggestions(user_id)`
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
curl -i http://localhost:8080/v1/trade/suggestions
# → HTTP/1.1 401

# Wrong/unknown key → 403
curl -i -H "X-API-Key: wrong" http://localhost:8080/v1/trade/suggestions
# → HTTP/1.1 403

# Correct key → 200, reasoning over THAT tenant's own platform_db_url
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8080/v1/trade/suggestions?user_id=user_001"
```

And the actual functionality across all three new routes:

```bash
curl -X POST http://localhost:8080/v1/chat \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "Should I trade my Pikachu for their Charizard?"}'

curl -X POST http://localhost:8080/v1/trade/evaluate \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard"}'

curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8080/v1/trade/suggestions?user_id=user_001"
```

---

## Phase 6 — Offers & Query Endpoints

**Goal:** Complete the full API surface — inbox management and knowledge queries.

**Tasks:**

- Add to `src/api/app.py`, all protected by `require_api_key`:
  - `GET /v1/offers` (query param: `user_id`) → `get_pending_offers(user_id)`
    from `agents.trade_advisor_api`
  - `POST /v1/offers/send` →
    `send_trade_offer(sender_id, recipient_id, offered_pokemon, requested_pokemon)`
  - `POST /v1/pokedex/query` → `query_pokedex(question, user_id)` from `agents`
  - `POST /v1/market/query` → `query_market(question)` from `agents.trade_market_analyst`
- Write `tests/api/test_offers_endpoints.py` and `tests/api/test_query_endpoints.py` for these
  four routes as part of this phase, same reasoning as Phase 5

**Endpoints added this phase:** 4 (total: 8)

**Verification:**

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/v1/offers?user_id=user_001"

curl -X POST http://localhost:8080/v1/offers/send \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sender_id":"user_001","recipient_id":"user_002",
       "offered_pokemon":"Eevee","requested_pokemon":"Vaporeon"}'

curl -X POST http://localhost:8080/v1/pokedex/query \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are Charizards weaknesses?"}'

curl -X POST http://localhost:8080/v1/market/query \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Which Pokemon are trending bullish right now?"}'

# Swagger UI (key can be set via the Authorize button)
open http://localhost:8080/docs
```

---

## Phase 7 — API Versioning Strategy

**Goal:** Introduce versioning *before* any external tenant integrates (Phase 14 deployment,
Phase 15 self-serve registration), so a future breaking change doesn't silently break existing
integrations — retrofitting versioning onto a live API with real callers is far more painful
than deciding this now. Doing this before Phase 8/9 also means their integration tests and
docs are written against the final `/v1/...` paths directly, with no rework later.

**Design:**

- URL-path versioning (`/v1/chat`, `/v1/trade/evaluate`, ...) — simplest and most discoverable
  for API consumers, versus a header-based scheme.
- `/health` stays unversioned — it's infrastructure-level, not business logic, matching its
  existing exemption from API-key auth (Phase 3).
- Decide (not necessarily exercise yet) a deprecation policy: how long `/v1` stays supported
  once a `/v2` exists.

**Tasks:**

- ~~Mount Phase 5/6's routes under an `APIRouter(prefix="/v1")` in `src/api/app.py`~~ **done**
- ~~Write a short versioning/deprecation policy doc~~ **done** — `docs/REFERENCE/API_VERSIONING.md`

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
  send an offer, fetch it back via `GET /v1/offers`, confirm the AI analysis is present —
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

| Method | Path                       | Auth | Description                                    |
| ------ | -------------------------- | ---- | ----------------------------------------------- |
| GET    | `/health`                  | No   | Service health check                           |
| POST   | `/v1/accounts/register`    | No   | Self-serve tenant signup (Phase 15)            |
| POST   | `/v1/chat`                 | Yes  | Free-text natural language agent query         |
| POST   | `/v1/trade/evaluate`       | Yes  | Structured trade evaluation                    |
| GET    | `/v1/trade/suggestions`    | Yes  | Proactive trade suggestions                    |
| GET    | `/v1/offers`               | Yes  | Pending trade offer inbox                      |
| POST   | `/v1/offers/send`          | Yes  | Send a trade offer                             |
| POST   | `/v1/pokedex/query`        | Yes  | Pokedex knowledge question                     |
| POST   | `/v1/market/query`         | Yes  | Market demand & trend query                    |
| POST   | `/v1/accounts/rotate-key`  | Yes  | Rotate the caller's own API key (Phase 15)     |
| DELETE | `/v1/accounts`             | Yes  | Deactivate the caller's own account (Phase 15) |

---

## Phase 10 — Project Documentation Site (GitHub Pages)

**Goal:** A browsable docs/landing site at `https://jazicorn.github.io/pokemon-trainer-platform-ai/`,
built from the project's existing `README.md` and `docs/` markdown — no new content authored
just for this, just a better way to browse what's already written.

**Independent of the other phases:** unlike the sequential build-up in the phases before it,
this one has no dependency on the API work at all — it's just documentation tooling. It can be
done any time, including before Phase 2, without blocking or being blocked by anything else
here.

**Design (v2 — Astro + Starlight):** this phase originally shipped on MkDocs + Material
(a `uv`-installable Python tool, deliberately not Docusaurus/React — see git history for that
version's reasoning), then briefly grew a small React "hub" island bolted onto the Material
Home page. Both were replaced outright — not layered further — once the priority became "looks
creative and polished," which a themed MkDocs site couldn't get to on its own:

- **[Astro](https://astro.build) + [Starlight](https://starlight.astro.build)**, in
  `web/docs-site/`. Same self-hosted GitHub Pages model as the MkDocs version (still a `gh-pages`
  branch, still no third-party platform dependency — this is *not* a move to something like
  Mintlify, which would mean hosting docs on their infrastructure instead of ours) and, like
  Astro's islands architecture generally, ships close to zero JS by default — the opposite
  direction from the React hub it replaces, even though the framework itself is JS-based. Content
  is still plain markdown; only navigation and theming moved into Astro/Starlight's own config
  and component model.
- Content is unchanged at the source: `README.md`, both roadmap files, `ARCHITECTURE.md`,
  `HISTORY.md`, `CHANGELOG.md`, and everything under `docs/` are still the one source of truth.
  `scripts/docs_prepare.py` (the direct successor to the old Makefile `cp` lines) mirrors them
  into `web/docs-site/src/content/docs/` — adding the frontmatter (`title`, and a `pokemonType`
  badge for pages that map to one of the eight type tokens below) that plain markdown doesn't
  carry, and rewriting cross-references between docs to the new route paths. Generated, gitignored,
  same "one source of truth" reasoning as before. The one hand-authored exception is
  `src/content/docs/index.mdx` (the home page), which the script never touches.
- **Home** (`index.mdx`) is a from-scratch Starlight "splash" page, not a mirror of `README.md`:
  a hero, a "Meet the party" grid of the five real agents (`src/components/AgentCard.astro` +
  `party.ts`), a "Talk to it" `CardGrid` with real CLI/`/v1`/MCP entry points, and a `curl`
  example against a real endpoint. `README.md` itself now renders as its own **Overview** page
  (first item in the sidebar) instead of doubling as Home.
- **Party chrome** (the five-agent strip in the header, every page) and the **type-badge kicker**
  (above a page's H1, on pages whose section maps to one of the eight type tokens) are Starlight
  component overrides — `SiteTitle.astro` and `PageTitle.astro` in `web/docs-site/src/components/`,
  following [Starlight's documented override pattern](https://starlight.astro.build/guides/overriding-components/)
  of wrapping the default component rather than reimplementing it. `pokemonType` is a frontmatter
  field added to Starlight's schema (`src/content.config.ts`'s `docsSchema({ extend: ... })`),
  computed once at prepare-time by `docs_prepare.py` rather than sniffed from the URL at runtime
  in the browser (the MkDocs version's approach) — same eight-color system, no client-side
  path-matching needed anymore.
- Starlight's own accent color (used for links, the active sidebar item, focus rings) is retuned
  from its stock blue to this project's Dragon hue (`web/docs-site/src/styles/theme.css`) so the
  whole site reads as one coordinated palette instead of theme-default blue fighting the
  Pokemon-type colors used everywhere else — the MkDocs version never did this, which is most of
  why its color scheme read as "off."
- `.github/workflows/docs-publish.yml` builds with `astro build` (Node, via `actions/setup-node`)
  and still deploys to the `gh-pages` branch, now via `peaceiris/actions-gh-pages` since there's
  no `mkdocs gh-deploy` equivalent in this stack.
- GitHub Pages itself (repo Settings → Pages, serving from the `gh-pages` branch) is a
  one-time manual step in the GitHub UI — no workflow file can do that part. **Still pending.**

**Tasks:**

- ~~Scaffold `web/docs-site/` (Astro + Starlight)~~ **done**
- ~~Write `scripts/docs_prepare.py`~~ **done** — mirrors root/`docs/` markdown into
  `src/content/docs/`, adds frontmatter, rewrites internal links
- ~~Build the Home page (`index.mdx`) as a real splash page, not a README mirror~~ **done**
- ~~Party chrome + type-badge kicker as Starlight component overrides~~ **done**
- ~~Retune Starlight's accent color to match the type-token palette~~ **done**
- ~~Rewrite `.github/workflows/docs-publish.yml` for the Astro build + `gh-pages` deploy~~ **done**
- ~~Remove the MkDocs + React-hub setup (`mkdocs.yml`, `web/hub/`, the `docs` dependency
  group)~~ **done**
- One-time: enable GitHub Pages in repo settings, pointed at the `gh-pages` branch — **not done
  yet**, needs a human in the GitHub UI
- Still open, deliberately deferred rather than done blind alongside the framework swap:
  reorganizing the docs corpus itself (nav grouping, page-level splitting/merging) now that it's
  easy to see the whole site rendered — content is currently mirrored over with its existing
  structure intact, not redesigned

**Verification:**

```bash
make docs-serve
# → runs scripts/docs_prepare.py, then `astro dev` — confirm the sidebar renders every docs/
#   page and README/ROADMAP/HISTORY, Home renders the hub (agent cards + Talk to it), the
#   five-agent party strip shows in the header on every page, and type badges appear on pages
#   that map to one, light and dark

git push origin main   # touching docs/, web/docs-site/, scripts/docs_prepare.py, README.md,
                        # ROADMAP.md, ROADMAP_PLATFORM.md, ARCHITECTURE.md, HISTORY.md,
                        # CHANGELOG.md, or Makefile
# → docs-publish.yml runs, gh-pages branch updates
# → https://jazicorn.github.io/pokemon-trainer-platform-ai/ reflects the change, once GitHub
#   Pages is enabled (see the still-pending task above)
```

---

## Phase 11 — Interim Landing Page (Roadmap + Newsletter Signup)

**Depends only on Phase 10's GitHub Pages setup** — nothing else. The full marketing/signup
site (Phase 20) is a long way off, since it needs most of the API actually built first; this
closes that gap in the meantime.

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
make docs-serve
# → homepage shows roadmap summary + signup form, both render correctly

# Submit a test signup, confirm it actually lands in the provider's list
# (manual check — this is a third-party integration, not something to script here)
```

---

## Phase 12 — Dependency & Vulnerability Scanning

**No dependency on any other phase** — applies to whatever the repo looks like at any point.

**Goal:** Automated detection of vulnerable dependencies, using tooling that's free on GitHub.

**Tasks:**

- ~~Add `.github/dependabot.yml` for the `uv` and `github-actions` ecosystems~~ **done**
- ~~Add a `pip-audit` step to `ci-quality.yml`~~ **done** — report-only (`continue-on-error`),
  since pip-audit reports no severity data to gate a block/warn split on. Findings show in the
  CI log; Dependabot's PRs are expected to work them down over time. Revisit blocking once the
  current findings are clear.

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

RAG's vector storage is **Chroma Cloud** (managed) — see "Vector storage: Chroma Cloud" below.

**Tasks:**

- ~~Fix `api/app.py`'s `lifespan()`~~ **done** — it called `startup(chromadb=True, ...)`, which
  shells out to `docker run` when ChromaDB isn't reachable; a Fly Machine has no Docker daemon,
  so that failed and killed the API on boot. Fixed to `chromadb=False`, mirroring Phase 4's
  existing guard for Phoenix. `/health`'s `is_vector_store_running()` (`src/utils.py`) reports
  reachability for whichever RAG backend is actually active.
- ~~Add a long-running `api` service to `docker-compose.yml`~~ **done** — local dev/testing
  parity only; `fly.toml` is the production deploy path.
- ~~Resolve the non-root-user/volume-permission conflict~~ **done** — a Fly volume is created
  empty and root-owned; `docker-entrypoint.sh` runs as root, `chown`s `/app/data`, then
  `exec gosu appuser "$@"` (a real exec, not a wrapping shell, so container signals still reach
  the app directly).
- ~~Write `fly.toml`~~ **done** — `force_https = true`, health check against `/health`, a
  `[mounts]` entry for the data volume.
- ~~Write `docs/DEPLOYMENT.md`~~ **done** — the Fly runbook, including secrets setup and the
  `TENANT_DB_ENCRYPTION_KEY` backup reminder Phase 3 established.

**Vector storage: Chroma Cloud.** Replaces self-hosted ChromaDB (`src/rag/vector_store.py`) —
managed, no self-hosted infra to run or back up.

Dense-only, not the originally-planned hybrid search (dense + sparse via Chroma Cloud's hosted
Qwen/Splade embedding functions) — both depend on a JSON schema file missing from every
published `chromadb-client` wheel (1.5.6-1.5.9) and from Chroma's own GitHub source, an
upstream bug. Embeddings are computed client-side instead (the same
`get_simple_embedding`/`get_ollama_embedding` self-hosted mode already used); Chroma Cloud is
used purely for storage/search. Revisit hybrid search once the upstream bug is fixed.

Design:

- `PokemonVectorStore` picks its backend by whether `config.chroma_api_key` is set — same
  "presence of the value is the switch" idiom as `platform_db_url`/`sentry_dsn`.
- Documents over Chroma's 16 KiB per-document limit are chunked (`src/rag/chunking.py`,
  line-span splitting) and tagged with `source_document_id`/`chunk_index`, deduped to one
  result per source document via `GroupBy` at query time. Not exercised today — nothing
  currently exceeds the limit.
- No per-tenant sharding: the `pokemon`/`smogon_strategy` collections are shared reference
  data, not tenant-owned.
- No data migration needed: `scripts/migrate_to_chroma_cloud.py` re-runs the existing
  PokeAPI/Smogon ingestion (`rag/ingest.py`) against whichever backend is configured.

Tasks:

- ~~Bump `chromadb-client` to `>=1.5.9`~~ **done** — `1.5.1` doesn't import on Python 3.14.
- ~~Add `chroma_api_key`/`chroma_tenant`/`chroma_database`/`chroma_host` to `src/config.py`~~
  **done** — `chroma_host` is optional, only for a non-default deployment.
- ~~Rewrite `PokemonVectorStore` for the two-backend design above~~ **done**.
- ~~Write `src/rag/chunking.py`~~ **done**.
- ~~Write `scripts/migrate_to_chroma_cloud.py`~~ **done**.
- ~~Update `.env.example` / `.env.op` / `docs/1PASSWORD.md`~~ **done**.
- ~~Update `docker-compose.yml`'s `api` service~~ **done**.

Tests (mocked by default — no live external service required for `make test`):

- `tests/rag/test_chunking.py`, `tests/rag/test_vector_store_cloud.py`.
- `tests/memory/test_memory.py`'s `TestIsVectorStoreRunning`.
- `requires_chroma_cloud` pytest marker (mirroring `requires_chromadb`) for live-service
  coverage (`tests/rag/test_chroma_cloud_live.py`), deselected by default —
  `make test-chroma-cloud` runs it against a real account.

**Security checklist (required, not optional — this phase isn't done without these):**

- ~~**TLS/HTTPS sitewide**~~ **done** — Fly's edge (`force_https = true` in `fly.toml`); no
  reverse proxy of our own. (OWASP: [Transport Layer Protection Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html))
- ~~**Rate limiting / DoS protection**~~ **done, app-level, Redis-backed** — Fly's edge is a
  load balancer, not a WAF, so this has to live in the app: `slowapi`, keyed by client IP,
  `default_limits` applied globally so it also covers `/health` and Phase 15's future no-key
  registration endpoint. `RATE_LIMIT_STORAGE_URI` (Upstash Redis) backs the counter across
  however many instances are running and across redeploys.
  `in_memory_fallback_enabled=True` so a Redis outage degrades to per-instance counting instead
  of 500ing every request. Tests: `tests/api/test_rate_limiting.py`. (OWASP: [Denial of Service
  Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html))
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

- ~~`POST /v1/accounts/register` (unauthenticated by definition — it's how a caller *gets* a
  key): accepts `{name, platform_db_url}`, returns a newly generated API key **once**, and
  inserts the same `tenants` row shape `scripts/provision_tenant.py` creates today~~ **done**
- ~~Before storing, validate the submitted `platform_db_url` actually connects and matches
  `docs/REFERENCE/PLATFORM_DB.md`'s schema contract~~ **done** — `src/api/registration.py`
  connects and checks `information_schema.tables` for all five required tables, rejecting with
  a 422 naming exactly which are missing (or a 503 if the server itself is missing the
  `platform-db` dependency group)
- ~~Rate-limit this endpoint specifically~~ **done** — `5/minute`, well under the `100/minute`
  app-wide default
- ~~`POST /v1/accounts/rotate-key` and `DELETE /v1/accounts` (both behind the tenant's own
  current key)~~ **done**
- ~~Update `scripts/provision_tenant.py`'s docstring to note it's now the *admin override*
  path~~ **done**

The Dockerfile's `uv sync` now includes the `platform-db` group — this validation, and every
tenant's own real database routing (Phase 3+), need `psycopg` installed in the deployed image,
not just as a locally optional extra.

**Verification:**

```bash
curl -X POST https://<your-public-domain>/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"name": "new-tenant", "platform_db_url": "postgresql://user:pass@host/db"}'
# → {"tenant_id": "...", "api_key": "<shown once>"}

# A platform_db_url that doesn't match the schema contract is rejected up front:
curl -X POST https://<your-public-domain>/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"name": "bad-tenant", "platform_db_url": "postgresql://user:pass@host/empty_db"}'
# → HTTP 422, naming the missing table

uv run pytest tests/api/test_registration.py tests/api/test_accounts_endpoints.py -v
# → all passing
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
curl -i -H "X-API-Key: <same key>" http://localhost:8080/v1/trade/suggestions
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
