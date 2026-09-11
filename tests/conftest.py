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
def _isolate_ollama_base_url(  # pyright: ignore[reportUnusedFunction]  # autouse fixture, never referenced by name
    monkeypatch: pytest.MonkeyPatch,
):
    """config.py sets OLLAMA_BASE_URL as an import-time side effect via
    os.environ.setdefault (pydantic-ai's OllamaProvider reads that name, not
    this project's own OLLAMA_URL). setdefault only acts once per process,
    and several test files use importlib.reload(cfg_module) to test other
    env var overrides — without clearing it before each test, one test's
    reload could leak a stale OLLAMA_BASE_URL into every test that runs
    after it, in any file, for the rest of the session.
    """
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _isolate_chroma_api_key(  # pyright: ignore[reportUnusedFunction]  # autouse fixture, never referenced by name
    monkeypatch: pytest.MonkeyPatch,
):
    """Force PokemonVectorStore/is_vector_store_running into local mode by default.

    Unlike ANTHROPIC_API_KEY/OPENAI_API_KEY/GOOGLE_API_KEY above, a real CHROMA_API_KEY present
    in the environment isn't harmless to leave as-is: nothing intercepts it the way
    FunctionModel/AsyncMock intercept LLM calls — api/app.py's /health (hit by several existing
    tests, none of which assert on its chromadb field) would make a real, live Chroma Cloud
    heartbeat call on every developer machine that happens to have this set locally (as this one
    does — see ROADMAP.md Phase 9), silently, on every `make test` run.

    Patches EVERY module below individually, not just config.config — verified directly that
    this matters: `from config import config` binds a name to whatever object config.config
    pointed to at THAT module's own import time. tests/core/test_config.py's own
    importlib.reload(cfg_module) calls (see _isolate_ollama_base_url's docstring above)
    replace config.config with a brand-new object partway through the session, but modules
    already imported before that reload — utils.py, rag/vector_store.py — keep their own,
    now-stale reference to the ORIGINAL object. Patching only config.config's attributes
    silently no-ops for anything reading it through one of those stale references: this is
    exactly how a real CHROMA_API_KEY leaked into a live network call and an assertion-failure
    message during this fixture's own development — patching config.config alone looked
    correct and passed in isolation, but not when run after test_config.py in the same session.
    Tests that specifically want cloud mode (tests/rag/test_vector_store_cloud.py) set this
    back themselves, the same way, via their own autouse fixture, which runs after this one.
    """
    import config as config_module
    import rag.vector_store as vector_store_module
    import utils as utils_module

    for module in (config_module, vector_store_module, utils_module):
        monkeypatch.setattr(module.config, "chroma_api_key", None)
