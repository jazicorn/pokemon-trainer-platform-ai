"""Tests for the security-headers middleware (ROADMAP.md Phase 14 checklist)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app
from api.paths import HEALTH, OFFERS


class TestSecurityHeaders:
    def test_hsts_header_present(self) -> None:
        response = TestClient(app).get(HEALTH)
        assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"

    def test_nosniff_header_present(self) -> None:
        response = TestClient(app).get(HEALTH)
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_frame_options_header_present(self) -> None:
        response = TestClient(app).get(HEALTH)
        assert response.headers["x-frame-options"] == "DENY"

    def test_headers_present_even_on_error_responses(self) -> None:
        """Auth failures still go through the middleware — confirms these
        headers aren't accidentally scoped to only the success path.
        """
        response = TestClient(app).get(OFFERS)  # no X-API-Key -> 401

        assert response.status_code == 401
        assert "strict-transport-security" in response.headers
