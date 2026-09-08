"""Tests for src/config.py — Config dataclass, env var overrides, and validation."""

import importlib
import os

import pytest

import config as cfg_module
from config import MODELS, Config, ModelConfig, ModelProvider, _load_dotenv_files

# _isolate_ollama_base_url in tests/conftest.py (autouse, applies here too)
# prevents this file's importlib.reload(cfg_module) calls from leaking a
# stale OLLAMA_BASE_URL into other tests.


class TestModelConfig:
    """Tests for the ModelConfig dataclass."""

    def test_anthropic_model_id_format(self):
        mc = ModelConfig(ModelProvider.ANTHROPIC, "claude-sonnet-4-6")
        assert mc.model_id == "anthropic:claude-sonnet-4-6"

    def test_openai_model_id_format(self):
        mc = ModelConfig(ModelProvider.OPENAI, "gpt-4o")
        assert mc.model_id == "openai:gpt-4o"

    def test_gemini_model_id_format(self):
        mc = ModelConfig(ModelProvider.GEMINI, "gemini-1.5-flash")
        assert mc.model_id == "gemini:gemini-1.5-flash"

    def test_ollama_model_id_uses_prefix(self):
        mc = ModelConfig(ModelProvider.OLLAMA, "llama3.2")
        assert mc.model_id == "ollama:llama3.2"


class TestModelsDict:
    """Tests for the MODELS registry."""

    def test_all_expected_keys_present(self):
        expected = {
            "claude-sonnet",
            "claude-haiku",
            "gpt-4o",
            "gpt-4o-mini",
            "gemini-flash",
            "gemini-pro",
            "llama",
            "llama-cloud",
        }
        assert expected == set(MODELS.keys())

    def test_claude_sonnet_is_anthropic(self):
        assert MODELS["claude-sonnet"].provider == ModelProvider.ANTHROPIC

    def test_llama_is_ollama(self):
        assert MODELS["llama"].provider == ModelProvider.OLLAMA


class TestConfigDefaults:
    """Tests for default field values on a fresh Config instance."""

    def setup_method(self):
        self.cfg = Config()

    def test_default_model_is_claude_sonnet(self):
        assert self.cfg.default_model == "claude-sonnet"

    def test_default_chromadb_url(self):
        assert self.cfg.chromadb_url == "http://localhost:8000"

    def test_default_phoenix_url(self):
        assert self.cfg.phoenix_url == "http://127.0.0.1:6006"

    def test_default_ollama_url(self):
        assert self.cfg.ollama_url == "http://localhost:11434"

    def test_default_ollama_embedding_model(self):
        assert self.cfg.ollama_embedding_model == "nomic-embed-text"

    def test_default_project_name(self):
        assert self.cfg.project_name == "pokemon-trade-advisor"

    def test_default_use_ollama_embeddings_is_false(self):
        assert self.cfg.use_ollama_embeddings is False


class TestDotenvLoading:
    """_load_dotenv_files() — layered .env.local / .env loading with real
    environment variables always taking precedence over both files.

    Uses tmp_path rather than this project's real .env/.env.local — those
    are real, potentially developer-populated files that tests must never
    read from or write to.
    """

    VAR = "POKEMON_TEST_DOTENV_VAR"

    def test_env_file_sets_previously_unset_var(self, tmp_path, monkeypatch):
        monkeypatch.delenv(self.VAR, raising=False)
        (tmp_path / ".env").write_text(f"{self.VAR}=from-env\n")
        _load_dotenv_files(tmp_path)
        assert os.environ[self.VAR] == "from-env"

    def test_env_local_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv(self.VAR, raising=False)
        (tmp_path / ".env").write_text(f"{self.VAR}=from-env\n")
        (tmp_path / ".env.local").write_text(f"{self.VAR}=from-env-local\n")
        _load_dotenv_files(tmp_path)
        assert os.environ[self.VAR] == "from-env-local"

    def test_real_env_var_wins_over_both_files(self, monkeypatch, tmp_path):
        monkeypatch.setenv(self.VAR, "from-real-shell")
        (tmp_path / ".env").write_text(f"{self.VAR}=from-env\n")
        (tmp_path / ".env.local").write_text(f"{self.VAR}=from-env-local\n")
        _load_dotenv_files(tmp_path)
        assert os.environ[self.VAR] == "from-real-shell"

    def test_missing_files_do_not_raise(self, tmp_path):
        _load_dotenv_files(tmp_path)  # neither file exists in tmp_path


