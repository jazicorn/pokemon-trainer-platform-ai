#!/usr/bin/env python3
"""Migrate tenants.db off Phase 3's static-key encryption to Phase 17's
per-tenant Vault-wrapped DEK scheme.

Not required to keep the API running — api.tenants._decrypt_stored_url()
already supports both schemes side by side, dispatching per row on whether
wrapped_dek is set. This script is for actually closing that gap: every
existing tenant is still one leaked TENANT_DB_ENCRYPTION_KEY away from every
other tenant's platform_db_url being decryptable at once, until it's run.

Idempotent — re-running only touches rows still on the old scheme
(api.tenants.migrate_tenant_to_vault_encryption() is a no-op for anything
already migrated), so it's safe to run repeatedly, e.g. after a batch of
new self-hosted signups.

Usage:
    uv run python scripts/migrate_to_vault_encryption.py

Requires TENANT_DB_ENCRYPTION_KEY (to decrypt existing rows) and
VAULT_ADDR/VAULT_TOKEN (to wrap each row's new DEK) to all be set — see
docs/1PASSWORD.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable — mirrors app.py/api_server.py/provision_tenant.py's own setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    from config import config

    if not config.tenant_db_encryption_key:
        print("TENANT_DB_ENCRYPTION_KEY is not set — nothing to decrypt existing rows with.", file=sys.stderr)
        raise SystemExit(1)
    if not config.vault_addr or not config.vault_token:
        print("VAULT_ADDR and VAULT_TOKEN must both be set — nothing to wrap new DEKs with.", file=sys.stderr)
        raise SystemExit(1)

    from api.tenants import list_unmigrated_tenant_ids, migrate_tenant_to_vault_encryption

    tenant_ids = list_unmigrated_tenant_ids()
    if not tenant_ids:
        print("Nothing to migrate — every tenant is already on the Vault-wrapped-DEK scheme.")
        return

    print(f"Migrating {len(tenant_ids)} tenant(s)...")
    migrated = 0
    for tenant_id in tenant_ids:
        if migrate_tenant_to_vault_encryption(tenant_id):
            migrated += 1
            print(f"  {tenant_id}: migrated")
        else:
            print(f"  {tenant_id}: skipped (already migrated or no longer exists)")

    print(f"Done — {migrated} tenant(s) migrated.")


if __name__ == "__main__":
    main()
