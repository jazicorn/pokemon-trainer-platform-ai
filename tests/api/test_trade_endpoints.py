"""Tests for the core trade endpoints — /chat, /trade/evaluate,
/trade/suggestions (ROADMAP.md Phase 4).
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.auth import require_api_key
from api.tenants import TenantContext


@pytest.fixture
def authenticated_client() -> Generator[TestClient]:
    """A TestClient with require_api_key overridden to a fixed fake tenant.

    These tests exercise the trade endpoints themselves, not auth — that's
    already covered by tests/api/test_auth.py. Cleans up the override
    afterward (try/finally) so it can't leak into other test modules that
    share this same `app` singleton.
    """
    app.dependency_overrides[require_api_key] = lambda: TenantContext(
        tenant_id="test-tenant", platform_db_url="postgresql://fake"
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestChat:
    def test_success(self, authenticated_client: TestClient) -> None:
        with patch("api.app.evaluate_trade", new=AsyncMock(return_value="Good trade!")) as mock_eval:
            response = authenticated_client.post("/chat", json={"message": "Should I trade my Pikachu?"})

        assert response.status_code == 200
        assert response.json() == {"result": "Good trade!", "status": "ok"}
        mock_eval.assert_awaited_once_with(
            raw_query="Should I trade my Pikachu?",
            user_id="user_001",
            conversation_context=None,
        )

    def test_agent_failure_is_500_and_reported_to_sentry(self, authenticated_client: TestClient) -> None:
        error = RuntimeError("boom")
        with (
            patch("api.app.evaluate_trade", new=AsyncMock(side_effect=error)),
            patch("api.app.sentry_sdk.capture_exception") as mock_capture,
        ):
            response = authenticated_client.post("/chat", json={"message": "hi"})

        assert response.status_code == 500
        mock_capture.assert_called_once_with(error)


class TestTradeEvaluate:
    def test_success(self, authenticated_client: TestClient) -> None:
        with patch("api.app.evaluate_trade", new=AsyncMock(return_value="Fair trade")) as mock_eval:
            response = authenticated_client.post(
                "/trade/evaluate",
                json={"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard"},
            )

        assert response.status_code == 200
        assert response.json() == {"result": "Fair trade", "status": "ok"}
        mock_eval.assert_awaited_once_with(
            offered_pokemon="Pikachu",
            requested_pokemon="Charizard",
            user_id="user_001",
            conversation_context=None,
        )

    def test_missing_required_field_is_422(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post("/trade/evaluate", json={"offered_pokemon": "Pikachu"})
        assert response.status_code == 422


class TestTradeSuggestions:
    def test_success_with_explicit_user_id(self, authenticated_client: TestClient) -> None:
        with patch("api.app.get_trade_suggestions", new=AsyncMock(return_value="Try trading X")) as mock_sugg:
            response = authenticated_client.get("/trade/suggestions?user_id=user_042")

        assert response.status_code == 200
        assert response.json() == {"result": "Try trading X", "status": "ok"}
        mock_sugg.assert_awaited_once_with(user_id="user_042")

    def test_default_user_id(self, authenticated_client: TestClient) -> None:
        with patch("api.app.get_trade_suggestions", new=AsyncMock(return_value="x")) as mock_sugg:
            authenticated_client.get("/trade/suggestions")

        mock_sugg.assert_awaited_once_with(user_id="user_001")


class TestAuthStillAppliesToNewRoutes:
    """Confirm these new routes are actually behind require_api_key, not
    accidentally exempted — using the real dependency, no override.
    """

    def test_chat_without_key_is_401(self) -> None:
        assert TestClient(app).post("/chat", json={"message": "hi"}).status_code == 401

    def test_trade_evaluate_without_key_is_401(self) -> None:
        response = TestClient(app).post(
            "/trade/evaluate", json={"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard"}
        )
        assert response.status_code == 401

    def test_trade_suggestions_without_key_is_401(self) -> None:
        assert TestClient(app).get("/trade/suggestions").status_code == 401
