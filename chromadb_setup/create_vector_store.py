"""
Vector Store Creator for Document Embeddings

This module creates a vector database from text documents using ChromaDB
server (via Docker) and embeddings from an HTTP API or local model.

Connects to ChromaDB server via httpx (no chromadb Python package needed).

Author: Enhanced version
Date: 2026-02-17
"""

import math
import sys
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class Document:
    """Represents a document with its metadata."""

    content: str
    filename: str
    filepath: str

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError(f"Document {self.filename} has empty content")


class DocumentLoader:
    """Handles loading documents from the filesystem."""

    SUPPORTED_EXTENSIONS = (".md", ".txt", ".rst")

    def __init__(self, docs_dir: str) -> None:
        """
        Initialize the document loader.

        Args:
            docs_dir: Path to the directory containing documents
        """
        self.docs_dir = Path(docs_dir)
        if not self.docs_dir.exists():
            raise FileNotFoundError(f"Directory not found: {docs_dir}")

    def load_documents(self) -> list[Document]:
        """
        Load all supported documents from the directory.

        Returns:
            List of Document objects
        """
        documents = []
        for filepath in self._find_documents():
            try:
                documents.append(self._load_single_document(filepath))
            except Exception as e:
                print(f"⚠️  Warning: Could not read {filepath.name}: {e}")
        return documents

    def _find_documents(self):
        """Generator that yields paths to supported documents."""
        for ext in self.SUPPORTED_EXTENSIONS:
            yield from self.docs_dir.rglob(f"*{ext}")

    def _load_single_document(self, filepath: Path) -> Document:
        """
        Load a single document from disk.

        Args:
            filepath: Path to the document file

        Returns:
            Document object
        """
        content = filepath.read_text(encoding="utf-8")
        return Document(content=content, filename=filepath.name, filepath=str(filepath))


class TextChunker:
    """Handles splitting text into overlapping chunks."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        """
        Initialize the text chunker.

        Args:
            chunk_size: Number of words per chunk
            overlap: Number of overlapping words between chunks
        """
        if chunk_size <= overlap:
            raise ValueError("chunk_size must be greater than overlap")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> list[str]:
        """
        Split text into overlapping chunks.

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        words = text.split()
        step = self.chunk_size - self.overlap
        return [
            chunk for i in range(0, len(words), step)
            if (chunk := " ".join(words[i:i + self.chunk_size])).strip()
        ]


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI embeddings via HTTP API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.api_key = api_key
        self.model = model
        self.dim = 1536  # text-embedding-3-small dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=30,
        )
        r.raise_for_status()
        # Sort by index to guarantee alignment with the input list
        return [item["embedding"] for item in sorted(r.json()["data"], key=lambda x: x["index"])]


class OllamaEmbeddings(EmbeddingProvider):
    """Ollama embeddings via local HTTP API."""

    def __init__(self, model: str = "nomic-embed-text", host: str = "localhost", port: int = 11434) -> None:
        self.model = model
        self.base_url = f"http://{host}:{port}"
        self.dim = 768  # nomic-embed-text dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Ollama.

        Note: the Ollama /api/embeddings endpoint accepts one text at a time,
        so requests are made sequentially.
        """
        def _embed_one(text: str) -> list[float]:
            r = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["embedding"]

        return [_embed_one(t) for t in texts]


class DummyEmbeddings(EmbeddingProvider):
    """Dummy embeddings for testing (not semantically meaningful)."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic hash-based embeddings."""
        return [self._dummy_embedding(t) for t in texts]

    def _dummy_embedding(self, text: str) -> list[float]:
        vec = [(hash(text + str(i)) & 0xFFFFFF) / 0xFFFFFF * 2 - 1 for i in range(self.dim)]
        magnitude = math.sqrt(sum(x * x for x in vec))
        return [x / magnitude for x in vec]


