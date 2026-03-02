# ChromaDB Setup (Docker)

Quick setup scripts and tools for ChromaDB vector database using Docker.

## 📦 Contents

```text
chromadb_setup/
├── CHROMA_DB_GUIDE/
│   ├── CHROMADB_SERVER_GUIDE.md
│   ├── DOCKER_QUICKSTART.md
│   ├── RESOURCES.md
│   ├── TROUBLESHOOTING.md
│   └── USAGE_EXAMPLES.md
├── chroma_data/                 # Persisted data (created by Docker)
├── chromadb-docker.sh           # Docker management script
├── chromadb_quickstart.py       # Quick start script (HTTP client mode)
├── create_vector_store.py       # Production vector store implementation
├── test_vector_store.py         # Test suite
└── README.md                    # This file
```

**Note:** This project uses Docker for the ChromaDB server and `httpx` for
Python HTTP communication. No `chromadb` Python package is required or
recommended — it has compatibility issues with Python 3.14+.

## 🚀 Quick Start

### Prerequisites

- Docker installed ([Get Docker](https://docs.docker.com/get-docker/))
- **macOS:** Colima (the script will install it for you if missing)
- Python 3.10+ with `uv`
- `httpx` (already a transitive dependency in most projects)

### 1. Install Python Dependency

Only `httpx` is needed. No `chromadb` package required:

```bash
uv add httpx
```

### 2. Run the Quickstart

Run from the **project root**:

```bash
uv run chromadb
```

The quickstart will check if ChromaDB is already running. If it isn't, it will
prompt you to start it automatically:

```bash
❌ Cannot connect to ChromaDB at localhost:8000
   Start it now with ./chromadb-docker.sh start? [y/N]
```

Type `y` and the script will start the Docker server for you, wait for it to be
ready, then continue running the tests.

If `chromadb-docker.sh` doesn't have execute permissions yet, the script will
detect this and prompt you to fix it:

```bash
   ✅ chromadb-docker.sh is already executable
   — or —
   './chromadb-docker.sh' exists but is not executable.
   Fix with: chmod +x chromadb-docker.sh
```

To start the server manually instead:

```bash
chmod +x chromadb-docker.sh   # first time only
./chromadb-docker.sh start
```

Or with Docker directly:

```bash
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma \
  chromadb/chroma
```

The script is registered in `pyproject.toml` under `[project.scripts]`:

```toml
[project.scripts]
chromadb = "chromadb_setup.chromadb_quickstart:main"
```

## 📁 Project Structure

The `chromadb` folder lives at the **project root**, alongside `rag`, `katas`,
and other modules, so it can be shared across assignments:

```text
katas-exercises/
├── chromadb_setup/          # ← shared ChromaDB setup (was rag/chromadb-setup/)
├── rag/
├── katas/
├── capstone/
└── pyproject.toml
```

## 🐳 Docker Management

### Using the Helper Script

```bash
./chromadb-docker.sh start      # Start ChromaDB server
./chromadb-docker.sh stop       # Stop server
./chromadb-docker.sh restart    # Restart server
./chromadb-docker.sh status     # Check status
./chromadb-docker.sh logs       # View logs
./chromadb-docker.sh update     # Pull latest image and restart
./chromadb-docker.sh remove     # Remove container (asks about data)
```

### Using Docker Directly

```bash
docker start chromadb           # Start server
docker stop chromadb            # Stop server
docker restart chromadb         # Restart server
docker ps                       # Check status
docker logs chromadb            # View logs
docker logs -f chromadb         # Follow logs (live tail)
```

### Check Server Health

```bash
curl http://localhost:8000/api/v2/heartbeat
# Returns: {"nanosecond heartbeat": <timestamp>}
```

## 🔌 Connecting from Python

**Do not use `chromadb.HttpClient`** — the `chromadb` and `chromadb-client`
packages have Python 3.14 compatibility issues. Use `httpx` directly:

```python
import httpx

HOST = "localhost"
PORT = 8000
TENANT = "default_tenant"
DATABASE = "default_database"
BASE_URL = f"http://{HOST}:{PORT}"
BASE = f"{BASE_URL}/api/v2/tenants/{TENANT}/databases/{DATABASE}"

# Check server is up
httpx.get(f"{BASE_URL}/api/v2/heartbeat").raise_for_status()

# Create or get a collection (returns collection ID)
r = httpx.post(f"{BASE}/collections", json={"name": "my_collection", "get_or_create": True})
r.raise_for_status()
collection_id = r.json()["id"]

# Add documents (embeddings required in v2 API)
httpx.post(f"{BASE}/collections/{collection_id}/add", json={
    "ids": ["doc1"],
    "documents": ["Hello world"],
    "embeddings": [[0.1, 0.2, ...]],   # must provide embeddings
}).raise_for_status()

# Query
r = httpx.post(f"{BASE}/collections/{collection_id}/query", json={
    "query_embeddings": [[0.1, 0.2, ...]],
    "n_results": 5,
})
r.raise_for_status()
results = r.json()

# Delete collection by name
httpx.delete(f"{BASE}/collections/my_collection").raise_for_status()
```

> **Important:** ChromaDB v2 API requires embeddings on every `add` and
> `query` call. The server no longer generates them from raw text. See
> `chromadb_quickstart.py` for a working dummy embedding implementation
> and guidance on plugging in a real model.

## 📜 Scripts

### chromadb_quickstart.py

Verifies your Docker setup end-to-end:

- ✅ Connects to ChromaDB server
- ✅ Tests basic CRUD operations
- ✅ Tests persistent storage
- ✅ Creates a sample database

Uses a deterministic hash-based embedding for testing (not semantically
meaningful — swap in a real model for actual similarity search).

```bash
# Start the server first
./chromadb-docker.sh start

# Then run from the project root
uv run chromadb
```

## 🛠️ Requirements

### System Requirements

- Docker (latest stable version)
- **macOS:** Colima (lightweight Docker runtime — managed by `chromadb-docker.sh`)
- Python 3.10 or higher (tested on 3.14)
- 2 GB RAM minimum (4 GB+ recommended)
- 1 GB disk space (for Docker image + data)

### Python Dependencies

```toml
[project]
dependencies = [
    "httpx>=0.28.1",   # HTTP client for ChromaDB v2 API
]
```

Do **not** add `chromadb` or `chromadb-client` — both have Python 3.14
compatibility issues via Pydantic V1.

## 🔄 Why Docker + httpx?

**The problem:** ChromaDB's Python package (and `chromadb-client`) depend on
Pydantic V1, which is incompatible with Python 3.14+. Even the "client-only"
package installs broken code.

**The solution:** Run ChromaDB in Docker (its own isolated Python environment)
and talk to it over HTTP using `httpx`. This gives you:

- ✅ Works with any Python version including 3.14+
- ✅ Zero Pydantic V1 on your side
- ✅ Production-ready client/server architecture
- ✅ Easy updates — just pull a new Docker image
- ✅ Consistent across all machines

## 📝 API Quick Reference

All paths are relative to:

```http
http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database
```

| Operation            | Method | Path                              |
|----------------------|--------|-----------------------------------|
| Heartbeat            | GET    | `/api/v2/heartbeat`               |
| List collections     | GET    | `.../collections`                 |
| Create collection    | POST   | `.../collections`                 |
| Delete collection    | DELETE | `.../collections/{name}`          |
| Add documents        | POST   | `.../collections/{id}/add`        |
| Get documents by ID  | POST   | `.../collections/{id}/get`        |
| Query documents      | POST   | `.../collections/{id}/query`      |

## 🆘 Troubleshooting

### Server Won't Start (macOS)

```bash
# Colima not running
colima start

# Then retry
./chromadb-docker.sh start
```

### Cannot Connect from Python

```bash
# Verify server is up
curl http://localhost:8000/api/v2/heartbeat

# Check Docker container
./chromadb-docker.sh status
docker logs chromadb
```

### 422 Unprocessable Entity on /add

The v2 API requires embeddings on every add call. You must pass an
`"embeddings"` field alongside `"documents"` and `"ids"`.

### 404 on DELETE /collections/{id}

Delete by **name**, not ID:

```http
DELETE /collections/my_collection_name   ✅
DELETE /collections/678e7c3b-...         ❌
```

### Port Already in Use

```bash
lsof -i :8000                        # find what's using it
./chromadb-docker.sh stop   # or stop our container
```
