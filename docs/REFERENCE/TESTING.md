# Testing Guide

This guide covers how to run and work with tests in the Pokemon Trainer Platform - AI.

## Quick Start

```bash
# Run all tests (excludes ChromaDB-dependent tests)
uv run pytest tests/ -v --tb=short -m "not requires_chromadb"

# Skip ChromaDB/Docker tests explicitly
uv run pytest tests/ -v --tb=short -m "not requires_chromadb"

# Run specific test file
uv run pytest tests/data/test_data.py -v

# Run specific test class
uv run pytest tests/rag/test_rag.py::TestEmbedding -v
```

## pytest.ini Defaults

`pytest.ini` at the project root configures two defaults that apply to every
`uv run pytest` invocation:

| Setting | Value | Effect |
| ------- | ----- | ------ |
| `asyncio_mode = strict` | strict | async tests must be explicitly marked with `@pytest.mark.asyncio` or `pytestmark` |
| `markers = requires_chromadb` | registered | ChromaDB tests marked and filterable with `-m "not requires_chromadb"` |

Override output capturing when you want stdout suppressed (e.g. CI):

```bash
uv run pytest tests/ -v --tb=short --capture=fd -m "not requires_chromadb"
```

## Test Structure

```text
tests/
├── conftest.py                     # Shared fixtures, path setup, API key stubs
├── agents/
│   ├── test_legitimacy_guard.py    # Legitimacy guard agent integration tests
│   ├── test_multi_agent.py         # Multi-agent orchestration tests
│   ├── test_pokedex_agent.py       # Pokedex expert agent integration tests
│   ├── test_trade_advisor.py       # Trade advisor agent integration tests
│   ├── test_trade_analytics.py     # Market analyst tests
│   └── test_trade_offers.py        # TradeOffersManager CRUD + offer agent functions
├── cli/
│   └── test_cli.py                 # CLI command parsing tests
├── core/
│   ├── test_config.py              # Config loading and env var override tests
│   └── test_startup_validation.py  # Env var validation tests
├── data/
│   └── test_data.py                # Mock data generation tests
├── evals/
│   ├── test_evals.py               # Evaluation scoring unit tests
│   └── test_evals_execution.py     # End-to-end eval pipeline tests
├── guardrails/
│   └── test_guardrails.py          # PII detection/filtering tests
├── mcp/
│   └── test_mcp_server.py          # MCP tool definition tests
├── memory/
│   ├── test_memory.py              # SQLite memory system unit tests
│   └── test_memory_persistence.py  # Cross-instance SQLite persistence tests
└── rag/
    └── test_rag.py                 # RAG and vector store tests (requires_chromadb)
```

## Environment Variables

### API Key Handling

`conftest.py` automatically stubs missing or empty API keys before any agent
module is imported, so no manual `export` is needed for local or CI runs:

```python
# conftest.py — runs before test collection
if not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "test-fake-key"
```

The `if not get()` guard handles both **absent** keys and **empty-string**
values (e.g. `ANTHROPIC_API_KEY=` exported as a placeholder by 1Password or a
`.env` file). A real key already in the environment is always respected.

To run tests against the **live LLM** (e.g. smoke testing), inject the real
key first:

```bash
# With 1Password CLI
op run -- uv run pytest tests/ -v --tb=short

# Or export directly
export ANTHROPIC_API_KEY=sk-ant-...
uv run pytest tests/ -v --tb=short
```

Other providers follow the same pattern:

| Provider (`POKEMON_MODEL`)       | Required env var      |
| -------------------------------- | --------------------- |
| `claude-sonnet` / `claude-haiku` | `ANTHROPIC_API_KEY`   |
| `gpt-4o` / `gpt-4o-mini`         | `OPENAI_API_KEY`      |
| `gemini-flash` / `gemini-pro`    | `GOOGLE_API_KEY`      |
| `llama` (Ollama)                 | *(none)*              |

`validate_environment()` in `startup.py` raises a clear `EnvironmentError` at
app startup if the required key is missing, empty, or unresolved.
It detects the 1Password CLI (`op`) and tailors the message accordingly:

