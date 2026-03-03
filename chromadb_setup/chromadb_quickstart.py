#!/usr/bin/env python3
"""
ChromaDB Quick Start Script (Docker / HTTP Mode)

Talks directly to the ChromaDB Docker server over HTTP using httpx.
No chromadb client package needed — zero Pydantic V1 issues.

ChromaDB v2 API requires embeddings to be provided with every document.
This script uses a simple hash-based embedding for testing, and shows
how to plug in real embeddings when you have a model available.

Prerequisites:
    ./chromadb-docker.sh start

Run:
    uv run chromadb          # from project root (registered in pyproject.toml)
    python chromadb_quickstart.py  # from within the chromadb/ folder

The script will prompt you to start the Docker server automatically if it
isn't already running, and will check/fix execute permissions on
chromadb-docker.sh if needed.
"""

import math
import os
import subprocess
import sys
import time
from pathlib import Path

from typing import Any

import httpx

HOST = "localhost"
PORT = 8000
TENANT = "default_tenant"
DATABASE = "default_database"
BASE_URL = f"http://{HOST}:{PORT}"
BASE = f"{BASE_URL}/api/v2/tenants/{TENANT}/databases/{DATABASE}"
EMBEDDING_DIM = 384  # must match whatever model you use; 384 = all-MiniLM-L6-v2

_DOCKER_SCRIPT = Path("./chromadb-docker.sh")
_STARTUP_WAIT = 8   # seconds to poll for ChromaDB readiness after launch


# ─── Simple deterministic embedding for testing ───────────────────────────────
# Not semantically meaningful — just valid floats so the API accepts the payload.
# Replace with a real model (e.g. OpenAI, Ollama) for actual similarity search.

def dummy_embedding(text: str) -> list[float]:
    """Deterministic hash-based unit-vector. Good enough for API testing."""
    vec = [(hash(f"{text}{i}") & 0xFFFFFF) / 0xFFFFFF * 2 - 1 for i in range(EMBEDDING_DIM)]
    magnitude = math.sqrt(sum(x * x for x in vec))
    return [x / magnitude for x in vec]


def dummy_embeddings(texts: list[str]) -> list[list[float]]:
    return [dummy_embedding(t) for t in texts]


# ─── Low-level HTTP helpers ───────────────────────────────────────────────────

