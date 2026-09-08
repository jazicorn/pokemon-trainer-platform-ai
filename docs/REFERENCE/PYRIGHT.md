# Linting & Type Checking Setup

This project uses **pyright** (strict mode) for static type analysis and **ruff** for
formatting/linting.

---

## Tools

| Tool | Purpose | Config location |
| ------ | --------- | --------------- |
| `pyright` | Static type checking (strict) | `[tool.pyright]` in root `pyproject.toml` |
| `ruff` | Linting & formatting | `[tool.ruff]` in root `pyproject.toml` |
| Pylance | VS Code in-editor type checking | reads `[tool.pyright]` + `.vscode/settings.json` |

---

## Running the Linter

```bash
# Type check source
uv run pyright src/

# Or run everything (ruff format check, ruff lint, pyright) via make
make lint

# Auto-fix formatting and lint issues where possible
make lint-fix
```

---

## VS Code Setup

Pylance (the VS Code Python extension) must be pointed at the correct interpreter to resolve
imports.

### One-time setup

1. `Cmd+Shift+P` → **"Python: Select Interpreter"**
2. Click **"Enter interpreter path..."**
3. Paste the full path to the project venv:

   ```text
   /path/to/project/.venv/bin/python
   ```

> **Note:** `python.defaultInterpreterPath` in `.vscode/settings.json` only applies the first
> time VS Code opens the workspace. If an interpreter was previously selected, you must set it
> manually via the command palette.

### What's already configured

`pyproject.toml` `[tool.pyright]`:

```toml
[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "strict"
venvPath = "."
venv = ".venv"
extraPaths = ["src"]
reportAny = false
reportExplicitAny = false
reportMissingTypeStubs = false
reportUnknownMemberType = false
reportUnknownVariableType = false
```

`extraPaths = ["src"]` lets both the CLI tool and Pylance resolve project
modules (e.g. `from agents.trade_advisor import ...`) without needing to
install the package.

---

## pyproject.toml Configuration

The full active config (pyright reads `[tool.pyright]`):

```toml
[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "strict"
venvPath = "."
venv = ".venv"
extraPaths = ["src"]
reportAny = false
reportExplicitAny = false
reportMissingTypeStubs = false
reportUnknownMemberType = false
reportUnknownVariableType = false
```

The disabled checks are suppressed because third-party packages (`rich`, `httpx`, `pydantic-ai`)
don't always expose complete type information in pyright strict mode. All first-party code
is fully typed.

---

## Ruff Configuration

The full active config (ruff reads `[tool.ruff]`):

```toml
[tool.ruff]
target-version = "py313"
line-length = 120
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort (import sorting)
    "B",   # flake8-bugbear (likely bugs / design smells)
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
    "UP",  # pyupgrade (modern syntax)
    "PLE", # pylint errors
]
```

This rule set covers the same ground a standalone `pylint` install would (bug-prone
patterns, needless complexity, outdated syntax, import hygiene) at a fraction of the
runtime, since pyright already handles the type-checking side. We deliberately don't
enable the `PLR`/`PLC`/`PLW` (pylint refactor/convention/warning) groups — those are
mostly style opinions that would need per-project threshold tuning, versus `PLE`
(pylint errors), which flags things that are close to genuine bugs.

```bash
# Check formatting, lint, and types without changing anything
make lint

# Auto-fix formatting and lint issues where possible
make lint-fix
```

`make lint-fix` won't fix everything — anything requiring a judgment call (e.g. a long
line inside an agent system prompt, `zip()` without an explicit `strict=`) is left for a
human to resolve.

---

## Common Errors & Fixes

### `Import "rich.console" could not be resolved`

Pylance is not using the correct Python interpreter.

- **Fix:** Select the interpreter manually (see VS Code Setup above).
- **Root cause to avoid:** Never create a nested `.venv` inside the project — Pylance walks up
  from the file and stops at the nearest venv. A local empty venv shadows the root one.

### `Type of "X" is unknown`

pyright strict mode can't infer the type of a module-level variable.

- **Fix:** Add an explicit type annotation: `_console: Console = Console(force_terminal=True)`
- If it's a third-party type that remains unresolved, `reportUnknownVariableType = false` in
  `pyproject.toml` suppresses it.

### `Import "X" could not be resolved from source`

The module is installed but pyright can't find it.

- Check `venvPath` and `venv` are set in `[tool.pyright]`.
- Run `uv sync` to ensure all dependencies are installed.

---

## Venv Rules

- **One venv, at the repo root:** `.venv/` — created and managed by `uv sync`
- **Never create a nested `.venv`** — it shadows the root venv for all files inside and breaks
  import resolution
- If a stray inner venv appears: `rm -rf .venv` (in the nested directory, not the root)
