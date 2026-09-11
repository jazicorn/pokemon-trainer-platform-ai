"""Tests for platform_db_url validation — api.registration (ROADMAP.md Phase 15)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import api.registration as registration_module
from api.registration import REQUIRED_TABLES, PlatformDBValidationError, validate_platform_db_url


@pytest.fixture
def fake_psycopg(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a fake `psycopg` module so validate_platform_db_url's lazy
    `import psycopg` succeeds regardless of whether the real optional
    dependency is installed (CI doesn't sync the `platform-db` group).
    """
    monkeypatch.setattr(registration_module, "_PSYCOPG_AVAILABLE", True)
    fake_module = MagicMock()
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)
    return fake_module


def _mock_cursor(fake_psycopg: MagicMock) -> MagicMock:
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    fake_psycopg.connect.return_value.__enter__.return_value = mock_conn
    return mock_cursor


class TestValidatePlatformDbUrl:
    def test_all_required_tables_present_raises_nothing(self, fake_psycopg: MagicMock) -> None:
        cursor = _mock_cursor(fake_psycopg)
        cursor.fetchall.return_value = [(t,) for t in REQUIRED_TABLES]

        validate_platform_db_url("postgresql://u:p@h/db")  # no exception

    def test_extra_unrelated_tables_are_fine(self, fake_psycopg: MagicMock) -> None:
        cursor = _mock_cursor(fake_psycopg)
        cursor.fetchall.return_value = [(t,) for t in {*REQUIRED_TABLES, "some_other_table"}]

        validate_platform_db_url("postgresql://u:p@h/db")  # no exception

    def test_missing_table_is_named_in_the_error(self, fake_psycopg: MagicMock) -> None:
        cursor = _mock_cursor(fake_psycopg)
        cursor.fetchall.return_value = [(t,) for t in REQUIRED_TABLES if t != "trade_offers"]

        with pytest.raises(PlatformDBValidationError, match="trade_offers"):
            validate_platform_db_url("postgresql://u:p@h/db")

    def test_multiple_missing_tables_are_all_named(self, fake_psycopg: MagicMock) -> None:
        cursor = _mock_cursor(fake_psycopg)
        cursor.fetchall.return_value = [("trades",)]

        with pytest.raises(PlatformDBValidationError) as exc_info:
            validate_platform_db_url("postgresql://u:p@h/db")

        for table in REQUIRED_TABLES - {"trades"}:
            assert table in str(exc_info.value)

    def test_connection_failure_is_reported_not_raised_raw(self, fake_psycopg: MagicMock) -> None:
        fake_psycopg.connect.side_effect = Exception("connection refused")

        with pytest.raises(PlatformDBValidationError, match="Could not connect"):
            validate_platform_db_url("postgresql://u:p@h/db")


class TestPsycopgNotInstalled:
    def test_raises_runtime_error_naming_the_dependency_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(registration_module, "_PSYCOPG_AVAILABLE", False)

        with pytest.raises(RuntimeError, match="platform-db"):
            validate_platform_db_url("postgresql://u:p@h/db")
