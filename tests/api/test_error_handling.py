"""Tests for _handle_agent_error — api.app's Sentry-capture + clean-500
conversion for agent-call failures (ROADMAP.md Phase 6).
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException

from api.app import _handle_agent_error  # pyright: ignore[reportPrivateUsage] — deliberately testing it directly


class TestHandleAgentError:
    def test_reports_to_sentry(self) -> None:
        error = RuntimeError("agent call failed")
        with patch("api.app.sentry_sdk.capture_exception") as mock_capture:
            _handle_agent_error(error)

        mock_capture.assert_called_once_with(error)

    def test_returns_a_clean_500(self) -> None:
        error = RuntimeError("agent call failed")
        with patch("api.app.sentry_sdk.capture_exception"):
            result = _handle_agent_error(error)

        assert isinstance(result, HTTPException)
        assert result.status_code == 500
        assert result.detail == "agent call failed"
