# 1Password CLI Integration

This project uses the 1Password CLI (`op`) to manage API keys. This document
covers every approach, when to use each one, and how to troubleshoot common
errors.

## How It Works

API keys (Anthropic, OpenAI, Google) are stored as items in your 1Password
vault. The CLI fetches them at runtime so secrets never live in plain text on
disk or in your shell history.

`validate_environment()` in `startup.py` detects the `op` CLI and gives
1Password-specific guidance when a key is missing or unresolved.

The same mechanism also covers secrets that aren't vendor API keys — e.g. the
Web API's `TENANT_DB_ENCRYPTION_KEY` (see [Other Secrets](#other-secrets)
below). Anything with an `op://` reference in `.env.op` works the same way,
regardless of where the value originally came from.

## Approaches

### Option A — `.env.op` file (Recommended)

The project ships a `.env.op` file containing `op://` URI references:

```text
ANTHROPIC_API_KEY=op://Private/ANTHROPIC_API_KEY/credential
GOOGLE_API_KEY=op://Private/GOOGLE_API_KEY/credential
# OPENAI_API_KEY=op://Private/OPENAI_API_KEY/credential  ← uncomment if you have this
```

These are URIs, not actual keys — the file is safe to commit. Secrets are
resolved by `op run` at the moment you run the command, so 1Password only
needs to be unlocked then (not at terminal startup).

> **Important:** `op run` errors on any `op://` reference it cannot resolve.
> Only uncomment lines for keys that actually exist in your 1Password vault.

```bash
# Run the app
op run --env-file .env.op -- uv run python app.py

# Run tests with live keys
op run --env-file .env.op -- uv run pytest tests/ -v --tb=short

# Run any command with resolved secrets
op run --env-file .env.op -- <any command>
```

### Option B — `.zshrc` with `op read`

Keys are resolved once when you open a terminal via `$(op read ...)` in your
`~/.zshrc`:

```bash
export ANTHROPIC_API_KEY=$(op read "op://Private/ANTHROPIC_API_KEY/credential")
export GOOGLE_API_KEY=$(op read "op://Private/GOOGLE_API_KEY/credential")
```

1Password must be unlocked at terminal startup. If it is not, `op read` fails
silently and the variable is exported as an empty string — which triggers the
error described in [Troubleshooting](#troubleshooting) below.

### Option C — `.zshrc` with `op://` URI + `op run`

Export the `op://` URI directly (no `$(op read ...)`) and always run via
`op run --`:

```bash
# ~/.zshrc
export ANTHROPIC_API_KEY="op://Private/ANTHROPIC_API_KEY/credential"
```

```bash
op run -- uv run python app.py
```

`op run` sees the `op://` value in the environment and resolves it before
spawning the child process. 1Password does not need to be unlocked at terminal
startup.

## Comparison

| | Option A `.env.op` | Option B `.zshrc op read` | Option C `.zshrc URI` |
| --- | --- | --- | --- |
| 1Password locked at startup OK | ✅ | ❌ | ✅ |
| No `op run` wrapper needed | ❌ | ✅ | ❌ |
| File documents required secrets | ✅ | ❌ | ❌ |
| Safe to commit | ✅ | n/a | n/a |
| Empty-string risk | ❌ | ✅ | ❌ |

## One-Time Setup

```bash
# 1. Install 1Password CLI
brew install --cask 1password/tap/1password-cli

# 2. Sign in (links CLI to your 1Password desktop app)
eval $(op signin)

# 3. Verify
op whoami
```

After this, 1Password CLI uses biometric unlock via the desktop app — you
rarely need to run `op signin` again unless your session expires.

## Daily Usage

```bash
# Recommended: use .env.op (works regardless of terminal age)
op run --env-file .env.op -- uv run python app.py

# Or if using .zshrc op read: just open a fresh terminal
# The key is loaded automatically on shell startup
```

## Other Secrets

Not every secret in this project is a vendor-issued API key. `TENANT_DB_ENCRYPTION_KEY`
(Web API, `make run-api`) is one you generate yourself locally — 1Password just
stores it the same way as the others once it exists:

```bash
# 1. Generate the key
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Create an item for it in your Private vault named TENANT_DB_ENCRYPTION_KEY,
#    with the generated value as its "credential" field — matching the op://
#    reference path .env.op already expects:
#    op://Private/TENANT_DB_ENCRYPTION_KEY/credential

# 3. Uncomment its line in .env.op
```

**Back this one up somewhere outside 1Password too, not just inside it** — see
`.env.op`'s and `src/config.py`'s comments on this key: losing it makes every
tenant's stored `platform_db_url` permanently unrecoverable, not just hard to
find. 1Password itself has its own recovery mechanisms, but treat this key
with the same "if this is gone, it's really gone" seriousness regardless of
where it's stored.

## Troubleshooting

See [TROUBLESHOOTING/1password.md](TROUBLESHOOTING/1password.md).