- **`op://` URI value** → key was never resolved; suggests
  `op run --env-file .env.op -- uv run python app.py`
- **Empty string + `op` present** → `op read` ran unauthenticated; suggests
  `eval $(op signin) && source ~/.zshrc`
- **Absent + `op` present** → shows the `op read` snippet to add to `~/.zshrc`
- **Absent, no `op`** → shows the plain `export KEY=<value>` instruction

This only affects the running app — tests are unaffected because `conftest.py`
stubs the key before any module is imported.

## Test Categories

### Unit Tests (No External Dependencies)

These tests run without Docker or external services:

```bash
# Data generation
uv run pytest tests/data/test_data.py -v

# CLI parsing
uv run pytest tests/cli/test_cli.py -v

# PII guardrails
uv run pytest tests/guardrails/test_guardrails.py -v

# Evaluation scoring (unit)
uv run pytest tests/evals/test_evals.py -v

# Evaluation pipeline end-to-end (mocked LLM)
uv run pytest tests/evals/test_evals_execution.py -v

# MCP tool definitions
uv run pytest tests/mcp/test_mcp_server.py -v

# SQLite memory persistence across instances
uv run pytest tests/memory/test_memory_persistence.py -v

# Startup env var validation
uv run pytest tests/core/test_startup_validation.py -v

# Legitimacy guard agent
uv run pytest tests/agents/test_legitimacy_guard.py -v

# Multi-agent orchestration
uv run pytest tests/agents/test_multi_agent.py -v

# Pokedex agent integration (async, mocked LLM)
uv run pytest tests/agents/test_pokedex_agent.py -v

# Trade advisor integration (async, mocked LLM)
uv run pytest tests/agents/test_trade_advisor.py -v

# Trade offers CRUD and agent functions (async, mocked LLM)
uv run pytest tests/agents/test_trade_offers.py -v
```

### Integration Tests (Require ChromaDB)

These tests are marked `@pytest.mark.requires_chromadb` and are excluded from
the default `make test` run. Start ChromaDB first, then use:

```bash
# Vector store tests via make target (passes -s for interactive prompt)
make test-rag

# Or run directly
uv run pytest tests/rag/test_rag.py::TestPokemonVectorStore -v -s
```

## Interactive Test Fixtures

### ChromaDB Fixture

The `ensure_chromadb` fixture automatically handles Docker and ChromaDB setup.
Pass `-s` so the interactive prompt appears when ChromaDB is not running:

```text
╭─────────────────────────────────────────╮
│     🧪 ChromaDB Test Environment        │
╰─────────────────────────────────────────╯

ℹ️  ChromaDB is not running
ℹ️  ⚠️  Docker is not running

╭─────────────────────────────────────────╮
│       🐳 Docker Startup Options         │
├─────────────────────────────────────────┤
│  [1] 🔧 Start Docker service (systemctl)│
│  [2] 🖥️  Start Docker Desktop            │
│  [3] ⏭️  Skip this test                  │
╰─────────────────────────────────────────╯

Enter choice [1/2/3]:
```

### Platform-Specific Behavior

| Platform | Default Action               |
| -------- | ---------------------------- |
| macOS    | Opens Docker Desktop         |
| Windows  | Starts Docker Desktop        |
| Linux    | Shows menu (systemctl or DD) |

## Docker Test Variables

### TEST_DOCKER_PLATFORM

Force a specific platform for testing cross-platform behavior:

```bash
# Test Linux flow on macOS
TEST_DOCKER_PLATFORM=linux \
  uv run pytest tests/rag/test_rag.py::TestPokemonVectorStore -v -s

# Test Windows flow
TEST_DOCKER_PLATFORM=win32 \
  uv run pytest tests/rag/test_rag.py::TestPokemonVectorStore -v -s
```

### TEST_DOCKER_DRY_RUN

Print commands without executing them (useful for verifying logic):

