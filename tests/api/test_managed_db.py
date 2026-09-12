"""Tests for Aiven-backed managed Postgres provisioning — api.managed_db
(ROADMAP_PLATFORM.md Phase 17).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import config as config_module
from api.managed_db import ManagedDBNotConfiguredError, provision_managed_database


@pytest.fixture
def admin_url_configured(monkeypatch: pytest.MonkeyPatch) -> str:
    url = "postgresql://avnadmin:adminpass@my-service.aivencloud.com:12345/defaultdb?sslmode=require"
    monkeypatch.setattr(config_module.config, "aiven_admin_db_url", url)
    return url


class _FakeIdentifier:
    """Mimics psycopg.sql.Identifier just enough for these tests: str()
    quotes it the same way, without needing the real (optional) dependency
    installed to run this test file at all.
    """

    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return f'"{self.value}"'


class _FakeLiteral:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return f"'{self.value}'"


class _FakeComposed:
    def __init__(self, text: str) -> None:
        self._text = text

    def as_string(self, conn: object) -> str:
        return self._text


class _FakeSQLTemplate:
    def __init__(self, template: str) -> None:
        self._template = template

    def format(self, *args: object) -> _FakeComposed:
        return _FakeComposed(self._template.format(*(str(a) for a in args)))


class _FakeSQLModule:
    """psycopg.sql.SQL's real placeholder syntax is the same as str.format's
    ({}), so this fake's format() can just delegate to it.
    """

    Identifier = _FakeIdentifier
    Literal = _FakeLiteral

    @staticmethod
    def SQL(template: str) -> _FakeSQLTemplate:
        return _FakeSQLTemplate(template)


@pytest.fixture
def fake_psycopg(monkeypatch: pytest.MonkeyPatch, admin_url_configured: str) -> MagicMock:
    """Inject a fake `psycopg` module — same pattern as
    tests/api/test_registration.py — so no real Postgres/Aiven, and no real
    `psycopg` package at all, is needed to run this file.
    """
    fake_module = MagicMock()
    mock_conn = MagicMock()
    fake_module.connect.return_value.__enter__.return_value = mock_conn
    fake_module.sql = _FakeSQLModule
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)
    return mock_conn


def _executed_sql(mock_conn: MagicMock) -> list[str]:
    """Normalize every conn.execute() call's argument to a plain string —
    some are raw strings (SCHEMA_STATEMENTS), some are psycopg.sql.Composed
    objects (the dynamic identifier-quoted statements).
    """
    statements: list[str] = []
    for call in mock_conn.execute.call_args_list:
        arg = call.args[0]
        statements.append(arg if isinstance(arg, str) else arg.as_string(None))
    return statements


class TestProvisionManagedDatabase:
    def test_rejects_a_non_hex_tenant_id(self, admin_url_configured: str) -> None:
        with pytest.raises(ValueError, match="hex-only"):
            provision_managed_database("not-hex!")

    def test_not_configured_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_module.config, "aiven_admin_db_url", None)

        with pytest.raises(ManagedDBNotConfiguredError, match="AIVEN_ADMIN_DB_URL"):
            provision_managed_database("deadbeef00000000")

    def test_creates_database_and_role_named_after_the_tenant(self, fake_psycopg: MagicMock) -> None:
        provision_managed_database("deadbeef00000000")

        executed = _executed_sql(fake_psycopg)
        assert any("CREATE DATABASE" in stmt and "tenant_deadbeef00000000" in stmt for stmt in executed)
        assert any("CREATE ROLE" in stmt and "tenant_deadbeef00000000" in stmt for stmt in executed)

    def test_runs_the_full_schema_contract(self, fake_psycopg: MagicMock) -> None:
        provision_managed_database("deadbeef00000000")

        executed = _executed_sql(fake_psycopg)
        for table in ("trades", "user_pokemon", "user_preferences", "user_trade_history", "trade_offers"):
            assert any(f"CREATE TABLE {table} " in s for s in executed), table

    def test_grants_are_issued_for_the_tenant_role(self, fake_psycopg: MagicMock) -> None:
        provision_managed_database("deadbeef00000000")

        executed = _executed_sql(fake_psycopg)
        assert any("GRANT SELECT, INSERT, UPDATE ON trade_offers" in s for s in executed)

    def test_returns_a_connection_string_for_the_tenant_role_not_the_admin(self, fake_psycopg: MagicMock) -> None:
        connection_string = provision_managed_database("deadbeef00000000")

        assert connection_string.startswith("postgresql://tenant_deadbeef00000000:")
        assert "adminpass" not in connection_string
        assert "avnadmin" not in connection_string
        assert "/tenant_deadbeef00000000" in connection_string
        assert "my-service.aivencloud.com:12345" in connection_string
