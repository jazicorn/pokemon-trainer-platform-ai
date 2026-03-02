# Troubleshooting Guide

Solutions to common ChromaDB problems when using the Docker server setup
with Python 3.14+ and the `httpx` HTTP client.

## Table of Contents

1. [Server Connection Issues](#server-connection-issues)
2. [Docker Issues](#docker-issues)
3. [API Errors](#api-errors)
4. [macOS / Colima Issues](#macos--colima-issues)
5. [Performance Problems](#performance-problems)
6. [Getting More Help](#getting-more-help)

---

## Server Connection Issues

### Connection refused

**Symptoms:**

```http
httpx.ConnectError: All connection attempts failed
```

**Solutions:**

```bash
# Start the ChromaDB container
./chromadb-docker.sh start

# Check it's running
./chromadb-docker.sh status

# Test connection directly
curl http://localhost:8000/api/v2/heartbeat
# Expected: {"nanosecond heartbeat": <number>}

# View logs for errors
./chromadb-docker.sh logs
```

**Verify in Python:**

```python
import httpx

r = httpx.get("http://localhost:8000/api/v2/heartbeat", timeout=5)
print(r.status_code, r.json())   # 200, {"nanosecond heartbeat": ...}
```

### 410 Gone on heartbeat

**Symptoms:**

```json
{"error": "Unimplemented", "message": "The v1 API is deprecated. Please use /v2 apis"}
```

**Cause:** You're hitting `/api/v1/heartbeat`. ChromaDB 1.x dropped the v1 API.

**Fix:** Use `/api/v2/heartbeat` everywhere. All paths must include tenant and
database:

```http
http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections
```

### `import chromadb` fails or crashes

**Symptoms:**

```bash
ModuleNotFoundError: No module named 'chromadb'
# or
pydantic.v1.errors.ConfigError: unable to infer type for attribute "chroma_server_nofile"
# or
UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.
```

**Cause:** The `chromadb` and `chromadb-client` packages both depend on
Pydantic V1, which is incompatible with Python 3.14+. Even after installing
`chromadb-client`, the actual `chromadb/` module directory may not exist in
site-packages — it's a known broken install.

**Fix:** Don't use either package. Use `httpx` directly:

```bash
uv add httpx
```

```python
import httpx

BASE = "http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database"

# Create collection
r = httpx.post(f"{BASE}/collections", json={"name": "my_collection", "get_or_create": True})
r.raise_for_status()
collection_id = r.json()["id"]
```

---

## Docker Issues

### Container won't start

**Symptoms:**

```bash
Error response from daemon: Ports are not available
```

**Solutions:**

```bash
# Check if port 8000 is in use
lsof -i :8000

# Stop whatever is using it, or use a different port
docker run -d --name chromadb -p 8001:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma chromadb/chroma

# Update BASE in Python to match
BASE = "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database"
```

### Container keeps restarting

```bash
# Check root cause in logs
docker logs chromadb

# Common causes:
# - Port already in use
# - Data directory permission issues
# - Insufficient memory

# Fix data directory permissions
chmod -R 755 ./chroma_data
sudo chown -R $(whoami):$(whoami) ./chroma_data
```

### Data not persisting after container restart

**Cause:** Missing volume mount — data stored inside the container is lost
when it stops.

```bash
# ❌ Wrong — no volume mount
docker run -d --name chromadb -p 8000:8000 chromadb/chroma

# ✅ Correct — with persistent volume
docker run -d --name chromadb -p 8000:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma chromadb/chroma

# The helper script always mounts the volume correctly
./chromadb-docker.sh start
```

---

## API Errors

### 422 Unprocessable Entity on `/add`

**Symptoms:**

```json
{"error": "ChromaError", "message": "Failed to deserialize the JSON body into the target type: missing field `embeddings`"}
```

**Cause:** The ChromaDB v2 API requires embeddings on every add call. The
server no longer generates them from raw text.

**Fix:** Always include `"embeddings"` in your add request:

```python
r = httpx.post(f"{BASE}/collections/{collection_id}/add", json={
    "ids": ["doc1"],
    "documents": ["Hello world"],
    "embeddings": [[0.1, 0.2, 0.3, ...]],   # required
})
r.raise_for_status()
```

For testing without a real model, a simple hash-based dummy embedding works:

```python
import math

EMBEDDING_DIM = 384


def dummy_embedding(text: str) -> list[float]:
    """Produce a deterministic unit-vector for `text` (not semantically meaningful)."""
    vec = [(hash(text + str(i)) & 0xFFFFFF) / 0xFFFFFF * 2 - 1 for i in range(EMBEDDING_DIM)]
    magnitude = math.sqrt(sum(x * x for x in vec))
    return [x / magnitude for x in vec]
```

### 404 Not Found on DELETE `/collections/{uuid}`

**Cause:** The v2 API deletes collections by **name**, not by UUID.

```python
# ❌ Wrong — 404
httpx.delete(f"{BASE}/collections/678e7c3b-d37c-44d2-af9d-bb992ad05a9f")

# ✅ Correct — 200
httpx.delete(f"{BASE}/collections/my_collection_name")
```

### Collection already exists

**Fix:** Use `"get_or_create": True` in your POST body:

```python
r = httpx.post(f"{BASE}/collections", json={
    "name": "my_collection",
    "get_or_create": True,   # safe — won't error if exists
})
r.raise_for_status()
```

### Document ID already exists on `/add`

**Fix:** Use the upsert endpoint instead of add:

```python
r = httpx.post(f"{BASE}/collections/{collection_id}/upsert", json={
    "ids": ["doc1"],
    "documents": ["Updated content"],
    "embeddings": [[...]],
})
r.raise_for_status()
```

---

## macOS / Colima Issues

### `failed to connect to the docker API at unix:///.../.colima/default/docker.sock`

**Cause:** Colima is not running.

**Fix:**

```bash
colima start
# then retry
./chromadb-docker.sh start
```

Or just run the script — it will detect the issue, ask permission, and start
Colima for you.

### Script asks to start Colima even though it's already running

**Cause:** The socket file doesn't exist yet even though `colima status` says
running. The script uses the socket file as the source of truth.

**Fix:** Wait a few seconds after `colima start` before running the script,
or run `colima stop && colima start` to get a clean state.

### Colima not installed

```bash
brew install colima docker
colima start
```

The `chromadb-docker.sh` script will offer to do this for you automatically.

---

## Performance Problems

### Slow queries

```python
# Reduce n_results
r = httpx.post(f"{BASE}/collections/{cid}/query", json={
    "query_embeddings": [query_embedding],
    "n_results": 5,   # lower = faster
})
r.raise_for_status()

# Use metadata filters to narrow the search space
r = httpx.post(f"{BASE}/collections/{cid}/query", json={
    "query_embeddings": [query_embedding],
    "n_results": 5,
    "where": {"category": "specific_category"},
})
r.raise_for_status()
```

### Slow document addition

Process in batches and generate all embeddings before sending:

```python
def add_in_batches(
    base_url: str,
    collection_id: str,
    documents: list[str],
    embeddings: list[list[float]],
    ids: list[str],
    batch_size: int = 500,
) -> None:
    """Add documents in fixed-size batches to avoid request timeouts."""
    total = len(documents)
    for start in range(0, total, batch_size):
        end = start + batch_size
        r = httpx.post(f"{base_url}/collections/{collection_id}/add", json={
            "ids": ids[start:end],
            "documents": documents[start:end],
            "embeddings": embeddings[start:end],
        }, timeout=60)
        r.raise_for_status()
        print(f"Added {min(end, total)}/{total}")
```

---

## Getting More Help

### Run Diagnostics

```bash
# Container status
./chromadb-docker.sh status

# Container logs
./chromadb-docker.sh logs

# Direct API test
curl http://localhost:8000/api/v2/heartbeat
curl http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections
```

### Collect Debug Information

```python
import sys
import platform
import httpx

print(f"Python: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"httpx: {httpx.__version__}")

try:
    r = httpx.get("http://localhost:8000/api/v2/heartbeat", timeout=5)
    r.raise_for_status()
    print(f"Server: Connected ({r.json()})")
except httpx.HTTPError as e:
    print(f"Server: Not connected — {e}")
```

### Common Error Reference

| Error                           | Cause                                   | Fix                                      |
|---------------------------------|-----------------------------------------|------------------------------------------|
| `ConnectError`                  | Server not running                      | `./chromadb-docker.sh start`             |
| `410 Gone`                      | Using v1 API                            | Switch to `/api/v2/...` paths            |
| `422` on `/add`                 | Missing `embeddings` field              | Add `"embeddings"` to request body       |
| `404` on DELETE                 | Deleting by UUID                        | Delete by collection name                |
| Pydantic V1 crash               | `chromadb`/`chromadb-client` installed  | Remove them, use `httpx`                 |
| `ModuleNotFoundError: chromadb` | Broken `chromadb-client` install        | Remove it, use `httpx`                   |
| Docker socket missing           | Colima not running (macOS)              | `colima start`                           |
| Port 8000 in use                | Another process on the port             | `lsof -i :8000` then kill or change port |

---

[Back to README](../README.md) | [Usage Examples →](USAGE_EXAMPLES.md)