```bash
# Dry run - shows what would be executed
TEST_DOCKER_DRY_RUN=1 \
  uv run pytest tests/rag/test_rag.py::TestPokemonVectorStore -v -s

# Combine with platform override
TEST_DOCKER_PLATFORM=linux TEST_DOCKER_DRY_RUN=1 \
  uv run pytest tests/rag/test_rag.py::TestPokemonVectorStore -v -s
```

## Running Tests in CI

No API keys or Docker required for the unit test suite:

```bash
# All unit tests — API keys are stubbed automatically by conftest.py
uv run pytest tests/ -v --tb=short --capture=fd -m "not requires_chromadb"
```

If Docker is available in CI, drop the `-m` filter to run ChromaDB tests too.

## Test Coverage

Generate coverage report:

```bash
# Install coverage
uv add --dev pytest-cov

# Run with coverage
uv run pytest tests/ --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

## Async Agent Integration Tests

Agent integration tests use `FunctionModel` from `pydantic_ai.models.function`
to deterministically control tool dispatch without hitting a live LLM. The pattern
mirrors `tests/agents/test_legitimacy_guard.py`:

```python
import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import (
    ModelResponse, ToolCallPart, ToolReturnPart, ModelRequest, TextPart
)

class TestMyAgentIntegration:
    pytestmark = pytest.mark.asyncio

    async def test_my_tool_is_called(self):
        deps = MyDependencies(...)  # or .model_construct(...) to skip validation

        def mock_model(messages, info):
            # Return a TextPart once the tool result is in history to end the loop
            if any(
                isinstance(part, ToolReturnPart)
                for msg in messages if isinstance(msg, ModelRequest)
                for part in msg.parts
            ):
                return ModelResponse(parts=[TextPart(content="Done.")])
            # Otherwise drive the agent to call the tool
            return ModelResponse(parts=[
                ToolCallPart(tool_name="my_tool", args={"param": "value"})
            ])

        with my_agent.override(model=FunctionModel(mock_model)):
            result = await my_agent.run("prompt", deps=deps)

        # Inspect tool return values via the message history
        tool_outputs = [
            str(part.content)
            for msg in result.all_messages() if isinstance(msg, ModelRequest)
            for part in msg.parts if isinstance(part, ToolReturnPart)
        ]
        assert any("expected" in out for out in tool_outputs)
```

**Key notes:**

- Always end the mock with `TextPart(content="...")` — an empty `parts=[]`
  causes `UnexpectedModelBehavior`
- Use `Model.model_construct(...)` instead of `Model(...)` to bypass Pydantic
  validation when passing `MagicMock` objects as typed deps
- When a sub-agent is called inside a tool, patch both the sub-agent's `run`
  method *and* the `Dependencies` class in the parent module's namespace
  (see `tests/agents/test_trade_advisor.py` for the `sys.modules` pattern)

## Memory Persistence Tests

Tests that verify SQLite data survives across new instances use `tmp_path` +
`monkeypatch` to redirect the database to a fresh temp file:

```python
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory.database.get_db_path", lambda: db_file)
    init_database()
    return db_file

def test_data_persists(self, isolated_db):
    instance_a = ConversationMemory("user_test")
    instance_a.add_message("user", "Hello")

    instance_b = ConversationMemory("user_test")  # brand new instance
    assert len(instance_b.get_history()) == 1
```

This guarantees tests are isolated and never pollute the real `data/memory.db`.

## Eval Pipeline Tests

`tests/evals/test_evals_execution.py` tests the eval loop end-to-end by
patching `evaluate_trade` so no live LLM call is made:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_eval_pipeline(self):
    with patch(
        "evals.eval_trade_advisor.evaluate_trade",
        new=AsyncMock(return_value="I recommend you accept this trade."),
    ):
        results = await run_trade_eval()

    assert len(results) == len(TRADE_CASES)
    assert all(isinstance(r, TradeEvalResult) for r in results)
```

## Writing New Tests

### Test File Template