def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    r = httpx.post(f"{BASE}{path}", json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> None:
    httpx.delete(f"{BASE}{path}", timeout=10).raise_for_status()


# ─── ChromaDB API wrappers ────────────────────────────────────────────────────

def heartbeat() -> bool:
    """Returns True if the ChromaDB server is reachable, False otherwise."""
    try:
        httpx.get(f"{BASE_URL}/api/v2/heartbeat", timeout=5).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def get_or_create_collection(name: str, metadata: dict[str, Any] | None = None) -> str:
    """Create or retrieve a collection; returns its ID."""
    body: dict[str, Any] = {"name": name, "get_or_create": True}
    if metadata:
        body["metadata"] = metadata
    return _post("/collections", body)["id"]


def delete_collection(name: str) -> None:
    _delete(f"/collections/{name}")


def add_documents(
    collection_id: str,
    documents: list[str],
    ids: list[str],
    metadatas: list[dict[str, Any]] | None = None,
    embeddings: list[list[float]] | None = None,
) -> None:
    """Add documents to a collection.

    If `embeddings` is omitted, deterministic dummy embeddings are generated
    automatically — suitable for API testing but not semantic search.
    """
    body: dict[str, Any] = {
        "documents": documents,
        "ids": ids,
        "embeddings": embeddings if embeddings is not None else dummy_embeddings(documents),
    }
    if metadatas:
        body["metadatas"] = metadatas
    _post(f"/collections/{collection_id}/add", body)


def get_documents(collection_id: str, ids: list[str]) -> dict[str, Any]:
    return _post(f"/collections/{collection_id}/get", {"ids": ids})


def query_collection(
    collection_id: str,
    query_texts: list[str] | None = None,
    query_embeddings: list[list[float]] | None = None,
    n_results: int = 2,
) -> dict[str, Any]:
    """Query a collection by text or pre-computed embeddings.

    Exactly one of `query_texts` or `query_embeddings` must be provided.
    When `query_texts` is given, dummy embeddings are generated automatically.
    """
    if query_embeddings is None and query_texts is None:
        raise ValueError("Provide either query_texts or query_embeddings.")
    embeddings = query_embeddings if query_embeddings is not None else dummy_embeddings(query_texts)  # type: ignore[arg-type]
    return _post(f"/collections/{collection_id}/query", {
        "query_embeddings": embeddings,
        "n_results": n_results,
    })


# ─── Server startup helpers ───────────────────────────────────────────────────

def _ensure_executable() -> bool:
    """Check if chromadb-docker.sh is executable; offer to fix it if not.

    Returns True if the script is (or becomes) executable, False otherwise.
    """
    script = _DOCKER_SCRIPT.resolve()
    if not script.exists():
        print(f"   ('{_DOCKER_SCRIPT}' not found in the current directory)")
        return False

    if os.access(script, os.X_OK):
        print(f"   ✅ {_DOCKER_SCRIPT} is already executable")
        return True

    print(f"   '{_DOCKER_SCRIPT}' exists but is not executable.")
    try:
        answer = input(f"   Run 'chmod +x {_DOCKER_SCRIPT}' now? [y/N] ").strip().lower()
    except EOFError:
        answer = ""

    if answer != "y":
        print(f"   Fix manually with: chmod +x {_DOCKER_SCRIPT}")
        return False

    result = subprocess.run(["chmod", "+x", str(script)], check=False)
    if result.returncode == 0:
        print(f"   ✅ {_DOCKER_SCRIPT} is now executable")
        return True

    print(f"   ❌ chmod failed with exit code {result.returncode}")
    return False


def _offer_to_start() -> bool:
    """Prompt to run ./chromadb-docker.sh start.

    Returns True if the server is reachable after the script completes,
    False if the script is missing, not executable, user declined, or
    the server did not come up within _STARTUP_WAIT seconds.
    """
    if not _ensure_executable():
        return False

    try:
        answer = input("   Start it now with ./chromadb-docker.sh start? [y/N] ").strip().lower()
    except EOFError:
        answer = ""  # Non-interactive environment (piped input, CI, etc.)

    if answer != "y":
        return False

    script = _DOCKER_SCRIPT.resolve()
    print(f"\n   Running: {script} start")
    result = subprocess.run([str(script), "start"], check=False)
    if result.returncode != 0:
        print(f"\n❌ '{script} start' exited with code {result.returncode}.")
        return False

    print(f"\n   Waiting up to {_STARTUP_WAIT}s for server to be ready...")
    for _ in range(_STARTUP_WAIT):
        time.sleep(1)
        if heartbeat():
            return True

    return False


def connect() -> None:
    print("=" * 60)
    print("Connecting to ChromaDB Docker Server...")
    print("=" * 60)
    if heartbeat():
        print(f"✅ Connected to ChromaDB at {HOST}:{PORT}\n")
        return

    print(f"❌ Cannot connect to ChromaDB at {HOST}:{PORT}")
    if _offer_to_start():
        print(f"✅ Connected to ChromaDB at {HOST}:{PORT}\n")
        return

    script = _DOCKER_SCRIPT.resolve()
    print(f"\n❌ ChromaDB is still not reachable at {HOST}:{PORT}.")
    print(f"   Run manually: {script} start\n")
    sys.exit(1)


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_basic_operations() -> bool:
    print("=" * 60)
    print("Test 1: Basic Operations")
    print("=" * 60)
    try:
        cid = get_or_create_collection("test_collection")
        print("✅ Created collection: test_collection")

        add_documents(
            cid,
            documents=["Hello world", "Goodbye world"],
            ids=["id1", "id2"],
            metadatas=[{"source": "test"}, {"source": "test"}],
        )
        print("✅ Added 2 documents")

        results = query_collection(cid, query_texts=["hello"], n_results=1)
        print(f"✅ Query result: '{results['documents'][0][0]}'")

        delete_collection("test_collection")
        print("✅ Cleaned up\n✅ Basic test PASSED!\n")
        return True
    except Exception as e:
        print(f"\n❌ Basic test FAILED: {e}\n")
        return False


def test_persistent_storage() -> bool:
    print("=" * 60)
    print("Test 2: Persistent Storage")
    print("=" * 60)
    try:
        cid = get_or_create_collection("persistent_test")

        add_documents(cid,
                      documents=["Data persists on the Docker server"],
                      ids=["persist1"])
        print("✅ Added document")

        result = get_documents(cid, ids=["persist1"])
        print(f"✅ Retrieved: '{result['documents'][0]}'")

        delete_collection("persistent_test")
        print("✅ Cleaned up\n✅ Persistent storage test PASSED!\n")
        return True
    except Exception as e:
        print(f"\n❌ Persistent storage test FAILED: {e}\n")
        return False


def create_sample_database() -> bool:
    print("=" * 60)
    print("Creating Sample Database")
    print("=" * 60)
    try:
        cid = get_or_create_collection(
            "programming_concepts",
            metadata={"description": "Computer science and programming concepts"},
        )

        documents = [
            "Object-oriented programming uses classes and objects to organize code",
            "Functional programming treats computation as mathematical functions",
            "Data structures organize and store data efficiently",
            "Algorithms are step-by-step procedures for solving problems",
            "Database systems store and retrieve structured data",
            "Machine learning enables computers to learn from data",
            "Version control systems track changes in source code",
            "APIs allow different software systems to communicate",
        ]
        metadatas = [
            {"topic": "OOP",             "difficulty": "intermediate"},
            {"topic": "FP",              "difficulty": "intermediate"},
            {"topic": "Data Structures", "difficulty": "beginner"},
            {"topic": "Algorithms",      "difficulty": "beginner"},
            {"topic": "Databases",       "difficulty": "intermediate"},
            {"topic": "ML",              "difficulty": "advanced"},
            {"topic": "Git",             "difficulty": "beginner"},
            {"topic": "APIs",            "difficulty": "intermediate"},
        ]

        add_documents(cid, documents=documents,
                      ids=[f"concept_{i}" for i, _ in enumerate(documents)],
                      metadatas=metadatas)
        print(f"✅ Added {len(documents)} programming concepts")

        results = query_collection(cid, query_texts=["How do computers learn?"], n_results=2)
        print("\n📊 Sample query: 'How do computers learn?'")
        print(f"   Result 1: {results['documents'][0][0]}")
        print(f"   Result 2: {results['documents'][0][1]}")
        print(f"\n✅ Collection 'programming_concepts' is live on the server")
        print("   Note: using dummy embeddings — swap in a real model for semantic search\n")
        return True
    except Exception as e:
        print(f"\n❌ Sample database creation FAILED: {e}\n")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n" + "=" * 60)
    print("ChromaDB Quick Start (Docker / HTTP Mode)")
    print("=" * 60 + "\n")

    connect()

    tests = [test_basic_operations, test_persistent_storage]
    results = [t() for t in tests]
    passed = sum(results)
    failed = len(results) - passed

    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"✅ Passed:  {passed}")
    print(f"❌ Failed:  {failed}\n")

    if failed == 0:
        create_sample_database()
        print("=" * 60)
        print("Next Steps")
        print("=" * 60)
        print("  Data lives in the Docker container (./chroma_data)")
        print("  Connect from any script:")
        print(f"    BASE = '{BASE}'")
        print("  For real semantic search, generate embeddings with a model")
        print("  and pass them to add_documents() / query_collection().")
        print("  Start building! 🚀\n")
        return 0

    print("⚠️  Some tests failed. Check errors above.\n")
    return 1


if __name__ == "__main__":
    main()
    