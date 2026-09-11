# Deployment (Fly.io)

How to run the Web API as a real, publicly-reachable service (ROADMAP.md Phase 14). This is the
production deploy path — `docker-compose.yml`'s `api` service is for local dev/testing parity
only, not what actually runs in production.

## Architecture

One Fly app:

- **`<name>-api`** — public. This repo's own `Dockerfile`, built and deployed via `fly.toml`.
  TLS is handled entirely by Fly's edge (`force_https = true` in `fly.toml`) — no Caddy/nginx
  needed. A persistent Fly volume holds `/app/data`, so `data/tenants.db` (Phase 3) survives
  redeploys.
  The Dockerfile's own `CMD` launches the CLI (`app.py`), since the same image is also used
  for local CLI use — `fly.toml`'s `[processes]` block overrides that for this deployment,
  running `api_server.py` instead.

RAG's vector storage is **Chroma Cloud** (a managed service, not something this deploy runs
itself) — see ROADMAP.md Phase 14. Phase 14 originally planned a second, private
`<name>-chromadb` Fly app (self-hosted ChromaDB); Chroma Cloud replaces that outright, so
there's no second app or volume for it here.

## One-time setup

```bash
# Install flyctl if you haven't: https://fly.io/docs/flyctl/install/
fly auth login

# Edit fly.toml's app name/region first, then:
fly apps create <name>-api
fly volumes create data_volume --app <name>-api --size 1 --region <your-region>
```

## Secrets

Never in `fly.toml` (it's committed) — always via `fly secrets set`:

```bash
fly secrets set --app <name>-api \
  ANTHROPIC_API_KEY=<your key> \
  TENANT_DB_ENCRYPTION_KEY=<generate below> \
  SENTRY_DSN=<your Sentry DSN> \
  RATE_LIMIT_STORAGE_URI=<your Upstash Redis rediss:// URL> \
  CHROMA_API_KEY=<your Chroma Cloud API key> \
  CHROMA_TENANT=<your Chroma Cloud tenant> \
  CHROMA_DATABASE=<your Chroma Cloud database>
```

Generate `TENANT_DB_ENCRYPTION_KEY`:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Back this up outside of Fly** (a password manager, matching this project's existing
1Password setup — see `docs/1PASSWORD.md`). Losing it makes every tenant's stored
`platform_db_url` permanently unrecoverable, not just hard to find — this is the same warning
Phase 3 already carries for local dev, and it applies just as much here.

## Deploy

```bash
fly deploy --app <name>-api
```

## Provisioning a tenant against the deployed API

Same script as local dev, pointed at the deployed encryption key (run this wherever you have
`TENANT_DB_ENCRYPTION_KEY` available — it only needs to reach `data/tenants.db`, which for a
real deployment means running it as a one-off Fly machine or via `fly ssh console`, not your own
laptop's local `data/tenants.db`):

```bash
fly ssh console --app <name>-api -C "uv run python scripts/provision_tenant.py '<tenant-name>' '<their platform_db_url>'"
```

## Security checklist re-verification

Re-confirmed true as of this deploy (ROADMAP.md Phase 14's checklist) — not new code, just
re-checked by direct inspection since the checklist was originally written:

- **Input validation** — every route still takes a typed Pydantic request model or a typed
  `Query(...)` param, never a raw dict.
- **SQL injection prevention** — every `platform_db.py` query still uses psycopg's `%s`
  parameterization; no f-strings or `.format()` building SQL anywhere in that file.
- **Secrets management** — no plaintext secret literals found committed anywhere in the repo.

## Verification

```bash
curl https://<name>-api.fly.dev/health
# -> {"status": "ok", "chromadb": true}
# "chromadb" here means "the RAG backend is reachable" (Chroma Cloud, since
# CHROMA_API_KEY is set — see ROADMAP.md Phase 14), not literally
# self-hosted ChromaDB.

curl -X POST https://<name>-api.fly.dev/v1/trade/evaluate \
  -H "X-API-Key: <a tenant's provisioned key>" \
  -H "Content-Type: application/json" \
  -d '{"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard", "user_id": "<a real user id>"}'

# TLS is enforced by Fly's edge itself (force_https) — plain HTTP should redirect, never serve:
curl -i http://<name>-api.fly.dev/health

# Rate limiting (app-level, not Fly's edge — see ROADMAP.md Phase 14):
for i in $(seq 1 110); do curl -s -o /dev/null -w "%{http_code}\n" \
  https://<name>-api.fly.dev/health; done | sort | uniq -c
# -> some requests eventually return 429

# Security headers (app-level middleware, not a reverse-proxy config — Fly gives no such layer):
curl -sI https://<name>-api.fly.dev/health | grep -iE "strict-transport-security|x-content-type-options|^server:"
# -> HSTS and X-Content-Type-Options present; Server header absent (uvicorn's server_header=False)

# Persistent volume check — restart and confirm tenants.db survived:
fly machine restart --app <name>-api $(fly machine list --app <name>-api -q)
curl -H "X-API-Key: <the same tenant key>" https://<name>-api.fly.dev/health
```