class VectorStoreManager:
    """Manages the ChromaDB vector store via HTTP."""

    _TENANT = "default_tenant"
    _DATABASE = "default_database"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        collection_name: str = "documents",
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        """
        Initialize the vector store manager.

        Args:
            host: ChromaDB server host
            port: ChromaDB server port
            collection_name: Name of the ChromaDB collection
            embedding_provider: EmbeddingProvider instance (defaults to DummyEmbeddings)
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self._base_url = f"http://{host}:{port}/api/v2/tenants/{self._TENANT}/databases/{self._DATABASE}"
        self._heartbeat_url = f"http://{host}:{port}/api/v2/heartbeat"
        self.collection_id: str | None = None
        self.embedding_provider = embedding_provider or DummyEmbeddings()

    def initialize(self, reset: bool = False) -> None:
        """
        Verify server connectivity and create or retrieve the collection.

        Args:
            reset: If True, delete the existing collection before creating a fresh one
        """
        print("🔧 Connecting to ChromaDB server...")
        try:
            httpx.get(self._heartbeat_url, timeout=5).raise_for_status()
            print(f"✅ Connected to ChromaDB at {self.host}:{self.port}")
        except httpx.HTTPError as e:
            print(f"❌ Cannot connect to ChromaDB server at {self.host}:{self.port}")
            print(f"   Error: {e}")
            print("\n💡 Make sure ChromaDB server is running:")
            print("   ./chromadb-docker.sh start")
            raise

        if reset:
            self._reset_collection()

        r = httpx.post(
            f"{self._base_url}/collections",
            json={
                "name": self.collection_name,
                "get_or_create": True,
                "metadata": {"description": "Document embeddings for semantic search"},
            },
            timeout=10,
        )
        r.raise_for_status()
        self.collection_id = r.json()["id"]
        print(f"✅ Collection ready: {self.collection_name}")

    def _reset_collection(self) -> None:
        """Delete the collection if it exists; silently ignore 404."""
        r = httpx.delete(f"{self._base_url}/collections/{self.collection_name}", timeout=10)
        if r.status_code == 404:
            return  # Nothing to delete
        r.raise_for_status()
        print(f"🗑️  Deleted existing collection: {self.collection_name}")

    def add_documents(
        self,
        documents: list[Document],
        chunker: TextChunker,
        batch_size: int = 100,
    ) -> int:
        """
        Chunk documents and add them to the vector store in batches.

        Chunks are streamed per-document rather than accumulated in memory,
        keeping peak memory proportional to batch_size rather than corpus size.

        Args:
            documents: List of Document objects to index
            chunker: TextChunker for splitting document text
            batch_size: Maximum number of chunks per HTTP request

        Returns:
            Total number of chunks stored
        """
        if not self.collection_id:
            raise RuntimeError("VectorStoreManager not initialized. Call initialize() first.")

        total_stored = 0
        chunk_id = 0
        buf_chunks: list[str] = []
        buf_meta: list[dict] = []
        buf_ids: list[str] = []

        def _flush() -> None:
            nonlocal total_stored
            if not buf_chunks:
                return
            batch_num = total_stored // batch_size + 1
            print(f"🔮 Creating embeddings for batch {batch_num} ({len(buf_chunks)} chunks)...")
            embeddings = self.embedding_provider.embed(buf_chunks)
            print("💾 Storing batch in vector database...")
            self._store_chunks(buf_chunks, embeddings, buf_meta, buf_ids)
            total_stored += len(buf_chunks)
            buf_chunks.clear()
            buf_meta.clear()
            buf_ids.clear()

        for doc in documents:
            print(f"📄 Processing: {doc.filename}")
            for chunk in chunker.chunk_text(doc.content):
                buf_chunks.append(chunk)
                buf_meta.append({"filename": doc.filename, "filepath": doc.filepath})
                buf_ids.append(f"chunk_{chunk_id}")
                chunk_id += 1
                if len(buf_chunks) >= batch_size:
                    _flush()

        _flush()  # Flush remaining chunks

        if total_stored == 0:
            print("⚠️  No chunks created! Check your documents.")
        else:
            print(f"✅ Successfully stored {total_stored} chunks in vector database")

        return total_stored

    def _store_chunks(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        ids: list[str],
    ) -> None:
        """POST a single batch of chunks to the ChromaDB /add endpoint."""
        httpx.post(
            f"{self._base_url}/collections/{self.collection_id}/add",
            json={"documents": chunks, "embeddings": embeddings, "metadatas": metadatas, "ids": ids},
            timeout=60,
        ).raise_for_status()

    def query(self, query_texts: list[str], n_results: int = 5) -> dict:
        """
        Query the collection by text.

        Embeddings are generated from query_texts using the configured provider.

        Args:
            query_texts: List of query strings
            n_results: Number of nearest neighbours to return

        Returns:
            Raw ChromaDB query response dict
        """
        if not self.collection_id:
            raise RuntimeError("VectorStoreManager not initialized. Call initialize() first.")
        embeddings = self.embedding_provider.embed(query_texts)
        r = httpx.post(
            f"{self._base_url}/collections/{self.collection_id}/query",
            json={"query_embeddings": embeddings, "n_results": n_results},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def delete_collection(self) -> None:
        """Delete this manager's collection from the server."""
        httpx.delete(
            f"{self._base_url}/collections/{self.collection_name}", timeout=10
        ).raise_for_status()

    def count(self) -> int:
        """Return the number of documents currently stored in the collection."""
        if not self.collection_id:
            raise RuntimeError("VectorStoreManager not initialized. Call initialize() first.")
        r = httpx.post(f"{self._base_url}/collections/{self.collection_id}/count", timeout=10)
        r.raise_for_status()
        return r.json()


def main() -> int:
    """Main execution function."""
    DOCS_DIR = "./knowledge_base"
    CHROMA_HOST = "localhost"
    CHROMA_PORT = 8000
    COLLECTION_NAME = "pokemon_docs"
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50

    # Choose embedding provider
    # Option 1: OpenAI (uncomment and set API key)
    # embedding_provider = OpenAIEmbeddings(api_key=os.environ["OPENAI_API_KEY"])

    # Option 2: Ollama (requires Ollama running locally)
    # embedding_provider = OllamaEmbeddings()

    # Option 3: Dummy (testing only — not semantically meaningful)
    embedding_provider = DummyEmbeddings()
    print("⚠️  Using dummy embeddings (testing only — not semantically meaningful)")
    print("   For real semantic search, use OpenAI or Ollama embeddings.\n")

    try:
        print("📚 Loading documents...\n")
        loader = DocumentLoader(DOCS_DIR)
        documents = loader.load_documents()
        print(f"\n✅ Found {len(documents)} documents\n")

        if not documents:
            print("❌ No documents found! Make sure documents exist in the knowledge_base directory.")
            return 1

        chunker = TextChunker(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        store_manager = VectorStoreManager(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            collection_name=COLLECTION_NAME,
            embedding_provider=embedding_provider,
        )
        store_manager.initialize(reset=True)
        num_chunks = store_manager.add_documents(documents, chunker)

        print(f"\n🎉 Processing complete! {num_chunks} chunks stored successfully.")
        print(f"\n📊 Collection '{COLLECTION_NAME}' is available on the ChromaDB server.")
        return 0

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
    