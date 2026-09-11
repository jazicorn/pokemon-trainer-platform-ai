# Runtime Errors

Common errors and fixes when running the application.

## ChromaDB Connection Error

```text
httpx.ConnectError: [Errno 61] Connection refused
```

**Fix:** Start ChromaDB:

```bash
docker start chromadb
# Or
docker run -d --name chromadb -p 8000:8000 chromadb/chroma:latest
```

## API Key Error

```text
AuthenticationError: Invalid API key
```

**Fix:** Check your `.env` file has the correct key value:

```bash
cat .env
# Verify key is set correctly
```

## API Key Empty at App Startup

```text
OSError: Environment variable ANTHROPIC_API_KEY is set but empty.
Your 1Password CLI integration may not be authenticated.
```

**Fix:** Your shell ran `op read` before 1Password was signed in, exporting
the variable as an empty string. Sign in and reload your shell:

```bash
eval $(op signin) && source ~/.zshrc
uv run python app.py
```

## API Key Contains a 1Password URI

```text
OSError: Environment variable ANTHROPIC_API_KEY contains a 1Password URI,
not an actual key. Run your command via op run so it is resolved.
```

**Fix:** Your env var holds an unresolved `op://` reference. Run via `op run`:

```bash
op run --env-file .env.op -- uv run python app.py
```

## Import Error

```text
ModuleNotFoundError: No module named 'agents'
```

**Fix:** Run from the project root with uv:

```bash
uv run python app.py
```

The project adds `src/` to the Python path at startup, so `from agents.trade_advisor import ...`
works. Running `python` directly without `uv` skips this.

## Docker Not Running

```text
Cannot connect to the Docker daemon
```

**Fix:**

- macOS/Windows: Start Docker Desktop
- Linux: `sudo systemctl start docker`