```python
"""Tests for [module name]."""

import pytest

from module_name import function_to_test


class TestFunctionName:
    """Tests for function_name."""

    def test_basic_case(self):
        result = function_to_test("input")
        assert result == "expected"

    def test_edge_case(self):
        result = function_to_test("")
        assert result is None

    @pytest.fixture
    def sample_data(self):
        """Provide sample test data."""
        return {"key": "value"}

    def test_with_fixture(self, sample_data):
        result = function_to_test(sample_data)
        assert "key" in result
```

### Using the ChromaDB Fixture

```python
@pytest.mark.requires_chromadb
class TestMyVectorFeature:
    """Tests requiring ChromaDB."""

    @pytest.fixture
    def ensure_chromadb(self):
        """Copy the fixture from tests/rag/test_rag.py."""
        # ... fixture code ...

    def test_my_feature(self, ensure_chromadb):
        # Test runs only if ChromaDB is available
        store = PokemonVectorStore()
        # ...
```

## Debugging Tests

### Run Single Test with Output

```bash
uv run pytest tests/cli/test_cli.py::TestParseCommand::test_parse_quit_commands -v
```

### Drop into Debugger on Failure

```bash
uv run pytest tests/ --pdb
```

### Show Local Variables on Failure

```bash
uv run pytest tests/ -l
```

### Stop on First Failure

```bash
uv run pytest tests/ -x
```

## Performance Testing

The CLI tests include performance benchmarks:

```bash
# Run performance tests
uv run pytest tests/cli/test_cli.py::TestParseCommandPerformance -v
```

Example performance test:

```python
def test_parse_command_is_fast(self):
    """Verify parsing is O(1) for simple commands."""
    import time

    commands = ["quit", "help", "suggest", "prefs", "history"]
    iterations = 10000

    start = time.perf_counter()
    for _ in range(iterations):
        for cmd in commands:
            parse_command(cmd)
    elapsed = time.perf_counter() - start

    # Should complete 50k parses in under 100ms
    assert elapsed < 0.1, f"Parsing too slow: {elapsed:.3f}s"
```

## Common Issues

### ChromaDB Connection Refused

```text
httpx.ConnectError: [Errno 61] Connection refused
```

**Solution:** Run the ChromaDB integration tests via the make target, which
handles startup automatically:

```bash
make test-rag
```

### OSError: reading from stdin while output is captured

```text
OSError: pytest: reading from stdin while output is captured!
```

**Solution:** Pass `-s` explicitly when running ChromaDB tests:

```bash
uv run pytest tests/rag/test_rag.py -v -s
```

### API Key Empty at App Startup (1Password)

```text
OSError: Environment variable ANTHROPIC_API_KEY is set but empty.
The configured model provider 'anthropic' requires this key.
Your 1Password CLI integration may not be authenticated.
```

**Solution:** Your shell's `op read` call ran but 1Password was not signed in,
so the variable was exported as an empty string. Sign in and reload:

```bash
eval $(op signin) && source ~/.zshrc
uv run python app.py
```

This only affects the running app — tests stub the key automatically.

### API Key Errors During Collection

```text
pydantic_ai.exceptions.UserError: Set the `ANTHROPIC_API_KEY` environment variable
```

**Solution:** `conftest.py` stubs the key automatically, but only when pytest
finds it. Run from the project root. If using a secret manager (e.g.
1Password) that exports the variable as an empty string, the stub still handles
it — no manual export needed.

### Import Errors

```text
ModuleNotFoundError: No module named 'agents'
```

**Solution:** Ensure conftest.py adds src to path:

```python
# conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

### Docker Timeout

```text
subprocess.TimeoutExpired: Command '['docker', 'info']' timed out
```

**Solution:** Docker Desktop may still be starting. Wait and retry, or
increase timeout in the fixture.

## Test Checklist

Before committing:

- [ ] All tests pass: `uv run pytest tests/ -v --tb=short -m "not requires_chromadb"`
- [ ] No type errors: `uv run pyright src/`
- [ ] Code formatted: `uv run ruff format .`
- [ ] Linting passes: `uv run ruff check .`