class TestConfigEnvVars:
    """Tests that every Config field can be set via its env var."""

    def test_pokemon_model_override(self, monkeypatch):
        monkeypatch.setenv("POKEMON_MODEL", "gpt-4o")
        importlib.reload(cfg_module)
        assert cfg_module.config.default_model == "gpt-4o"

    def test_chromadb_url_override(self, monkeypatch):
        monkeypatch.setenv("CHROMADB_URL", "http://myhost:9000")
        importlib.reload(cfg_module)
        assert cfg_module.config.chromadb_url == "http://myhost:9000"

    def test_phoenix_url_override(self, monkeypatch):
        monkeypatch.setenv("PHOENIX_URL", "http://myhost:6006")
        importlib.reload(cfg_module)
        assert cfg_module.config.phoenix_url == "http://myhost:6006"

    def test_ollama_url_override(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://myhost:11434")
        importlib.reload(cfg_module)
        assert cfg_module.config.ollama_url == "http://myhost:11434"

    def test_ollama_embedding_model_override(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
        importlib.reload(cfg_module)
        assert cfg_module.config.ollama_embedding_model == "mxbai-embed-large"

    def test_project_name_override(self, monkeypatch):
        monkeypatch.setenv("PROJECT_NAME", "my-custom-project")
        importlib.reload(cfg_module)
        assert cfg_module.config.project_name == "my-custom-project"

    def test_use_ollama_embeddings_true(self, monkeypatch):
        monkeypatch.setenv("USE_OLLAMA_EMBEDDINGS", "true")
        importlib.reload(cfg_module)
        assert cfg_module.config.use_ollama_embeddings is True

    def test_use_ollama_embeddings_false_by_default(self, monkeypatch):
        monkeypatch.delenv("USE_OLLAMA_EMBEDDINGS", raising=False)
        importlib.reload(cfg_module)
        assert cfg_module.config.use_ollama_embeddings is False

    def teardown_method(self):
        # Reload to restore defaults after each env-var test
        importlib.reload(cfg_module)


class TestConfigValidation:
    """Tests for __post_init__ validation of default_model."""

    def test_valid_model_does_not_raise(self):
        cfg = Config(default_model="claude-sonnet")
        assert cfg.default_model == "claude-sonnet"

    def test_all_known_models_are_valid(self):
        for name in MODELS:
            cfg = Config(default_model=name)
            assert cfg.default_model == name

    def test_invalid_model_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown model"):
            Config(default_model="not-a-real-model")

    def test_error_message_lists_available_models(self):
        with pytest.raises(ValueError) as exc_info:
            Config(default_model="bad-model")
        message = str(exc_info.value)
        assert "claude-sonnet" in message
        assert "llama" in message

    def test_get_model_returns_correct_config(self):
        cfg = Config()
        mc = cfg.get_model("gpt-4o")
        assert mc.provider == ModelProvider.OPENAI
        assert mc.model_name == "gpt-4o"

    def test_get_model_defaults_to_default_model(self):
        cfg = Config(default_model="llama")
        mc = cfg.get_model()
        assert mc.provider == ModelProvider.OLLAMA

    def test_get_model_unknown_raises_value_error(self):
        cfg = Config()
        with pytest.raises(ValueError, match="Unknown model"):
            cfg.get_model("does-not-exist")

    def test_model_id_property(self):
        cfg = Config(default_model="llama")
        assert cfg.model_id == "ollama:llama3.2"


class TestOllamaCloudTransportDetection:
    """llama-cloud resolves to one of two model names depending on OLLAMA_URL —
    the local-daemon-proxy transport uses a "-cloud" suffixed name, direct
    access to ollama.com's API uses the bare name (no local install needed).
    """

    def test_default_ollama_url_uses_local_proxy_suffix(self):
        cfg = Config(default_model="llama-cloud")
        assert cfg.get_model().model_name == "gpt-oss:120b-cloud"

    def test_ollama_com_url_uses_direct_api_name(self):
        cfg = Config(default_model="llama-cloud", ollama_url="https://ollama.com")
        assert cfg.get_model().model_name == "gpt-oss:120b"

    def test_ollama_com_url_model_id(self):
        cfg = Config(default_model="llama-cloud", ollama_url="https://ollama.com")
        assert cfg.model_id == "ollama:gpt-oss:120b"

    def test_local_model_unaffected_by_ollama_url(self):
        """`llama` (no direct_api_model_name) never gets suffix-swapped."""
        cfg = Config(default_model="llama", ollama_url="https://ollama.com")
        assert cfg.get_model().model_name == "llama3.2"


class TestOllamaBaseUrlPropagation:
    """pydantic-ai's OllamaProvider reads OLLAMA_BASE_URL — not this
    project's own OLLAMA_URL. Without propagating it, any "ollama:*"
    model_id raises UserError at Agent construction time, local or cloud.

    OLLAMA_BASE_URL must carry a "/v1" suffix (OllamaProvider hands it
    straight to the OpenAI SDK client, which hits Ollama's OpenAI-compatible
    endpoints, not its native /api/* ones) — but config.ollama_url itself
    must stay bare, since get_ollama_embedding() uses it against Ollama's
    native /api/embeddings path.
    """

    def test_ollama_base_url_gets_v1_suffix(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434")
        importlib.reload(cfg_module)
        assert os.environ["OLLAMA_BASE_URL"] == "http://test-host:11434/v1"

    def test_ollama_url_itself_has_no_v1_suffix(self, monkeypatch):
        """config.ollama_url must stay bare for get_ollama_embedding()."""
        monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434")
        importlib.reload(cfg_module)
        assert cfg_module.config.ollama_url == "http://test-host:11434"

    def test_cloud_direct_url_also_gets_v1_suffix(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "https://ollama.com")
        importlib.reload(cfg_module)
        assert os.environ["OLLAMA_BASE_URL"] == "https://ollama.com/v1"

    def test_trailing_slash_on_ollama_url_does_not_double_up(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434/")
        importlib.reload(cfg_module)
        assert os.environ["OLLAMA_BASE_URL"] == "http://test-host:11434/v1"

    def test_ollama_url_already_ending_in_v1_does_not_double_up(self, monkeypatch):
        """A user copying pydantic-ai's own docs might set OLLAMA_URL with
        /v1 already on it — must not become .../v1/v1."""
        monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434/v1")
        importlib.reload(cfg_module)
        assert os.environ["OLLAMA_BASE_URL"] == "http://test-host:11434/v1"

    def test_explicit_ollama_base_url_is_not_overridden(self, monkeypatch):
        """setdefault() must respect an explicitly-set OLLAMA_BASE_URL."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://explicit-override:1234/v1")
        monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434")
        importlib.reload(cfg_module)
        assert os.environ["OLLAMA_BASE_URL"] == "http://explicit-override:1234/v1"
