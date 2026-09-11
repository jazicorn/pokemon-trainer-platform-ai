"""Tests for the knowledge-query endpoints — POST /v1/pokedex/query,
POST /v1/market/query (ROADMAP.md Phase 6).
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.auth import require_api_key
from api.paths import MARKET_QUERY, POKEDEX_QUERY
from api.tenants import TenantContext


@pytest.fixture
def authenticated_client() -> Generator[TestClient]:
    """A TestClient with require_api_key overridden to a fixed fake tenant.

    These tests exercise the query endpoints themselves, not auth — that's
    already covered by tests/api/test_auth.py.
    """
    app.dependency_overrides[require_api_key] = lambda: TenantContext(
        tenant_id="test-tenant", platform_db_url="postgresql://fake"
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestPokedexQuery:
    def test_success(self, authenticated_client: TestClient) -> None:
        with patch("api.app.query_pokedex", new=AsyncMock(return_value="4x weak to Rock")) as mock_query:
            response = authenticated_client.post(
                POKEDEX_QUERY,
                json={"question": "What are Charizard's weaknesses?", "user_id": "user_042"},
            )

        assert response.status_code == 200
        assert response.json() == {"result": "4x weak to Rock", "status": "ok"}
        mock_query.assert_awaited_once_with(question="What are Charizard's weaknesses?", user_id="user_042")

    def test_default_user_id(self, authenticated_client: TestClient) -> None:
        with patch("api.app.query_pokedex", new=AsyncMock(return_value="x")) as mock_query:
            authenticated_client.post(POKEDEX_QUERY, json={"question": "hi"})

        mock_query.assert_awaited_once_with(question="hi", user_id="user_001")

    def test_agent_failure_is_500(self, authenticated_client: TestClient) -> None:
        with patch("api.app.query_pokedex", new=AsyncMock(side_effect=RuntimeError("boom"))):
            response = authenticated_client.post(POKEDEX_QUERY, json={"question": "hi"})

        assert response.status_code == 500

    def test_without_key_is_401(self) -> None:
        response = TestClient(app).post(POKEDEX_QUERY, json={"question": "hi"})
        assert response.status_code == 401


class TestMarketQuery:
    def test_success_ignores_user_id(self, authenticated_client: TestClient) -> None:
        """query_market has no per-user state — user_id in the request body
        (present because it shares QueryRequest with /v1/pokedex/query) must
        never be passed through to it."""
        with patch("api.app.query_market", new=AsyncMock(return_value="Charizard trending up")) as mock_query:
            response = authenticated_client.post(
                MARKET_QUERY,
                json={"question": "Which Pokemon are trending?", "user_id": "user_042"},
            )

        assert response.status_code == 200
        assert response.json() == {"result": "Charizard trending up", "status": "ok"}
        mock_query.assert_awaited_once_with(question="Which Pokemon are trending?")

    def test_agent_failure_is_500(self, authenticated_client: TestClient) -> None:
        with patch("api.app.query_market", new=AsyncMock(side_effect=RuntimeError("boom"))):
            response = authenticated_client.post(MARKET_QUERY, json={"question": "hi"})

        assert response.status_code == 500

    def test_without_key_is_401(self) -> None:
        response = TestClient(app).post(MARKET_QUERY, json={"question": "hi"})
        assert response.status_code == 401
