"""Full-stack integration tests and cross-cutting auth coverage that don't
belong to any single phase (ROADMAP.md Phase 8).

Audited tests/api/ against Phase 9's endpoint table: every route already has
dedicated coverage from the phases that added it, no gaps found. What's below
is what those per-route tests can't cover on their own: chaining real routes
together, and one real tenant's key resolving across every route type.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import config as config_module
from api.app import app
from api.tenants import create_tenant


@pytest.fixture
def isolated_tenants_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "test_tenants.db"
    monkeypatch.setattr("api.tenants.get_db_path", lambda: db_file)
    return db_file


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(config_module.config, "tenant_db_encryption_key", key)
    return key


@pytest.fixture
def isolated_offers_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect memory.database's SQLite file — this test never touches the
    real data/memory.db. Also force get_platform_db() to None so
    TradeOffersManager uses the local SQLite path (see its own seed_offers()
    docstring: PLATFORM_DB_URL, if set, is treated as the source of truth
    and local seeding is skipped entirely).
    """
    db_file = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory.database.get_db_path", lambda: db_file)
    monkeypatch.setattr("data.platform_db.get_platform_db", lambda: None)
    return db_file


@pytest.fixture
def client(isolated_tenants_db: Path, encryption_key: str, isolated_offers_db: Path) -> Generator[TestClient]:
    """A real TestClient with no dependency overrides — every test in this
    file exercises the actual require_api_key path against a real
    provisioned tenant, not a mocked one. lifespan doesn't run (TestClient
    isn't used as a context manager here), so no real startup() side effects.
    """
    yield TestClient(app)


class TestOfferSendThenFetch:
    """Send an offer via one route, fetch it back via another — something no
    single phase's own tests cover, since Phase 6's tests mock
    send_trade_offer/get_pending_offers independently rather than chaining
    the real TradeOffersManager/SQLite flow between them. Only the LLM
    boundary (evaluate_trade) is mocked; everything else is real.
    """

    def test_sent_offer_appears_in_recipients_inbox_with_analysis(self, client: TestClient) -> None:
        _, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        headers = {"X-API-Key": raw_key}

        with patch("agents.trade_advisor_api.evaluate_trade", new=AsyncMock(return_value="Solid trade.")):
            send_response = client.post(
                "/offers/send",
                headers=headers,
                json={
                    "sender_id": "user_001",
                    "recipient_id": "user_002",
                    "offered_pokemon": "Eevee",
                    "requested_pokemon": "Vaporeon",
                },
            )
            assert send_response.status_code == 200

            fetch_response = client.get("/offers?user_id=user_002", headers=headers)
            assert fetch_response.status_code == 200

        result = fetch_response.json()["result"]
        assert "Eevee" in result
        assert "Vaporeon" in result
        assert "Solid trade." in result


class TestSingleTenantKeyAcrossAllRoutes:
    """Phase 3's own tests prove auth logic works in isolation, against one
    representative route. This proves the SAME real tenant/key resolves
    correctly across every actual protected route, not just one.
    """

    def test_same_key_resolves_on_every_protected_route(self, client: TestClient) -> None:
        _, raw_key = create_tenant("acme", "postgresql://u:p@h/db")
        headers = {"X-API-Key": raw_key}

        with (
            patch("api.app.evaluate_trade", new=AsyncMock(return_value="ok")),
            patch("api.app.get_trade_suggestions", new=AsyncMock(return_value="ok")),
            patch("api.app.get_pending_offers", new=AsyncMock(return_value="ok")),
            patch("api.app.send_trade_offer", new=AsyncMock(return_value="ok")),
            patch("api.app.query_pokedex", new=AsyncMock(return_value="ok")),
            patch("api.app.query_market", new=AsyncMock(return_value="ok")),
        ):
            responses = {
                "POST /chat": client.post("/chat", headers=headers, json={"message": "hi"}),
                "POST /trade/evaluate": client.post(
                    "/trade/evaluate",
                    headers=headers,
                    json={"offered_pokemon": "Pikachu", "requested_pokemon": "Charizard"},
                ),
                "GET /trade/suggestions": client.get("/trade/suggestions", headers=headers),
                "GET /offers": client.get("/offers", headers=headers),
                "POST /offers/send": client.post(
                    "/offers/send",
                    headers=headers,
                    json={
                        "sender_id": "a",
                        "recipient_id": "b",
                        "offered_pokemon": "Eevee",
                        "requested_pokemon": "Vaporeon",
                    },
                ),
                "POST /pokedex/query": client.post("/pokedex/query", headers=headers, json={"question": "hi"}),
                "POST /market/query": client.post("/market/query", headers=headers, json={"question": "hi"}),
            }

        for route, response in responses.items():
            assert response.status_code == 200, f"{route} failed with {response.status_code}: {response.text}"
