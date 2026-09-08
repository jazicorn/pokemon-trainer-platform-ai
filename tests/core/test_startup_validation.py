"""Tests for startup environment variable validation."""

import pytest


class TestValidateEnvironment:
    """Tests for validate_environment() in startup.py."""

    def test_valid_anthropic_key_passes(self, monkeypatch):
        """No exception when ANTHROPIC_API_KEY is present and model is claude-sonnet."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.setenv("POKEMON_MODEL", "claude-sonnet")

        # Re-import config with the patched env so default_model is correct
        import importlib

        import config as cfg_module

        importlib.reload(cfg_module)

        from startup import validate_environment

        # Should not raise
        validate_environment()

    def test_missing_anthropic_key_raises(self, monkeypatch):
        """EnvironmentError raised when ANTHROPIC_API_KEY is absent for Anthropic model."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("POKEMON_MODEL", "claude-sonnet")

        import importlib

        import config as cfg_module

        importlib.reload(cfg_module)

        from startup import validate_environment

        with pytest.raises(EnvironmentError) as exc_info:
            validate_environment()

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_missing_openai_key_raises(self, monkeypatch):
        """EnvironmentError raised when OPENAI_API_KEY is absent for OpenAI model."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("POKEMON_MODEL", "gpt-4o")

        import importlib

        import config as cfg_module

        importlib.reload(cfg_module)

        from startup import validate_environment

        with pytest.raises(EnvironmentError) as exc_info:
            validate_environment()

        assert "OPENAI_API_KEY" in str(exc_info.value)

    def test_ollama_requires_no_key(self, monkeypatch):
        """No exception when using Ollama — it runs locally and needs no API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("POKEMON_MODEL", "llama")

        import importlib

        import config as cfg_module

        importlib.reload(cfg_module)

        from startup import validate_environment

        # Should not raise
        validate_environment()

    def test_error_message_is_descriptive(self, monkeypatch):
        """Error message names the missing variable and shows how to fix it."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("POKEMON_MODEL", "claude-haiku")

        import importlib

        import config as cfg_module

        importlib.reload(cfg_module)

        from startup import validate_environment

        with pytest.raises(EnvironmentError) as exc_info:
            validate_environment()

        message = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in message
        assert "export" in message.lower() or "set" in message.lower()
        # Should mention the provider name
        assert "anthropic" in message.lower()
