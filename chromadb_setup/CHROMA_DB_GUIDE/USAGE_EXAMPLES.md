# Usage Examples

Practical examples showing how to use ChromaDB for common tasks.

All examples connect to a ChromaDB Docker server using `httpx` directly —
no `chromadb` Python package required (it is incompatible with Python 3.14+).

Make sure your server is running before trying these examples:

```bash
./chromadb-docker.sh start
```

## Table of Contents

1. [Setup & Helpers](#setup--helpers)
2. [Basic Operations](#basic-operations)
3. [Embeddings](#embeddings)
4. [Semantic Search](#semantic-search)
5. [RAG Systems](#rag-systems)
6. [Advanced Queries](#advanced-queries)
7. [Production Patterns](#production-patterns)

---

## Setup & Helpers

Copy this block into any script as your foundation:

```python
import math
import httpx

HOST = "localhost"
PORT = 8000
TENANT = "default_tenant"
DATABASE = "default_database"
BASE = f"http://{HOST}:{PORT}/api/v2/tenants/{TENANT}/databases/{DATABASE}"
BASE_URL = f"http://{HOST}:{PORT}"


def heartbeat() -> bool:
    """Returns True if the ChromaDB server is reachable, False otherwise."""
    try:
        httpx.get(f"{BASE_URL}/api/v2/heartbeat", timeout=5).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def get_or_create_collection(name: str, metadata: dict | None = None) -> str:
    """Create or retrieve a collection; returns its ID."""
    body: dict = {"name": name, "get_or_create": True}
    if metadata:
        body["metadata"] = metadata
    r = httpx.post(f"{BASE}/collections", json=body, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def delete_collection(name: str) -> None:
    """Delete a collection by name (not ID)."""
    httpx.delete(f"{BASE}/collections/{name}", timeout=10).raise_for_status()


def add_documents(
    collection_id: str,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict] | None = None,
) -> None:
    """Add documents with pre-computed embeddings (required by v2 API)."""
    body: dict = {"ids": ids, "documents": documents, "embeddings": embeddings}
    if metadatas:
        body["metadatas"] = metadatas
    httpx.post(f"{BASE}/collections/{collection_id}/add", json=body, timeout=30).raise_for_status()


def upsert_documents(
    collection_id: str,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict] | None = None,
) -> None:
    """Add or update documents in a collection."""
    body: dict = {"ids": ids, "documents": documents, "embeddings": embeddings}
    if metadatas:
        body["metadatas"] = metadatas
    httpx.post(f"{BASE}/collections/{collection_id}/upsert", json=body, timeout=30).raise_for_status()


def query(
    collection_id: str,
    query_embeddings: list[list[float]],
    n_results: int = 5,
    where: dict | None = None,
) -> dict:
    """Run a nearest-neighbour query against a collection."""
    body: dict = {"query_embeddings": query_embeddings, "n_results": n_results}
    if where:
        body["where"] = where
    r = httpx.post(f"{BASE}/collections/{collection_id}/query", json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def get_by_ids(collection_id: str, ids: list[str]) -> dict:
    """Fetch specific documents by their IDs."""
    r = httpx.post(f"{BASE}/collections/{collection_id}/get", json={"ids": ids}, timeout=10)
    r.raise_for_status()
    return r.json()
```

---

## Basic Operations

### Connecting and Verifying

```python
assert heartbeat(), "ChromaDB server is not running — run ./chromadb-docker.sh start"
print("✅ Connected to ChromaDB")
```

### Creating and Listing Collections

```python
# Create (safe — won't error if it already exists)
cid = get_or_create_collection("documents", metadata={"description": "My docs"})
print(f"Collection ID: {cid}")

# List all collections
r = httpx.get(f"{BASE}/collections")
for c in r.json():
    print(c["name"], c["id"])
```

### Adding Documents

```python
from embeddings import embed   # see Embeddings section below

docs = [
    "Python is a programming language",
    "JavaScript is used for web development",
    "SQL is for database queries",
]
cid = get_or_create_collection("tutorials")

add_documents(
    cid,
    ids=["doc1", "doc2", "doc3"],
    documents=docs,
    embeddings=embed(docs),
    metadatas=[
        {"topic": "python",     "level": "beginner"},
        {"topic": "javascript", "level": "beginner"},
        {"topic": "sql",        "level": "intermediate"},
    ],
)
```

### Retrieving and Deleting

```python
# Fetch by ID
result = get_by_ids(cid, ["doc1", "doc2"])
print(result["documents"])

# Upsert (add or update)
upsert_documents(
    cid,
    ids=["doc1"],
    documents=["Python is a great programming language"],
    embeddings=embed(["Python is a great programming language"]),
)

# Delete collection
delete_collection("tutorials")
```

---

## Embeddings

The ChromaDB v2 API requires embeddings on every `add` and `query` call.
Choose one of these approaches based on your setup.

### Option 1: OpenAI Embeddings (Recommended — Pure HTTP, No Local Deps)

```python
import os
import httpx

OPENAI_KEY = os.environ["OPENAI_API_KEY"]


def embed(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    r = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {OPENAI_KEY}"},
        json={"model": model, "input": texts},
        timeout=30,
    )
    r.raise_for_status()
    # API returns items sorted by index, preserving input order
    return [item["embedding"] for item in sorted(r.json()["data"], key=lambda x: x["index"])]


# Usage
embeddings = embed(["Hello world", "Goodbye world"])
# Returns list of 1536-dimensional vectors (for text-embedding-3-small)
```

### Option 2: Ollama (Local Model, Pure HTTP)

```python
import httpx


def embed(texts: list[str], model: str = "nomic-embed-text") -> list[list[float]]:
    """Embed texts via a locally running Ollama server (https://ollama.com).

    Note: the Ollama /api/embeddings endpoint accepts one text at a time,
    so requests are made sequentially.
    """
    def _embed_one(text: str) -> list[float]:
        r = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["embedding"]

    return [_embed_one(t) for t in texts]
```

### Option 3: Dummy Embeddings (Testing Only)

Not semantically meaningful — similarity search results will be random.
Use only to verify your API calls work end-to-end.

```python
import math

EMBEDDING_DIM = 384


def dummy_embedding(text: str) -> list[float]:
    """Produce a deterministic unit-vector for `text` (not semantically meaningful)."""
    vec = [(hash(text + str(i)) & 0xFFFFFF) / 0xFFFFFF * 2 - 1 for i in range(EMBEDDING_DIM)]
    magnitude = math.sqrt(sum(x * x for x in vec))
    return [x / magnitude for x in vec]


def embed(texts: list[str]) -> list[list[float]]:
    return [dummy_embedding(t) for t in texts]
```

---

## Semantic Search

### Document Search System

```python
import httpx

# Requires the helpers from Setup & Helpers and an embed() from Embeddings above.


class DocumentSearcher:
    """Semantic document search backed by a ChromaDB collection."""

    def __init__(self, collection_name: str = "documents") -> None:
        assert heartbeat(), "ChromaDB server not running"
        self.cid = get_or_create_collection(collection_name)

    def index(self, documents: list[str], metadatas: list[dict] | None = None) -> None:
        """Index documents, assigning sequential IDs from 0.

        Warning: calling index() more than once on the same collection will
        produce duplicate IDs (doc_0, doc_1, …). Use upsert_documents() or
        track IDs externally when updating an existing collection.
        """
        ids = [f"doc_{i}" for i in range(len(documents))]
        add_documents(self.cid, ids=ids, documents=documents,
                      embeddings=embed(documents), metadatas=metadatas)
        print(f"✅ Indexed {len(documents)} documents")

    def search(
        self,
        query_text: str,
        n_results: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        results = query(self.cid, query_embeddings=embed([query_text]),
                        n_results=n_results, where=filters)
        return [
            {"document": doc, "metadata": meta, "distance": dist}
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]


# Usage
searcher = DocumentSearcher()
searcher.index([
    "Machine learning is a subset of AI",
    "Deep learning uses neural networks",
    "Python is popular for data science",
    "JavaScript runs in web browsers",
])

for r in searcher.search("artificial intelligence", n_results=2):
    print(f"📄 {r['document']}")
    print(f"   Distance: {r['distance']:.3f}\n")
```

---

## RAG Systems

### Simple RAG Implementation

```python
# Requires the helpers and embed() defined above.


class SimpleRAG:
    """Retrieval-Augmented Generation system backed by ChromaDB."""

    def __init__(self, collection_name: str = "knowledge") -> None:
        assert heartbeat(), "ChromaDB server not running"
        self.cid = get_or_create_collection(collection_name)

    def add_knowledge(self, texts: list[str], sources: list[str] | None = None) -> None:
        ids = [f"kb_{i}" for i in range(len(texts))]
        metadatas = [{"source": s} for s in sources] if sources else None
        add_documents(self.cid, ids=ids, documents=texts,
                      embeddings=embed(texts), metadatas=metadatas)
        print(f"✅ Added {len(texts)} knowledge entries")

    def retrieve(self, question: str, n_results: int = 3) -> list[str]:
        results = query(self.cid, query_embeddings=embed([question]), n_results=n_results)
        return results["documents"][0]

    def ask(self, question: str, n_contexts: int = 3) -> dict:
        """Retrieve context and build an LLM-ready prompt.

        In production, pass the returned prompt to Claude, GPT, or another LLM.
        """
        contexts = self.retrieve(question, n_contexts)
        return {
            "question": question,
            "contexts": contexts,
            "prompt": self._build_prompt(question, contexts),
        }

    def _build_prompt(self, question: str, contexts: list[str]) -> str:
        context_text = "\n".join(f"- {c}" for c in contexts)
        return (
            "Answer the question based on the following context:\n\n"
            f"{context_text}\n\n"
            f"Question: {question}"
        )


# Usage
rag = SimpleRAG()
rag.add_knowledge(
    [
        "ChromaDB is an open-source vector database for AI applications.",
        "Vector databases store embeddings for semantic similarity search.",
        "RAG combines retrieval with generation for better AI responses.",
        "Docker runs ChromaDB in an isolated container environment.",
    ],
    sources=["docs"] * 4,
)

result = rag.ask("What is ChromaDB?")
print(f"Q: {result['question']}")
print("\nContext retrieved:")
for c in result["contexts"]:
    print(f"  - {c}")
print(f"\nPrompt for LLM:\n{result['prompt']}")
```

---

## Advanced Queries

### Filtering with Metadata

```python
cid = get_or_create_collection("tutorials")
docs = [
    "Python tutorial for beginners",
    "Advanced Python techniques",
    "JavaScript basics",
    "JavaScript frameworks",
]
metadatas = [
    {"language": "python",     "level": "beginner"},
    {"language": "python",     "level": "advanced"},
    {"language": "javascript", "level": "beginner"},
    {"language": "javascript", "level": "advanced"},
]
add_documents(cid, ids=["py1", "py2", "js1", "js2"],
              documents=docs, embeddings=embed(docs), metadatas=metadatas)

# Filter by a single field
results = query(cid, query_embeddings=embed(["programming tutorial"]),
                n_results=2, where={"language": "python"})

# Filter by multiple fields
results = query(cid, query_embeddings=embed(["learn programming"]),
                n_results=1,
                where={"$and": [{"language": "python"}, {"level": "beginner"}]})
```

### Listing All Collections

```python
r = httpx.get(f"{BASE}/collections")
for c in r.json():
    print(c["name"], "—", c["id"])
```

---

## Production Patterns

### Batch Processing

```python
def add_in_batches(collection_id: str, documents: list[str], batch_size: int = 500) -> None:
    """Add a large corpus of documents in fixed-size batches."""
    total = len(documents)
    for start in range(0, total, batch_size):
        batch = documents[start:start + batch_size]
        ids = [f"doc_{i}" for i in range(start, start + len(batch))]
        add_documents(collection_id, ids=ids, documents=batch, embeddings=embed(batch))
        print(f"  {min(start + batch_size, total)}/{total} documents added")


# Usage
large_doc_set = [f"Document {i}" for i in range(5000)]
cid = get_or_create_collection("large_collection")
add_in_batches(cid, large_doc_set, batch_size=500)
```

### Error Handling

```python
def safe_add(collection_id: str, doc_id: str, document: str) -> bool:
    try:
        add_documents(collection_id, ids=[doc_id], documents=[document],
                      embeddings=embed([document]))
        return True
    except httpx.HTTPStatusError as e:
        print(f"HTTP error adding {doc_id}: {e.response.status_code} {e.response.text}")
    except httpx.HTTPError as e:
        print(f"Network error adding {doc_id}: {e}")
    return False


def safe_query(collection_id: str, query_text: str, n_results: int = 5) -> dict | None:
    try:
        return query(collection_id, query_embeddings=embed([query_text]), n_results=n_results)
    except httpx.HTTPStatusError as e:
        print(f"Query failed: {e.response.status_code} {e.response.text}")
    except httpx.HTTPError as e:
        print(f"Network error during query: {e}")
    return None
```

### Connection Management with Context Manager

```python
from contextlib import contextmanager
from collections.abc import Generator
import httpx


@contextmanager
def chroma_client(host: str = HOST, port: int = PORT) -> Generator[str, None, None]:
    """Yield the API base URL after verifying the server is reachable."""
    base = f"http://{host}:{port}/api/v2/tenants/{TENANT}/databases/{DATABASE}"
    httpx.get(f"http://{host}:{port}/api/v2/heartbeat", timeout=5).raise_for_status()
    yield base


# Usage
with chroma_client() as base:
    r = httpx.get(f"{base}/collections")
    print(r.json())
```

### Retry Logic for Flaky Connections

```python
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], retries: int = 3, delay: float = 1.0) -> T:
    """Call `fn` up to `retries` times, sleeping `delay` seconds between attempts."""
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            print(f"Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise


# Usage
result = with_retry(lambda: query(cid, query_embeddings=embed(["hello"]), n_results=3))
```

---

## Next Steps

- 📖 [Server Setup Guide](CHROMADB_SERVER_GUIDE.md) — detailed API reference
- 🔧 [Troubleshooting](TROUBLESHOOTING.md) — common errors and fixes
- 🔌 Plug in real embeddings from OpenAI or Ollama for meaningful similarity search
- 🚀 Pass retrieved context to Claude or another LLM to complete your RAG pipeline

---

[Back to README](../README.md) | [Troubleshooting →](TROUBLESHOOTING.md)
