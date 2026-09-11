"""Tests for rate limiting (ROADMAP.md Phase 9 security checklist)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from api.app import app as real_app
from api.app import limiter as real_limiter


class TestRateLimiting:
    """Deliberately NOT the real api.app `app`/`limiter` singletons — the
    real app carries a shared, in-memory 100/minute bucket used by every
    other test in this suite; hammering it here to actually trip a 429
    would start rate-limiting unrelated tests that run afterward in the
    same process. This isolated app has its own limiter and a low enough
    limit to trip in a handful of requests.
    """

    def _make_client(self) -> TestClient:
        test_app = FastAPI()
        limiter = Limiter(key_func=get_remote_address, default_limits=["3/minute"])
        test_app.state.limiter = limiter
        # See api/app.py's own note on this: slowapi's handler is typed narrower than
        # add_exception_handler expects, safe at runtime despite the static mismatch.
        test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
        test_app.add_middleware(SlowAPIMiddleware)

        @test_app.get("/ping")
        async def ping() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction] — registered via decorator
            return {"status": "ok"}

        return TestClient(test_app)

    def test_requests_within_the_limit_succeed(self) -> None:
        client = self._make_client()

        for _ in range(3):
            assert client.get("/ping").status_code == 200

    def test_exceeding_the_limit_returns_429(self) -> None:
        client = self._make_client()

        for _ in range(3):
            client.get("/ping")
        response = client.get("/ping")

        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["error"]


class TestAppWiring:
    """Confirm api.app actually wires up rate limiting — without generating
    real traffic against the shared app/limiter singleton (see above).
    """

    def test_limiter_is_attached_to_app_state(self) -> None:
        assert real_app.state.limiter is real_limiter

    def test_default_limit_is_configured(self) -> None:
        assert real_limiter._default_limits  # pyright: ignore[reportPrivateUsage]

    def test_slowapi_middleware_is_registered(self) -> None:
        assert any(m.cls is SlowAPIMiddleware for m in real_app.user_middleware)

    def test_in_memory_fallback_is_enabled(self) -> None:
        """Without this, a Redis outage would make every rate-limit check
        raise instead of falling back — 500ing the whole API rather than
        just skipping limiting during the outage. Not slowapi's own
        default; must be set explicitly (see api/app.py's own note).
        """
        assert real_limiter._in_memory_fallback_enabled  # pyright: ignore[reportPrivateUsage]

    def test_accounts_register_has_its_own_stricter_limit(self) -> None:
        """POST /v1/accounts/register (ROADMAP.md Phase 15) is the one route
        an anonymous caller can hit with no key at all, so it carries its own
        tighter limit instead of the 100/minute app-wide default.
        """
        route_limits = real_limiter._route_limits  # pyright: ignore[reportPrivateUsage]
        key = "api.app.accounts_register"
        assert key in route_limits
        assert any(str(limit.limit) == "5 per 1 minute" for limit in route_limits[key])
