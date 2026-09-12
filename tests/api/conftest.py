"""Shared fixtures for tests/api/.

The Vault-faking fixture every create_tenant() call needs now
(ROADMAP_PLATFORM.md Phase 17) lives in tests/conftest.py — tests/admin/
calls create_tenant() too, so it's project-wide, not specific to this
package.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> Generator[None]:  # pyright: ignore[reportUnusedFunction]  # autouse fixture, never referenced by name
    """The real api.app `limiter` is a process-global singleton — several
    test files' `client` fixtures reuse the real `app` (not an isolated
    test app; see test_rate_limiting.py's own note on why it avoids doing
    that for its own assertions), so a route with a tight limit like
    ACCOUNTS_REGISTER's 5/minute can accumulate hits across unrelated tests
    in the same run and start returning 429s unrelated to what a given test
    actually checks.

    Toggling `enabled` (not calling `limiter.reset()`) deliberately: reset()
    talks to whatever backend storage_uri points at, which in a real dev
    environment can be a live Redis instance (RATE_LIMIT_STORAGE_URI in
    .env) — a test fixture has no business making that network call.
    `enabled = False` short-circuits slowapi's check entirely, no storage
    touched. test_rate_limiting.py's own tests use a fully separate,
    isolated Limiter instance, so this doesn't affect what they verify.
    """
    from api.app import limiter

    previously_enabled = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = previously_enabled
