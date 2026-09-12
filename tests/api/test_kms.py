"""Tests for Vault-backed envelope encryption — api.kms (ROADMAP_PLATFORM.md Phase 17).

Patches api.kms._client() directly rather than faking the `hvac` module in
sys.modules — tests/api/conftest.py's autouse fixture already fakes hvac
for every test in this package (so api.tenants.create_tenant() works
without every test needing its own Vault setup); patching at the same
level here would just be two competing sys.modules patches for no benefit.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

import api.kms as kms_module
import config as config_module
from api.kms import VaultNotConfiguredError, unwrap_dek, wrap_new_dek


@pytest.fixture(autouse=True)
def _clear_unwrap_cache() -> None:  # pyright: ignore[reportUnusedFunction]  # autouse fixture, never referenced by name
    """unwrap_dek is lru_cache'd by wrapped_dek string — clear between tests
    so one test's fake Vault response doesn't leak into another's.
    """
    unwrap_dek.cache_clear()


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(kms_module, "_client", lambda: client)
    return client


class TestWrapNewDek:
    def test_returns_plaintext_and_wrapped_dek(self, fake_client: MagicMock) -> None:
        raw_dek = b"0" * 32
        fake_client.secrets.transit.generate_data_key.return_value = {
            "data": {
                "plaintext": base64.b64encode(raw_dek).decode(),
                "ciphertext": "vault:v1:fake-wrapped-dek",
            }
        }

        plaintext_dek, wrapped_dek = wrap_new_dek()

        assert plaintext_dek == raw_dek
        assert wrapped_dek == "vault:v1:fake-wrapped-dek"

    def test_calls_generate_data_key_with_configured_key_name(self, fake_client: MagicMock) -> None:
        fake_client.secrets.transit.generate_data_key.return_value = {
            "data": {"plaintext": base64.b64encode(b"1" * 32).decode(), "ciphertext": "vault:v1:x"}
        }

        wrap_new_dek()

        fake_client.secrets.transit.generate_data_key.assert_called_once_with(
            name=config_module.config.vault_transit_key_name, key_type="plaintext"
        )

    def test_not_configured_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_module.config, "vault_addr", None)
        monkeypatch.setattr(config_module.config, "vault_token", None)

        with pytest.raises(VaultNotConfiguredError, match="VAULT_ADDR"):
            wrap_new_dek()


class TestUnwrapDek:
    def test_returns_the_plaintext_dek(self, fake_client: MagicMock) -> None:
        raw_dek = b"2" * 32
        fake_client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(raw_dek).decode()}
        }

        result = unwrap_dek("vault:v1:some-wrapped-dek")

        assert result == raw_dek

    def test_calls_decrypt_data_with_the_wrapped_dek_and_key_name(self, fake_client: MagicMock) -> None:
        fake_client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(b"3" * 32).decode()}
        }

        unwrap_dek("vault:v1:abc")

        fake_client.secrets.transit.decrypt_data.assert_called_once_with(
            name=config_module.config.vault_transit_key_name, ciphertext="vault:v1:abc"
        )

    def test_result_is_cached_by_wrapped_dek(self, fake_client: MagicMock) -> None:
        fake_client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(b"4" * 32).decode()}
        }

        unwrap_dek("vault:v1:same-key")
        unwrap_dek("vault:v1:same-key")

        fake_client.secrets.transit.decrypt_data.assert_called_once()

    def test_not_configured_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_module.config, "vault_addr", None)
        monkeypatch.setattr(config_module.config, "vault_token", None)

        with pytest.raises(VaultNotConfiguredError, match="VAULT_ADDR"):
            unwrap_dek("vault:v1:whatever-not-cached")
