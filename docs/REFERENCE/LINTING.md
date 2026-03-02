# Linting & Type Checking Setup

This project uses **basedpyright** (strict mode) for static type analysis and **ruff** for
formatting/linting.

---

## Tools

| Tool | Purpose | Config location |
| ------ | --------- | --------------- |
| `basedpyright` | Static type checking (strict) | `[tool.basedpyright]` in root `pyproject.toml` |
| `ruff` | Linting & formatting | `[tool.ruff]` in root `pyproject.toml` |
| Pylance | VS Code in-editor type checking | reads `[tool.pyright]` + `.vscode/settings.json` |

---

## Running the Linter

```bash
# From the repo root
uv run basedpyright capstone/src

# Or via make (if configured)
make lint
```

---

## VS Code Setup

Pylance (the VS Code Python extension) must be pointed at the correct interpreter to resolve
imports.

### One-time setup

1. `Cmd+Shift+P` → **"Python: Select Interpreter"**
2. Click **"Enter interpreter path..."**
3. Paste the full path:

   ```text
   /Users/jasmineanderson/Code/TW-Beach/katas-exercises/.venv/bin/python
   ```

> **Note:** `python.defaultInterpreterPath` in `.vscode/settings.json` only applies the first
> time VS Code opens the workspace. If an interpreter was previously selected, you must set it
> manually via the command palette.

### What's already configured

`.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.analysis.extraPaths": ["${workspaceFolder}/capstone/src"]
}
```

`pyproject.toml` `[tool.pyright]`:

```toml
extraPaths = ["capstone/src"]
venvPath = "."
venv = ".venv"
```

---

## pyproject.toml Configuration

```toml
[tool.basedpyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
venvPath = "."
venv = ".venv"
reportAny = false
reportExplicitAny = false
reportMissingTypeStubs = false
reportUnknownMemberType = false
reportUnknownVariableType = false   # rich/httpx types don't fully resolve in strict mode

[tool.pyright]
extraPaths = ["capstone/src"]
venvPath = "."
venv = ".venv"
```

The disabled checks are suppressed because third-party packages (`rich`, `httpx`, `pydantic-ai`)
don't always expose complete type information in basedpyright strict mode. All first-party code
is fully typed.

---

## Common Errors & Fixes

### `Import "rich.console" could not be resolved`

Pylance is not using the correct Python interpreter.

- **Fix:** Select the interpreter manually (see VS Code Setup above).
- **Root cause to avoid:** Never create a `capstone/.venv` — Pylance walks up from the file and
  stops at the nearest venv. A local empty venv shadows the root one.

### `Type of "X" is unknown`

basedpyright strict mode can't infer the type of a module-level variable.

- **Fix:** Add an explicit type annotation: `_console: Console = Console(force_terminal=True)`
- If it's a third-party type that remains unresolved, `reportUnknownVariableType = false` in
  `pyproject.toml` suppresses it.

### `Import "X" could not be resolved from source`

The module is installed but basedpyright can't find it.

- Check `venvPath` and `venv` are set in `[tool.basedpyright]`.
- Run `uv sync` to ensure all dependencies are installed.

---

## Venv Rules

- **One venv, at the repo root:** `.venv/` — created and managed by `uv sync`
- **Never create `capstone/.venv`** — it will shadow the root venv for all files inside
  `capstone/` and break import resolution
- If a stray inner venv appears: `rm -rf capstone/.venv`
