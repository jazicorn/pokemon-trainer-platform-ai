"""API key authentication for the HTTP API — see ROADMAP.md Phase 3.

Every protected route depends on `require_api_key`, which resolves the
caller's `X-API-Key` header to a `TenantContext` (tenant_id + that tenant's
own `platform_db_url`) via FastAPI's dependency injection — every handler
receives it as a parameter, never a global. `/health` is the one route that
doesn't use this dependency at all.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from api.tenants import TenantContext, get_tenant_by_key_hash, hash_api_key

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Annotated[str | None, Security(_api_key_header)]) -> TenantContext:
    """Resolve the X-API-Key header to a tenant, or raise 401/403.

    401: header missing entirely. 403: header present but doesn't match any
    active tenant (wrong key, or a deactivated one — deliberately
    indistinguishable, so a revoked key doesn't reveal it once existed).
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    tenant = get_tenant_by_key_hash(hash_api_key(api_key))
    if tenant is None:
        raise HTTPException(status_code=403, detail="Invalid or inactive API key")

    return tenant
