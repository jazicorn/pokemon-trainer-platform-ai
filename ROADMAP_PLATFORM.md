# Roadmap: Platform, Launch & Growth

Continues [ROADMAP.md](ROADMAP.md) — Phases 1-16 build the API itself (dependencies through
admin tooling). This file picks up once that exists: turning it into a real, public,
monetized multi-tenant product — hosting and billing, the actual public website, security
hardening for genuine public exposure, and the long tail of operational maturity (backups,
client SDKs, webhooks, staging, uptime monitoring, provider fallback, growth analytics).

Phase numbers are shared and continuous with ROADMAP.md — Phase 17 here is really "Phase 17
overall," not a reset.

**Testing policy — same as ROADMAP.md, applies here too:** a phase isn't done until its own
automated tests exist in `tests/` and pass, written as part of implementing that phase, not
after it. There is no "manually verify with curl or a throwaway script" step in this
project's workflow — if code needs verifying, write the real `pytest`/`TestClient` test for
it; that test *is* how it gets verified, and it's what stays behind to catch the next
regression.

---

## Phase 17 — Managed PostgreSQL Provisioning (Default Database Option)

**Goal:** Let a tenant register without bringing their own `PLATFORM_DB_URL` — provision a
dedicated managed Postgres database for them automatically, using the exact same schema
contract self-hosted tenants use (`docs/REFERENCE/PLATFORM_DB.md`), so there's one code path
either way. Per your direction, this becomes the **default** choice at registration — bringing
your own database becomes the opt-out, not the opt-in.

**Requires explicit disclosure, not just a technical default:** the whole point of encouraging
the managed option is so tenant data lives on infrastructure you control — which only becomes
Phase 18's cross-tenant analytics if tenants have actually agreed to that. A checkbox default
doesn't substitute for a terms-of-service / privacy-policy tenants see and accept. Phase 20 is
where those actual pages get built — this phase links to them, not duplicates them.

**Database hosting and analytics consent are two separate toggles, not one.** Where a tenant's
database lives (`use_managed_db`) and whether their data feeds Phase 18's cross-tenant
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
  can't touch another's. Doesn't block Phase 18's cross-tenant analytics, which reads across
  many tenant databases via ETL regardless of how they're separated.
- A managed cloud Postgres (RDS, Cloud SQL, Supabase, etc.) rather than self-hosting the
  `postgres` service from `docker-compose.yml` for this — that service is a dev convenience;
  other people's data now needs real backups and durability guarantees.
- Schema migration: a SQL migration script (the exact schema from `PLATFORM_DB.md`) runs
  automatically against each new tenant database at provisioning time — `create_tenant()`
  (Phase 3) gains a `managed: bool` path that provisions the database first, then stores the
  resulting connection string exactly like a self-hosted one (encrypted, same `tenants` table).
- Phase 15's `POST /accounts/register` gains a `use_managed_db: bool` field (**defaulting to
  `true`**, per your direction) — when true, `platform_db_url` in the request is ignored/omitted
  entirely and a database is provisioned instead — plus the independent `analytics_opt_in: bool`
  field described above.
- Sets up Phase 19 naturally: a paid tier can later mean "your own dedicated Postgres instance"
  vs. free tier's shared server, many-databases model.

**Tasks:**

