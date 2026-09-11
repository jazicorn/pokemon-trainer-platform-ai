"""Tests for the request-logging middleware (ROADMAP.md Phase 4)."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.paths import HEALTH, OFFERS


class TestLoggingMiddleware:
    def test_logs_method_path_status_and_duration(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="api.app"):
            response = TestClient(app).get(HEALTH)

        assert response.status_code == 200
        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert message.startswith(f"GET {HEALTH} 200 ")
        assert message.endswith("ms")

    def test_logs_the_real_status_code_on_auth_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="api.app"):
            response = TestClient(app).get(OFFERS)  # no X-API-Key -> 401

        assert response.status_code == 401
        message = caplog.records[-1].getMessage()
        assert message.startswith(f"GET {OFFERS} 401 ")
