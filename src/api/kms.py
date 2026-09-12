"""Envelope encryption via HashiCorp Vault's Transit secrets engine (ROADMAP_PLATFORM.md
Phase 17).

Replaces Phase 3's single static `TENANT_DB_ENCRYPTION_KEY` (one leak decrypts every
tenant's `platform_db_url` at once) with a fresh, randomly-generated Data Encryption Key
(DEK) per tenant. Vault's master key never leaves Vault — it only ever "wraps" (encrypts)
each tenant's own DEK; the *wrapped* DEK is what `api.tenants` stores, alongside a
Fernet ciphertext of the actual `platform_db_url` encrypted locally with that DEK.

Decrypting a tenant's URL means asking Vault to unwrap that one DEK — an authenticated,
logged API call, giving a real audit trail ("who/what decrypted tenant X's credentials,
and when") the old static-key design had no equivalent of. Key rotation becomes
tractable too: rotate Vault's own Transit key and re-wrap the (small) DEKs, rather than
decrypting and re-encrypting every tenant's real data by hand.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from config import config

if TYPE_CHECKING:
    # See data/platform_db.py's own note on this pattern: this module stays
    # importable when the optional `platform-db` group (hvac) isn't
    # installed, since `from __future__ import annotations` makes every
    # annotation below a lazy string. The ignore covers pyright runs that
    # also lack the group synced — CI's ci-quality.yml syncs it.
    import hvac  # pyright: ignore[reportMissingImports]


class VaultNotConfiguredError(RuntimeError):
    """VAULT_ADDR/VAULT_TOKEN aren't set — raised at the point of use, same
    pattern as api.tenants._get_fernet()'s missing-key error.
    """


def _client() -> hvac.Client:
    import hvac  # pyright: ignore[reportMissingImports]

    if not config.vault_addr or not config.vault_token:
        raise VaultNotConfiguredError(
            "VAULT_ADDR and VAULT_TOKEN must both be set to use envelope encryption. "
            "See docs/1PASSWORD.md for how this project stores them."
        )
    return hvac.Client(url=config.vault_addr, token=config.vault_token)


def wrap_new_dek() -> tuple[bytes, str]:
    """Generate a fresh Data Encryption Key via Vault Transit.

    Returns:
        (plaintext_dek, wrapped_dek) — plaintext_dek is used immediately to
        Fernet-encrypt one tenant's platform_db_url and then discarded, never
        stored; wrapped_dek is what actually gets persisted in tenants.db.
    """
    client = _client()
    response: dict[str, Any] = client.secrets.transit.generate_data_key(
        name=config.vault_transit_key_name, key_type="plaintext"
    )
    plaintext_b64: str = response["data"]["plaintext"]
    wrapped_dek: str = response["data"]["ciphertext"]
    # hvac ships no type stubs at all — even with the explicit annotations
    # above, pyright still can't fully resolve the response shape here,
    # a library limitation rather than a real type error.
    return base64.b64decode(plaintext_b64), wrapped_dek  # pyright: ignore[reportUnknownArgumentType]


@lru_cache(maxsize=256)
def unwrap_dek(wrapped_dek: str) -> bytes:
    """Unwrap a previously-wrapped DEK back to its plaintext form.

    Cached by the wrapped ciphertext itself (stable per tenant, since a
    tenant's DEK is never re-wrapped after creation) so decrypting the same
    tenant's platform_db_url on every authenticated request doesn't round-
    trip to Vault every single time — mirroring data/platform_db.py's own
    get_platform_db_for() cache.
    """
    client = _client()
    response: dict[str, Any] = client.secrets.transit.decrypt_data(
        name=config.vault_transit_key_name, ciphertext=wrapped_dek
    )
    plaintext_b64: str = response["data"]["plaintext"]
    return base64.b64decode(plaintext_b64)  # pyright: ignore[reportUnknownArgumentType]
