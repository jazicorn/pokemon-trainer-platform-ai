# Resources

Additional resources, links, and community information for ChromaDB.

> **Setup note:** This project uses `httpx` directly to talk to the ChromaDB
> Docker server. No `chromadb` or `chromadb-client` Python package is used —
> both are incompatible with Python 3.14+. Code examples in external resources
> that use `chromadb.HttpClient(...)` will need to be adapted to the `httpx`
> pattern documented in [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md).

## Official Resources

### Documentation

- **Main Documentation:** <https://docs.trychroma.com/>
- **API Reference:** <https://docs.trychroma.com/reference>
- **Getting Started:** <https://docs.trychroma.com/getting-started>
- **Deployment Guide:** <https://docs.trychroma.com/deployment>

### Code and Examples

- **GitHub Repository:** <https://github.com/chroma-core/chroma>
- **Examples:** <https://github.com/chroma-core/chroma/tree/main/examples>
- **Release Notes:** <https://github.com/chroma-core/chroma/releases>
- **Changelog:** <https://github.com/chroma-core/chroma/blob/main/CHANGELOG.md>

## Community

### Get Help

- **Discord:** [Join ChromaDB Discord](https://discord.gg/MMeYNTmh3x)
- **GitHub Discussions:** <https://github.com/chroma-core/chroma/discussions>
- **Issue Tracker:** <https://github.com/chroma-core/chroma/issues>
- **Stack Overflow:** Tag questions with `chromadb`
- **Twitter:** [@trychroma](https://twitter.com/trychroma)

### Contributing

- **Contributing Guide:** <https://github.com/chroma-core/chroma/blob/main/CONTRIBUTING.md>
- **Code of Conduct:** <https://github.com/chroma-core/chroma/blob/main/CODE_OF_CONDUCT.md>

## Learning Materials

### Blog Posts and Articles

- **ChromaDB Blog:** <https://www.trychroma.com/blog>
- **Pinecone Blog:** Vector search insights (concepts apply to ChromaDB too)
- **Papers with Code:** <https://paperswithcode.com/>

### Research Papers

- **HNSW Algorithm:** "Efficient and robust approximate nearest neighbor search"
- **Embeddings:** "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks"
- **RAG:** "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
- **arXiv.org:** <https://arxiv.org/>

## Embedding Options

Since the ChromaDB v2 API requires you to provide embeddings, you need an
embedding source. All of these work with Python 3.14+ via HTTP:

### OpenAI Embeddings (Recommended)

- **API Docs:** <https://platform.openai.com/docs/guides/embeddings>
- **Models:** `text-embedding-3-small` (1536-dim), `text-embedding-3-large`
- **Usage:** Pure HTTP call, no local Python package needed

```python
import os
import httpx


def embed(texts: list[str]) -> list[list[float]]:
    r = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": "text-embedding-3-small", "input": texts},
    )
    r.raise_for_status()
    # Sort by index to guarantee alignment with the input list
    return [item["embedding"] for item in sorted(r.json()["data"], key=lambda x: x["index"])]
```

### Cohere Embeddings

- **Documentation:** <https://cohere.com/embeddings>
- **Usage:** HTTP API, no local deps

### Ollama (Local, No Cloud Required)

- **Documentation:** <https://ollama.com>
- **Models:** `nomic-embed-text`, `mxbai-embed-large`
- **Usage:** HTTP API at `http://localhost:11434/api/embeddings`

```python
import httpx


def embed(texts: list[str], model: str = "nomic-embed-text") -> list[list[float]]:
    """Embed texts via a locally running Ollama server.

    Note: the Ollama /api/embeddings endpoint accepts one text at a time,
    so requests are made sequentially.
    """
    def _embed_one(text: str) -> list[float]:
        r = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": model, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]

    return [_embed_one(t) for t in texts]
```

### Voyage AI

- **Documentation:** <https://www.voyageai.com/>
- **Usage:** HTTP API

### SentenceTransformers ⚠️

- **Documentation:** <https://www.sbert.net/>
- **Warning:** Incompatible with Python 3.14+ due to scipy/sklearn deps.
  Use only if you are on Python ≤ 3.13.

## LLM Frameworks

These frameworks have ChromaDB integrations, but their examples typically use
`chromadb.HttpClient`. On Python 3.14+ you'll need to use the `httpx` pattern
and adapt accordingly, or run your Python code on 3.12/3.13.

### LangChain

- **Documentation:** <https://python.langchain.com/>
- **ChromaDB Integration:** <https://python.langchain.com/docs/integrations/vectorstores/chroma>

### LlamaIndex

- **Documentation:** <https://docs.llamaindex.ai/>
- **ChromaDB Integration:** <https://docs.llamaindex.ai/en/stable/examples/vector_stores/ChromaIndexDemo/>

### Haystack

- **Documentation:** <https://haystack.deepset.ai/>

## Tools

### Development

- **httpx:** <https://www.python-httpx.org/> — HTTP client used for all ChromaDB communication
- **uv:** <https://docs.astral.sh/uv/> — Fast Python package manager
- **Docker:** <https://docs.docker.com/> — Container runtime for ChromaDB server
- **Colima:** <https://github.com/abiosoft/colima> — Lightweight Docker runtime for macOS

### Testing

- **pytest:** Testing framework
- **mypy / basedpyright:** Type checking
- **ruff:** Linting and formatting

## Deployment Options

### Self-Hosted

- **Docker:** Current setup — containerized, easy to manage
- **Docker Compose:** Multi-service setup (see [Server Guide](CHROMADB_SERVER_GUIDE.md))
- **Kubernetes:** Orchestrated at scale

### Cloud Platforms

- **AWS:** EC2, ECS, App Runner
- **Google Cloud:** Compute Engine, Cloud Run
- **Azure:** Container Instances
- **DigitalOcean:** App Platform

### Managed Services

- **ChromaDB Cloud:** Official managed service — <https://www.trychroma.com/>

## Alternative Vector Databases

For comparison:

| Database       | Type            | Notes                                  |
|----------------|-----------------|----------------------------------------|
| **Pinecone**   | Managed         | <https://www.pinecone.io/>             |
| **Weaviate**   | Open source     | <https://weaviate.io/>                 |
| **Milvus**     | Open source     | <https://milvus.io/>                   |
| **Qdrant**     | Open source     | <https://qdrant.tech/>                 |
| **FAISS**      | Library (local) | <https://faiss.ai/>                    |
| **pgvector**   | Postgres ext    | <https://github.com/pgvector/pgvector> |

## Datasets for Practice

### Public Datasets

- **Wikipedia:** Text corpus for search
- **Stack Overflow:** Q&A dataset
- **GitHub Code:** Code search
- **ArXiv Papers:** Research papers

### Quick Test Data

```python
test_documents = [
    "Python is a programming language",
    "JavaScript is used for web development",
    "Machine learning is a subset of AI",
    "Deep learning uses neural networks",
    "SQL is for database queries",
]
```

## Quick Links Reference

| Resource                 | Link                                                 |
|--------------------------|------------------------------------------------------|
| **Official Docs**        | <https://docs.trychroma.com/>                        |
| **GitHub**               | <https://github.com/chroma-core/chroma>              |
| **Discord**              | <https://discord.gg/MMeYNTmh3x>                      |
| **OpenAI Embeddings**    | <https://platform.openai.com/docs/guides/embeddings> |
| **Ollama**               | <https://ollama.com>                                 |
| **httpx docs**           | <https://www.python-httpx.org/>                      |
| **Docker**               | <https://docs.docker.com/>                           |
| **Colima (macOS)**       | <https://github.com/abiosoft/colima>                 |

---

[Back to README](../README.md)
