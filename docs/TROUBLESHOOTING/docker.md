# Docker Troubleshooting

## ChromaDB container not found

```text
Error: No such container: chromadb
```

The container was never created or was deleted. Re-create it:

```bash
make chromadb-start
# or manually:
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -v "$(pwd)/chroma_data:/chroma/chroma" \
  chromadb/chroma:latest
```

## Port 8000 already in use

```text
Error: Bind for 0.0.0.0:8000 failed: port is already allocated
```

Find and stop whatever is using port 8000:

```bash
lsof -i :8000
kill -9 <PID>
docker start chromadb
```

## Container exits immediately after start

Check the container logs:

```bash
docker logs chromadb
```

Common causes:

- Volume mount path doesn't exist — run `mkdir -p chroma_data`
- Port conflict — see above
- Image not pulled — `docker pull chromadb/chroma:latest`

## `docker: command not found` on macOS

Docker CLI is not in `PATH`. Options:

- Install Docker Desktop (includes CLI)
- Install via Homebrew: `brew install docker` (requires Colima
  or another runtime)

## Container running but ChromaDB unreachable

```text
httpx.ConnectError: [Errno 61] Connection refused
```

The container is up but ChromaDB has not finished initializing.
Wait a few seconds, then retry. If it persists:

```bash
docker logs chromadb --tail 20
docker restart chromadb
```

## Data lost after `docker rm chromadb`

If you removed the container with `-v` (volume removal), the
`chroma_data/` directory on the host may be intact. Verify:

```bash
ls chroma_data/
```

If the host directory exists, recreate the container (it will
re-mount existing data). If it is empty, re-ingest:

```bash
make chromadb-start
make ingest
```
