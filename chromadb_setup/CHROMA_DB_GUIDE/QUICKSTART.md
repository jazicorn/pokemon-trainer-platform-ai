# ChromaDB Docker Quick Start

Simple guide to get ChromaDB running with Docker and connect from Python.

> **Important:** This guide uses `httpx` directly instead of the `chromadb`
> Python package, which is incompatible with Python 3.14+.

## Prerequisites

- Docker installed ([Get Docker](https://docs.docker.com/get-docker/))
- **macOS:** Colima (the helper script will install it)
- Python 3.10+ with `uv`
- `httpx` (`uv add httpx`)

## Step 1: Start ChromaDB Server (Docker)

### Option A: Using the Helper Script (Recommended)

The quickstart script will handle this for you automatically — when it can't
reach the server it will prompt you to start it and fix permissions if needed.
See [Step 4](#step-4-run-the-test-script) to run the quickstart directly.

To start the server manually from inside the `chromadb/` folder:

```bash
./chromadb-docker.sh start
```

Or from the project root:

```bash
./chromadb/chromadb-docker.sh start
```

On macOS this automatically handles Colima setup and asks permission at each step.

### Option B: Manual Docker Command

```bash
# Pull the image
docker pull chromadb/chroma

# Run the server
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma \
  chromadb/chroma
```

**What this does:**

- `-d` — Runs in background (detached mode)
- `--name chromadb` — Names the container for easy reference
- `-p 8000:8000` — Maps port 8000 (access at `localhost:8000`)
- `-v $(pwd)/chroma_data:/chroma/chroma` — Persists data to `./chroma_data`

### Verify Server is Running

```bash
# Check container status
docker ps

# Test the server (v2 API)
curl http://localhost:8000/api/v2/heartbeat

# View logs
docker logs chromadb
```

> **Note:** The v1 API (`/api/v1/heartbeat`) returns 410 Gone. Always use v2.

## Step 2: Install Python Dependency

**Do not install `chromadb` or `chromadb-client`** — both are incompatible with Python 3.14+.

```bash
uv add httpx
```

## Step 3: Connect from Python

```python
import httpx

HOST = "localhost"
PORT = 8000
TENANT = "default_tenant"
DATABASE = "default_database"
BASE_URL = f"http://{HOST}:{PORT}"
BASE = f"{BASE_URL}/api/v2/tenants/{TENANT}/databases/{DATABASE}"

# Test connection
httpx.get(f"{BASE_URL}/api/v2/heartbeat", timeout=5).raise_for_status()
print("Connected!")

# Create collection
r = httpx.post(f"{BASE}/collections", json={
    "name": "my_collection",
    "get_or_create": True,
})
r.raise_for_status()
collection_id = r.json()["id"]

# Add documents (embeddings required by v2 API — supply from OpenAI, Ollama, etc.)
httpx.post(f"{BASE}/collections/{collection_id}/add", json={
    "ids": ["doc1", "doc2"],
    "documents": ["This is a test document", "This is another document"],
    "embeddings": [[0.1, 0.2, 0.3, ...], [0.4, 0.5, 0.6, ...]],
    "metadatas": [{"source": "test"}, {"source": "test"}],
}).raise_for_status()

# Query
r = httpx.post(f"{BASE}/collections/{collection_id}/query", json={
    "query_embeddings": [[0.1, 0.2, 0.3, ...]],
    "n_results": 2,
})
r.raise_for_status()
results = r.json()
print(results["documents"][0])
```

See [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) for complete working code including
embedding providers (OpenAI, Ollama, dummy).

## Step 4: Run the Test Script

Run from the **project root**:

```bash
uv run chroma-quickstart
```

The script will automatically check if the server is running. If it isn't, it
will prompt you to start it — and if `chromadb-docker.sh` doesn't have execute
permissions yet, it will offer to fix that for you too.

## Docker Management Commands

### Using the Helper Script

From inside the `chromadb/` folder:

```bash
./chromadb-docker.sh start      # Start server
./chromadb-docker.sh stop       # Stop server
./chromadb-docker.sh restart    # Restart server
./chromadb-docker.sh status     # Check status
./chromadb-docker.sh logs       # View logs
./chromadb-docker.sh remove     # Remove (asks about data)
```

### Using Docker Directly

```bash
# Stop
docker stop chromadb

# Start (after stopping)
docker start chromadb

# Restart
docker restart chromadb

# View logs
docker logs chromadb
docker logs -f chromadb  # follow (live tail)

# Remove container
docker stop chromadb
docker rm chromadb

# Remove everything including data
docker stop chromadb
docker rm chromadb
rm -rf ./chroma_data
```

## Production Setup (Docker Compose)

### Create `docker-compose.yml`

```yaml
services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb
    ports:
      - "8000:8000"
    volumes:
      - ./chroma_data:/chroma/chroma
    environment:
      # Optional: Add authentication
      - CHROMA_SERVER_AUTH_PROVIDER=chromadb.auth.token.TokenAuthenticationServerProvider
      - CHROMA_SERVER_AUTH_TOKEN_TRANSPORT_HEADER=X-Chroma-Token
      - CHROMA_SERVER_AUTH_CREDENTIALS=your-secret-token-here
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v2/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Start with Docker Compose

```bash
# Start server
docker-compose up -d

# View logs
docker-compose logs -f

# Stop server
docker-compose down

# Stop and remove data
docker-compose down -v
```

### Connect with Authentication (if enabled)

```python
import httpx

headers = {"X-Chroma-Token": "your-secret-token-here"}

r = httpx.get(f"{BASE}/collections", headers=headers)
r.raise_for_status()
```

## Troubleshooting

### Port Already in Use

```bash
# Find what's using port 8000
lsof -i :8000              # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Use a different port
docker run -d --name chromadb -p 8001:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma chromadb/chroma

# Update BASE in Python
BASE = "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database"
```

### Cannot Connect

```bash
# Check container is running
docker ps

# Check logs for errors
docker logs chromadb

# Test v2 API from command line
curl http://localhost:8000/api/v2/heartbeat

# Try with explicit IP
curl http://127.0.0.1:8000/api/v2/heartbeat
```

### macOS: Colima Not Running

```bash
colima start
./chromadb-docker.sh start
```

### Permission Issues with Volume

```bash
# Fix permissions on data directory
sudo chown -R $(whoami):$(whoami) ./chroma_data
chmod -R 755 ./chroma_data
```

### 410 Gone Error

You're hitting the v1 API. Use `/api/v2/...` paths everywhere.

### 422 Unprocessable Entity on `/add`

The v2 API requires `"embeddings"` on every add call. See [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md)
for embedding provider examples.

## Advantages of Docker Setup

| Benefit | Description |
| ------- | ----------- |
| ✅ **Isolation** | Server runs in its own environment |
| ✅ **Consistency** | Same setup across all machines |
| ✅ **Easy Updates** | Just pull new image |
| ✅ **Production Ready** | Same setup for dev and prod |
| ✅ **Python 3.14+ Compatible** | Works with any Python version |
| ✅ **Resource Management** | Control memory/CPU limits |
| ✅ **Easy Cleanup** | Remove container and you're done |

## Project Structure

```text
katas-exercises/
├── chromadb/
│   ├── CHROMA_DB_GUIDE/
│   │   ├── DOCKER_QUICKSTART.md     # this file
│   │   ├── RESOURCES.md
│   │   ├── TROUBLESHOOTING.md
│   │   └── USAGE_EXAMPLES.md
│   ├── chroma_data/                 # persisted data (created by Docker)
│   ├── chromadb-docker.sh           # Docker management script
│   ├── chromadb_quickstart.py       # test script
│   ├── create_vector_store.py
│   ├── test_vector_store.py
│   └── README.md
└── pyproject.toml
```

## Quick Reference

```bash
# Start server and run quickstart (from project root)
./chromadb/chromadb-docker.sh start
uv run chroma-quickstart

# Or just run the quickstart — it will offer to start the server for you
uv run chroma-quickstart

# Docker helpers (from inside chromadb/ folder)
./chromadb-docker.sh status
./chromadb-docker.sh logs
```

```python
# Python connection pattern
import httpx

BASE = "http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database"

# Heartbeat
httpx.get("http://localhost:8000/api/v2/heartbeat").raise_for_status()

# Create collection
r = httpx.post(f"{BASE}/collections", json={"name": "test", "get_or_create": True})
r.raise_for_status()
collection_id = r.json()["id"]
```

## Next Steps

1. ✅ Server is running at `http://localhost:8000`
2. ✅ Install `httpx` (`uv add httpx`)
3. ✅ Run `uv run chroma-quickstart` to test
4. ✅ Read [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) for complete patterns
5. ✅ Start building your application!

---

[← Back to README](../README.md)
