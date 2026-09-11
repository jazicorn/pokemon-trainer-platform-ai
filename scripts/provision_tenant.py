#!/usr/bin/env python3
"""Provision a new API tenant — admin override path (ROADMAP.md Phase 3).

Generates a new API key, encrypts the tenant's own `platform_db_url` at rest,
and inserts the row into `data/tenants.db`. The generated key is printed
exactly once here — it is never stored or retrievable again, so capture it
now and hand it to the tenant.

`POST /v1/accounts/register` (ROADMAP.md Phase 15) is the normal way in now;
this script is for support/manual cases — e.g. a tenant who can't self-serve,
or a `platform_db_url` you want to register without going through that
endpoint's own connectivity validation.

Usage:
    uv run python scripts/provision_tenant.py <name> <platform_db_url>

Requires TENANT_DB_ENCRYPTION_KEY to be set — generate one with:
    uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable — mirrors app.py/api_server.py's own sys.path setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <name> <platform_db_url>", file=sys.stderr)
        raise SystemExit(1)

    name, platform_db_url = sys.argv[1], sys.argv[2]

    from api.tenants import create_tenant

    tenant_id, api_key = create_tenant(name, platform_db_url)

    print(f"Tenant provisioned: {name} (id={tenant_id})")
    print(f"API key (shown once): {api_key}")
    print("Store this now — it cannot be retrieved again.")


if __name__ == "__main__":
    main()
