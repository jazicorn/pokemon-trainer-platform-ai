# 1Password Troubleshooting

## `ANTHROPIC_API_KEY is set but empty`

```text
OSError: Environment variable ANTHROPIC_API_KEY is set but empty.
Your 1Password CLI integration may not be authenticated.

Option A — use the project .env.op file (avoids this issue):
  op run --env-file .env.op -- uv run python app.py

Option B — sign in and reload your shell:
  eval $(op signin) && source ~/.zshrc
```

**Cause:** Your `.zshrc` runs `op read` at terminal startup but 1Password was
not unlocked at that moment. The variable was exported as an empty string.

**Fix (Option A — avoids this permanently):**

```bash
op run --env-file .env.op -- uv run python app.py
```

**Fix (Option B — for the current terminal):**

```bash
eval $(op signin) && source ~/.zshrc
uv run python app.py
```

## `ANTHROPIC_API_KEY contains a 1Password URI`

```text
OSError: Environment variable ANTHROPIC_API_KEY contains a 1Password URI,
not an actual key. Run your command via op run so it is resolved.
```

**Cause:** You exported `ANTHROPIC_API_KEY=op://...` directly but ran the
command without `op run`.

**Fix:**

```bash
op run --env-file .env.op -- uv run python app.py
# or
op run -- uv run python app.py
```

## `op: command not found`

1Password CLI is not installed or not in `PATH`:

```bash
# Install
brew install --cask 1password/tap/1password-cli

# Verify
which op
op --version
```

## `[AUTH] error: you are not currently signed in`

```bash
eval $(op signin)
```

If you have the 1Password desktop app open, it will prompt for biometric
confirmation and the CLI will be authorized automatically.

## Key not loading in fresh terminal

Confirm your `.zshrc` contains the export:

```bash
grep ANTHROPIC ~/.zshrc
# Should show: export ANTHROPIC_API_KEY=$(op read "op://...")
```

If it is missing, add it or switch to Option A (`.env.op`).