- ~~Choose a managed Postgres provider~~ **done** — [Aiven](https://aiven.io/), which supports
  creating multiple databases within one PostgreSQL *service* (including via a plain Postgres
  client connection) — the "one server, one database per tenant" design this phase needs.
  **You still need to provision the real Aiven service yourself** and set `AIVEN_ADMIN_DB_URL`
  (see `docs/1PASSWORD.md`) — this repo can't create the account for you.
- ~~Write the tenant-database provisioning function~~ **done** — `src/api/managed_db.py`:
  `CREATE DATABASE`/`CREATE ROLE` per tenant, runs the exact schema from `PLATFORM_DB.md`,
  grants matching that doc's "Database Role (Recommended)" section, returns a connection string
  scoped to that tenant's own role — never the admin/superuser's credentials.
- ~~Extend `create_tenant()` and `POST /accounts/register` with `use_managed_db` and
  `analytics_opt_in`~~ **done** — `use_managed_db` defaults `true` on the endpoint.
- ~~Link the registration flow to Phase 20's Privacy Policy / Terms pages~~ **done, as a
  placeholder** — `use_managed_db=true` requires `terms_accepted=true` (422 otherwise),
  pointing at `config.terms_url`. That URL is a placeholder until Phase 20 actually builds the
  page; the technical gate (can't register a managed tenant without accepting) is real now.
- ~~Decide the deactivated-tenant managed-database policy~~ **done** — retain. Deactivating a
  managed tenant leaves their database running untouched: simplest, reversible, but costs
  continue accruing until cleaned up manually. A scheduled cleanup job is a natural future
  addition, not built here.
- ~~Migrate `TENANT_DB_ENCRYPTION_KEY` to KMS-backed envelope encryption~~ **done** —
  [HashiCorp Vault](https://www.vaultproject.io/)'s Transit secrets engine
  (`src/api/kms.py`: `generate_data_key`/`decrypt_data`), a fresh DEK per tenant. `wrapped_dek`
  is nullable in `tenants.db`: `NULL` means a row is still on the Phase 3 static key (decrypted
  via the old path, unaffected), set means the new per-tenant path — migration is operator-paced,
  not a hard cutover. `scripts/migrate_to_vault_encryption.py` migrates existing rows; **you
  still need a real Vault instance and `VAULT_ADDR`/`VAULT_TOKEN`** for any of this to actually
  encrypt anything (see `docs/1PASSWORD.md`).

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

## Phase 18 — Cross-Tenant Analytics via ClickHouse

**Goal:** Platform-wide insights ("which Pokemon are trending across every tenant this week")
fed from every tenant database that's actually opted in, using ClickHouse as the analytics layer.

**Why ClickHouse specifically:** the tenant-facing schema in `PLATFORM_DB.md` is an OLTP
workload — point lookups by `user_id`, and `trade_offers` needs real row-level UPDATEs — which
ClickHouse handles poorly (its `ALTER TABLE ... UPDATE` is an async batch "mutation," not a
routine per-row write). It's the right tool for a different job: append-heavy aggregation over
large volumes, which is exactly what cross-tenant trend analysis is. That's why this is a
separate, additive layer fed *from* Postgres, not a replacement for it.

**Scope boundary — this is the load-bearing part:** this pipeline only reads from tenants with
`analytics_opt_in == true` (Phase 17), regardless of whether their database is managed or
self-hosted — hosting location and analytics consent are independent flags, not the same
decision (see Phase 17's design note). A tenant who hasn't opted in never has their data touch
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
- A read path for the aggregated data — initially internal/admin-only (queried from Phase 16's
  admin web UI), with a public `/market/insights`-style endpoint as a later, natural Phase 19
  paid-tier feature rather than something every tenant gets by default.

**Tasks:**

- Add `clickhouse` to `docker-compose.yml` under the `analytics` profile
- Write the ETL script: per-opted-in-tenant extraction into the shared ClickHouse fact table
- Schedule it (cron, or a scheduled GitHub Actions workflow / external scheduler)
- Add a query module (e.g. `src/analytics/clickhouse_client.py`) exposing the aggregate queries
  the platform actually wants (trending Pokemon, tier distribution shifts, etc.)
- Surface a first read of this data in Phase 16's admin web UI before exposing it publicly

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

## Phase 19 — Account Plans (Free & Paid Tiers)

**Goal:** Differentiate tenant capability by plan, and monetize the public API.

**Design:**

- Extend the `tenants` table (Phase 3) with a `plan` column (`free` | `paid` to start — leave
  room for more tiers later rather than hardcoding a boolean).
- **Free tier**: rate-limited (requests/day), managed-database tenants share the pooled
  Postgres server from Phase 17, no access to Phase 18's aggregate market-insights endpoint.
- **Paid tier**: higher/no rate limits, a **dedicated** managed Postgres instance instead of a
  shared server (a direct, natural use of Phase 17's per-tenant-database design — "dedicated
  database" becomes a concrete paid-tier feature, not just an isolation detail), and access to
  Phase 18's `/market/insights` endpoint as a premium feature.
- Billing via Stripe (or an equivalent processor) — hosted Checkout for the actual payment
  flow, webhooks for subscription created/upgraded/downgraded/cancelled events updating the
  tenant's `plan` column. This is ordinary SaaS billing integration code — building the
  webhook handlers and checkout flow isn't something I'd hold back on — but the Stripe account,
  pricing, and business terms are yours to set, not something to default here.
- Rate limiting is already required as of Phase 14 (abuse prevention, applied uniformly).
  This phase adds a second dimension on top: limits that vary *by plan*, not just a uniform
  abuse threshold — free vs. paid tenants get different caps, which is a business rule, not
  a security one.

**Tasks:**

- Add `plan` (and any plan-specific limit fields) to the `tenants` schema
- Set up a Stripe account, products/prices for the paid tier
- Add `POST /billing/checkout` (redirects to Stripe Checkout) and `POST /billing/webhook`
  (verifies Stripe's signature, updates `plan` on subscription events)
- Implement rate limiting keyed by tenant + plan (a reverse-proxy layer or in-app middleware —
  whichever fits wherever Phase 14 actually deploys this)
- Gate Phase 18's `/market/insights` endpoint behind `plan == "paid"`
- Surface plan and usage in Phase 16's admin web UI

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

## Phase 20 — Marketing/Signup Website & Launch Checklist

**Goal:** A real product website — distinct from Phase 10's GitHub Pages docs site — covering
signup, pricing (Phase 19), and the legal pages Phase 17 already links to. Phase 10 renders
existing docs as-is; this phase is new, purpose-built content: a landing page, a pricing page,
the registration flow's front end, and the Privacy Policy / Terms of Service tenants actually
read and accept.

**This is the concrete home for Phase 17's disclosure requirement** — the Privacy Policy here
is where "what managed-tenant and opted-in data is used for" actually gets written down and
shown to a tenant before they accept it, not a task deferred indefinitely.

**Tasks**, grouped and adapted from a general pre-launch checklist to what actually applies here:

*Legal & compliance:*
- Privacy Policy page — covers what tenant data is collected, how `analytics_opt_in` data
  feeds Phase 18, and how managed-database hosting (Phase 17) works
- Terms of Service page — API usage terms, billing terms for Phase 19's paid tier

*Security:*
- Secrets off the frontend — no API keys, Stripe secret keys, or admin tokens ever reach
  client-side code on this site (the registration flow only ever talks to `POST
  /accounts/register`, which returns a key to display once, not embed in page source)
- Force HTTPS (already required by Phase 14 for the API; applies here too)

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
- Spam/abuse protection on signup — the same concern Phase 15's `POST /accounts/register`
  already flags as needing rate limiting; a CAPTCHA or honeypot on the front-end form is the
  other half of that
- Site analytics (visits, signup conversion) — a *different* thing from Phase 18's product
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

## Phase 21 — Security Hardening

**Goal:** Systematic security hardening across transport, application, and infrastructure
layers, prioritized by what's load-bearing for a public multi-tenant API versus genuine
defense-in-depth. Cross-references [OWASP's cheat sheet
series](https://cheatsheetseries.owasp.org/index.html) per item rather than treating "read
OWASP" as one task — it's a reference library, not a checklist itself.

**The P0 tier (TLS, rate limiting, input validation, SQL injection, secrets management)
lives directly in ROADMAP.md's Phase 14, not here.** It was originally written up as this
phase's own P0 tier, but a security checklist that only lives in a separate, later phase is
exactly the mistake this project already made once with testing — a later "testing phase"
let an earlier phase look done without ever having tests. Moved for the same reason: those
five items gate Phase 14 directly now, not a cross-reference away from it. What's left here is
P1 (land shortly after launch) and P2 (ongoing hardening) — genuinely later-tier items, not
load-bearing for launch itself.

**Everything with a natural phase already moved there — this phase is what's left over.**
The P0 tier (TLS, rate limiting, input validation, SQL injection, secrets management) moved
to ROADMAP.md's Phase 14. HTTP security headers moved there too (same reverse-proxy config,
same moment). Cookie security + CSRF moved to Phase 16 (the concrete answer to "whichever
cookie-based feature ships first"). Dependency/vulnerability scanning moved to Phase 12 (no
reason to wait). TLS certificate expiry monitoring moved to Phase 27 (already "external
monitoring," the natural home). What's left here doesn't have a single phase to attach to —
it's genuinely ongoing practice, not one-time setup work.

**Two things already checked/fixed against the real codebase, not assumed:**
- **SQL injection — already safe.** Every query in `src/data/platform_db.py` uses psycopg's
  `%s` parameterized placeholders, never string interpolation (verified across all 9
  `cur.execute()` calls). Re-verified as part of Phase 14's own checklist now; the task here is
  keeping it true as Phase 17/19 add more queries, not fixing something broken.
- **Non-root Docker user — already fixed.** `Dockerfile` had no `USER` directive at all;
  added directly (no phase dependency, so no reason to wait) — `useradd --create-home` plus
  a `chown` of `/app`, switched to before `CMD`.

### Ongoing hardening practices

- **Explicit cipher suite verification** — check via an SSL Labs (or equivalent) scan rather
  than assuming the reverse proxy's defaults are sufficient; re-check periodically, since
  "secure today" doesn't mean "secure in a year" as ciphers age out.
- **Recurring security review cadence** — this environment already has a `security-review`
  skill available; run it before releases that touch auth/payment/data-access code (Phases 3,
  17, 19 especially), not just once at the end of this whole roadmap.

**Tasks:**

- Add a query-safety note to `CONTRIBUTING`-style guidance (or a lint rule, if one exists for
  this) flagging string-interpolated SQL as a blocker in review
- Run an initial SSL Labs scan once Phase 14's domain exists; put a recurring reminder on
  whatever calendar/task system you actually use — this isn't a one-time roadmap checkbox
- Schedule recurring `security-review` runs tied to Phases 3/17/19 landing, not just ad hoc

**Verification:**

```bash
# Confirm the non-root fix, once Docker is available to build with:
docker compose build app
docker run --rm pokemon-trainer-platform-ai-app whoami
# → "appuser", not "root"
```

---

## Phase 22 — Backups & Disaster Recovery

**Goal:** Tenant data survives infrastructure failure, with a *tested* restore path — not just
an assumption that the managed Postgres provider "probably handles it."

**Design:**

- Enable the managed Postgres provider's (Phase 17) automated snapshots, with an explicit
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

- Enable and configure automated Postgres backups/retention on the Phase 17 provider
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

## Phase 23 — Per-Tenant Cost/Usage Tracking

**Goal:** Track real LLM spend per tenant — independent of Phase 19's request-count rate
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
  plus a surfaced view in Phase 16's admin web UI.

**Tasks:**

- Wire usage capture into every agent-run call site
- Add the usage-tracking table/schema
- Integrate `genai_prices` for cost conversion
- Enforce the free-tier hard cap; implement the paid-tier alert
- Add `GET /account/usage` and the Phase 16 admin surface

**Verification:**

```bash
curl -H "X-API-Key: <free-tier-key>" -X POST https://<domain>/v1/chat -d '...'
# repeated until the period budget is hit
# → a clear "usage limit reached" response, not a generic 500 or silent overspend

curl -H "X-API-Key: <key>" https://<domain>/account/usage
# → {"tokens_used": ..., "estimated_cost_usd": ..., "period": "..."}
```

---

## Phase 24 — Client SDKs

**Goal:** Lower integration friction for tenants with a thin client wrapping the versioned API
(Phase 7) — directly relevant to the original "would I be calling the FastAPI endpoints from
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

## Phase 25 — Outbound Webhooks

**Goal:** Let tenants receive events (e.g., "trade offer analysis complete") instead of polling
`GET /offers`.

**Design:**

- Tenant registers a webhook URL (new field on `tenants`, or a dedicated `webhooks` table for
  multiple event subscriptions).
- Signed payload delivery — HMAC using a per-tenant secret, so tenants can verify authenticity,
  the same pattern Stripe itself uses for its own webhooks (fitting, given Phase 19 already
  integrates Stripe).
- Fire-and-forget with retry/backoff — never block the triggering request on webhook delivery.

**Tasks:**

- Add webhook URL + secret fields to tenant config (surfaced in Phase 16's admin UI)
- Implement signed delivery + retry logic
- Document the payload schema and signature verification for tenants

**Verification:**

```bash
# Using a local test receiver or a tool like webhook.site:
# trigger an offer analysis, confirm a signed POST arrives with the expected event payload
```

---

## Phase 26 — Staging Environment

**Goal:** A pre-production environment mirroring Phase 14's real deployment, so changes touching
tenant data or billing get exercised before they reach real tenants.

**Design:**

- A second instance of the same image (Phase 14), not a separate codebase — separate
  `TENANT_DB_ENCRYPTION_KEY`, separate managed Postgres instance, Stripe **test-mode** keys.
- Decide the promotion flow deliberately: auto-deploy every merge to staging, with production
  requiring a manual trigger/approval, is a reasonable default — but this is a real process
  decision, not something to default silently.

**Tasks:**

- Stand up a second Phase 14 deployment target pointed at staging config
- Implement the chosen promotion flow
- Use Stripe test-mode keys in staging so Phase 19 billing can be exercised safely

**Verification:**

```bash
curl https://staging.<your-domain>/health
# → confirms staging is live and isolated from production tenant data
```

---

## Phase 27 — Status Page & Uptime Monitoring

**Goal:** External visibility into uptime for tenants, and alerting for you when something is
actually down — from outside your own infrastructure, so it still works when that infrastructure
doesn't.

**Design:**

- An external uptime monitor (UptimeRobot, Better Uptime, etc. — free tiers exist) hitting the
  public `/health` endpoint on a schedule, alerting you on failure.
- A public status page (many uptime tools include a hosted one) linked from Phase 20's site and
  Phase 11's interim landing page.
- **TLS certificate expiry monitoring** lives here too, not bolted onto Phase 14's deployment
  mechanics — this phase is already "external monitoring/alerting," which is exactly what
  expiry checking is. Most managed platforms (Let's Encrypt via Caddy, Fly.io, Render)
  auto-renew, but silent auto-renewal failure is a real failure mode worth an explicit alert,
  not just trust that renewal always works. Most uptime tools (including UptimeRobot/Better
  Uptime) support this as a monitor type alongside plain HTTP checks — one more monitor, not
  a separate tool.

**Tasks:**

- Set up an external monitor against `/health`
- Set up a TLS expiry monitor against the same domain, same tool
- Configure alerting to wherever you actually want to be notified
- Link the public status page from Phases 20 and 11

**Verification:**

```bash
# In a safe/staging context, temporarily return non-200 from /health and confirm
# the monitor actually fires an alert within its configured check interval.

# Confirm the TLS expiry monitor is actually configured (not just the uptime one):
# check the monitoring tool's dashboard shows a cert-expiry check for the domain,
# with a real expiry date pulled from the live certificate — not a placeholder.
```

---

## Phase 28 — LLM Provider Fallback

**Goal:** Graceful degradation if the primary LLM provider has an outage, using multi-provider
support `src/config.py` already has (Ollama, OpenAI, Gemini alongside Anthropic).

**No need to hand-roll this:** `pydantic_ai.models.fallback.FallbackModel` already exists and
does exactly this — retries against a secondary model if the primary fails — confirmed present
in this project's installed `pydantic-ai` version. This phase is wiring it in and deciding
policy, not building new retry logic.

**Design:**

- Wrap `trade_advisor`'s model in a `FallbackModel` chain: primary provider, then a configured
  secondary (e.g. Anthropic → OpenAI, or → a local/cloud Ollama model already supported).
- Treat this as a **paid-tier** differentiator (Phase 19) — the free tier can reasonably just
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

## Phase 29 — Tenant Engagement & Retention Analytics

**Goal:** Answer "are our customers actually sticking around" — a real, different question
from what's already planned. Phase 18 aggregates *Pokemon trend data* across tenants; Phase
23 tracks *LLM cost/tokens* per tenant. Neither says whether a tenant who signed up ever made
a real call, or is still using the API weeks later. That's a business-health question a SaaS
product with paid tiers (Phase 19) genuinely needs answered.

**Tool: Mixpanel or PostHog** — either fits (product/event analytics: funnels, retention,
cohorts). If Phase 20/11's marketing site already adopted one for visitor/conversion
tracking, reuse that same vendor rather than running two separate analytics tools for
website visitors vs. API tenants, unless there's a specific reason to split them.

**Scope — usage metadata only, never trade content:** events here are `tenant_id` + event
name + timestamp (`tenant_registered`, `first_api_call`, per-endpoint usage). Never request
bodies, never which Pokemon or trades were involved — that's Phase 18's domain, with its own
separate consent story (`analytics_opt_in`). This is closer to ordinary product telemetry
(understanding your own customers' engagement) than the tenant-data-privacy question Phase 18
had to solve, but it's worth staying deliberate about that boundary rather than letting it
blur — it's the same "state your scope explicitly" discipline as everywhere else in this doc.

**Design:**

- Instrument events server-side (tenants interact via API, not a browser — no client-side JS
  tracking makes sense here): `tenant_registered` on successful registration (Phase 15),
  `first_api_call` on a new tenant's first successful request, and per-request usage events
  tagged by `tenant_id` and endpoint.
- **Activation funnel**: signup → first real API call — what fraction of tenants ever use
  what they signed up for.
- **Retention**: cohort tenants by signup week/month, track what fraction are still calling
  the API N days/weeks later.

**Tasks:**

- Choose Mixpanel or PostHog (reuse Phase 20/11's choice if one was already made)
- Add a small `src/analytics/engagement.py` wrapping event-tracking calls
- Emit `tenant_registered` from Phase 15's registration flow
- Emit `first_api_call` / per-request usage events from Phase 4's request-logging middleware
  (or a dedicated hook, if piggybacking on that middleware gets awkward)
- Build the activation funnel and retention cohort views in the chosen tool's dashboard

**Verification:**

```bash
# Register a test tenant, make one real API call, confirm both events
# appear in the tool's live event stream:
uv run python scripts/provision_tenant.py "engagement-test" "postgresql://user:pass@host/db"
curl -H "X-API-Key: <generated-key>" "http://localhost:8080/trade/suggestions?user_id=user_001"
# → tenant_registered and first_api_call both visible in Mixpanel/PostHog's live view
```
