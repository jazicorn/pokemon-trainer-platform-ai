"""Tests for API versioning (ROADMAP.md Phase 7)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app
from api.paths import API_PREFIX, HEALTH, OFFERS


class TestVersioning:
    def test_protected_routes_are_mounted_under_v1(self) -> None:
        response = TestClient(app).get(OFFERS)
        # 401 (missing key), not 404 — confirms the route exists at this path.
        assert response.status_code == 401

    def test_unversioned_protected_path_is_404(self) -> None:
        # OFFERS already carries API_PREFIX; strip it to get the bare route
        # path and confirm it isn't reachable without the prefix.
        response = TestClient(app).get(OFFERS.removeprefix(API_PREFIX))
        assert response.status_code == 404

    def test_health_stays_unversioned(self) -> None:
        assert TestClient(app).get(HEALTH).status_code == 200
        assert TestClient(app).get(f"{API_PREFIX}{HEALTH}").status_code == 404
