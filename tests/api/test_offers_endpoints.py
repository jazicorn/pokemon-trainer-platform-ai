"""Tests for the offers endpoints — GET /offers, POST /offers/send
(ROADMAP.md Phase 5).
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

    These tests exercise the offers endpoints themselves, not auth — that's
    already covered by tests/api/test_auth.py.
    """
    app.dependency_overrides[require_api_key] = lambda: TenantContext(
        tenant_id="test-tenant", platform_db_url="postgresql://fake"
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestOffers:
    def test_success_with_explicit_user_id(self, authenticated_client: TestClient) -> None:
        with patch("api.app.get_pending_offers", new=AsyncMock(return_value="You have 2 offers")) as mock_offers:
            response = authenticated_client.get("/offers?user_id=user_042")

        assert response.status_code == 200
        assert response.json() == {"result": "You have 2 offers", "status": "ok"}
        mock_offers.assert_awaited_once_with(user_id="user_042")

    def test_default_user_id(self, authenticated_client: TestClient) -> None:
        with patch("api.app.get_pending_offers", new=AsyncMock(return_value="x")) as mock_offers:
            authenticated_client.get("/offers")

        mock_offers.assert_awaited_once_with(user_id="user_001")

    def test_agent_failure_is_500(self, authenticated_client: TestClient) -> None:
        with patch("api.app.get_pending_offers", new=AsyncMock(side_effect=RuntimeError("boom"))):
            response = authenticated_client.get("/offers")

        assert response.status_code == 500

    def test_without_key_is_401(self) -> None:
        assert TestClient(app).get("/offers").status_code == 401


class TestOffersSend:
    def test_success(self, authenticated_client: TestClient) -> None:
        with patch("api.app.send_trade_offer", new=AsyncMock(return_value="Offer #1 sent")) as mock_send:
            response = authenticated_client.post(
                "/offers/send",
                json={
                    "sender_id": "user_001",
                    "recipient_id": "user_002",
                    "offered_pokemon": "Eevee",
                    "requested_pokemon": "Vaporeon",
                },
            )

        assert response.status_code == 200
        assert response.json() == {"result": "Offer #1 sent", "status": "ok"}
        mock_send.assert_awaited_once_with(
            sender_id="user_001",
            recipient_id="user_002",
            offered_pokemon="Eevee",
            requested_pokemon="Vaporeon",
        )

    def test_missing_required_field_is_422(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post("/offers/send", json={"sender_id": "user_001"})
        assert response.status_code == 422

    def test_without_key_is_401(self) -> None:
        response = TestClient(app).post(
            "/offers/send",
            json={
                "sender_id": "user_001",
                "recipient_id": "user_002",
                "offered_pokemon": "Eevee",
                "requested_pokemon": "Vaporeon",
            },
        )
        assert response.status_code == 401
