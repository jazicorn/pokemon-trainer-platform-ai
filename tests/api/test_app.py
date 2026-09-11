"""Tests for api.app's own startup wiring (ROADMAP.md Phase 14).

Not endpoint behavior — this guards the lifespan() call itself, so the
chromadb=True regression (see Phase 14's plan) can't silently come back.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app


class TestLifespanNeverAutoStartsChromadb:
    """chromadb=True would shell out to `docker run` on lifespan startup —
    fine on a laptop with Docker, fatal on a host with no Docker daemon of
    its own (e.g. a Fly Machine): a failed start calls `raise SystemExit(0)`,
    killing the whole process before it serves a single request. Mirrors the
    same guard Phase 4 already has for Phoenix (phoenix=False).
    """

    def test_lifespan_passes_chromadb_false(self) -> None:
        with patch("api.app.startup") as mock_startup, TestClient(app):
            pass  # __enter__/__exit__ drive the lifespan context manager

        mock_startup.assert_called_once_with(phoenix=False, chromadb=False, telemetry=False, database=True)
