# Colima Troubleshooting

Colima is the macOS Docker VM used to run ChromaDB. These issues
are macOS-only.

## VZ driver crash / VM in broken state

**Symptom:** `make run` stalls on ChromaDB startup, or you see
errors like:

```text
FATA[0000] error starting vm: error at '/usr/local/...'
```

**What happens automatically:** `startup.py` detects the broken
VZ state and calls `_try_colima_qemu_recovery()`, which deletes
the VM metadata and restarts with the QEMU driver. Your
`chroma_data/` volume is host-mounted and is **not** deleted.

**Manual fix (if auto-recovery fails):**

```bash
colima delete
colima start --vm-type qemu
```

Then restart ChromaDB:

```bash
make chromadb-start
# or
docker start chromadb
```

## Colima not installed

```text
command not found: colima
```

Install via Homebrew:

```bash
brew install colima
```

## Colima not running

```text
Cannot connect to the Docker daemon at unix:///...
```

Start Colima:

```bash
colima start
# If VZ crashes again, force QEMU:
colima start --vm-type qemu
```

## ChromaDB container missing after Colima restart

After `colima delete`, containers are wiped. Re-run setup:

```bash
make chromadb-start
make ingest
```

The `chroma_data/` directory on the host is preserved, but the
container itself must be recreated.

## Slow startup after QEMU switch

QEMU is slightly slower to boot than VZ. The first `colima start
--vm-type qemu` after recovery may take 60-90 seconds. Subsequent
starts are faster.
