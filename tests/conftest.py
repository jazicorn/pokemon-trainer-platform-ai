"""Pytest configuration for Pokemon Trainer Platform - AI tests."""

import os
import sys
from pathlib import Path

import pytest

# Add src to path so tests can import modules
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# ---------------------------------------------------------------------------
# Ensure API keys are set before agent modules are imported.
#
# Pydantic AI validates the provider API key at Agent instantiation time
# (module load), not at call time. If no key is present, collection fails
# with UserError before any test runs.
#
# We set a dummy value when the key is absent OR empty string (e.g. exported
# as ANTHROPIC_API_KEY= in a .env / shell config), so:
#   - CI / local runs without a key work correctly (no live LLM calls are
#     made in the test suite — FunctionModel / AsyncMock intercept them all)
#   - A real key in the environment is always respected and used as-is
# ---------------------------------------------------------------------------
if not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "test-fake-key"
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "test-fake-key"
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = "test-fake-key"


@pytest.fixture(autouse=True)
def _isolate_ollama_base_url(monkeypatch):
    """config.py sets OLLAMA_BASE_URL as an import-time side effect via
    os.environ.setdefault (pydantic-ai's OllamaProvider reads that name, not
    this project's own OLLAMA_URL). setdefault only acts once per process,
    and several test files use importlib.reload(cfg_module) to test other
    env var overrides — without clearing it before each test, one test's
    reload could leak a stale OLLAMA_BASE_URL into every test that runs
    after it, in any file, for the rest of the session.
    """
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
