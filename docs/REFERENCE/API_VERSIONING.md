# API Versioning

Every protected route is mounted under `/v1` (`POST /v1/chat`, `GET /v1/trade/suggestions`,
etc.) — set in `src/api/app.py`'s `app.include_router(protected_router, prefix="/v1")`.
`GET /health` stays unversioned: it's infrastructure-level, not business logic, matching its
existing exemption from `X-API-Key` auth.

## Scheme

URL-path versioning, not a header — simplest and most discoverable for API consumers. An
unversioned path (e.g. `GET /offers`) returns `404`, not a redirect: a caller has to be
explicit about which version they're targeting.

## Deprecation policy

- A new breaking change ships as `/v2`, not a modification to `/v1` — existing `/v1` callers
  are never broken by a `/v2` release.
- `/v1` stays supported for at least 6 months after `/v2` ships, with a deprecation notice
  (documented here, and via a `Deprecation` response header once `/v2` exists) before removal.
- Additive, non-breaking changes (a new optional field, a new endpoint) land directly on `/v1`
  — they don't require a new version.
