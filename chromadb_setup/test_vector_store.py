"""
Unit tests for the vector store creation module.

Demonstrates improved testability through class-based design.
Tests use Docker-based ChromaDB server.
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

from create_vector_store import (
    Document,
    DocumentLoader,
    TextChunker,
    VectorStoreManager,
)

_CHROMA_HOST = "localhost"
_CHROMA_PORT = 8000
_HEARTBEAT_URL = f"http://{_CHROMA_HOST}:{_CHROMA_PORT}/api/v2/heartbeat"


def check_chromadb_server() -> bool:
    """Return True if the ChromaDB server is reachable."""
    try:
        httpx.get(_HEARTBEAT_URL, timeout=3).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


CHROMADB_AVAILABLE = check_chromadb_server()
skip_if_no_server = pytest.mark.skipif(
    not CHROMADB_AVAILABLE,
    reason="ChromaDB server not running. Start with: ./chromadb-docker.sh start",
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_manager(collection_name: str) -> VectorStoreManager:
    return VectorStoreManager(host=_CHROMA_HOST, port=_CHROMA_PORT, collection_name=collection_name)


def _cleanup(manager: VectorStoreManager) -> None:
    """Best-effort collection cleanup — ignore errors so tests don't fail on teardown."""
    try:
        manager.delete_collection()
    except httpx.HTTPError:
        pass


# ─── Document ─────────────────────────────────────────────────────────────────

class TestDocument:
    """Tests for the Document dataclass."""

    def test_document_creation(self) -> None:
        doc = Document(content="Test content", filename="test.txt", filepath="/path/to/test.txt")
        assert doc.content == "Test content"
        assert doc.filename == "test.txt"
        assert doc.filepath == "/path/to/test.txt"

    def test_document_empty_content_raises_error(self) -> None:
        with pytest.raises(ValueError, match="empty content"):
            Document(content="", filename="test.txt", filepath="/path/to/test.txt")


# ─── DocumentLoader ───────────────────────────────────────────────────────────

class TestDocumentLoader:
    """Tests for the DocumentLoader class."""

    @pytest.fixture
    def temp_docs_dir(self) -> Generator[str, None, None]:
        """Create a temporary directory with test documents."""
        temp_dir = tempfile.mkdtemp()
        test_files = {
            "test1.md": "# Test Document 1\n\nThis is test content.",
            "test2.txt": "This is a plain text document.",
            "test3.rst": "Test RST Document\n==================",
            "ignored.pdf": "This should be ignored",
        }
        for filename, content in test_files.items():
            (Path(temp_dir) / filename).write_text(content)
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_loader_initialization(self, temp_docs_dir: str) -> None:
        assert DocumentLoader(temp_docs_dir).docs_dir.exists()

    def test_loader_invalid_directory_raises_error(self) -> None:
        with pytest.raises(FileNotFoundError):
            DocumentLoader("/nonexistent/directory")

    def test_load_documents(self, temp_docs_dir: str) -> None:
        documents = DocumentLoader(temp_docs_dir).load_documents()
        # Should load 3 documents (.md, .txt, .rst) but not .pdf
        assert len(documents) == 3
        for doc in documents:
            assert isinstance(doc, Document)
            assert doc.content
            assert doc.filename

    def test_load_documents_filters_extensions(self, temp_docs_dir: str) -> None:
        filenames = [doc.filename for doc in DocumentLoader(temp_docs_dir).load_documents()]
        assert any(f.endswith(".md") for f in filenames)
        assert any(f.endswith(".txt") for f in filenames)
        assert any(f.endswith(".rst") for f in filenames)
        assert not any(f.endswith(".pdf") for f in filenames)

    def test_find_documents_generator(self, temp_docs_dir: str) -> None:
        result = DocumentLoader(temp_docs_dir)._find_documents()  # pyright: ignore[reportPrivateUsage]
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")

    def test_load_single_document(self, temp_docs_dir: str) -> None:
        loader = DocumentLoader(temp_docs_dir)
        doc = loader._load_single_document(Path(temp_docs_dir) / "test1.md")  # pyright: ignore[reportPrivateUsage]
        assert isinstance(doc, Document)
        assert "Test Document 1" in doc.content
        assert doc.filename == "test1.md"


# ─── TextChunker ──────────────────────────────────────────────────────────────

class TestTextChunker:
    """Tests for the TextChunker class."""

    def test_chunker_initialization(self) -> None:
        chunker = TextChunker(chunk_size=100, overlap=10)
        assert chunker.chunk_size == 100
        assert chunker.overlap == 10

    def test_chunker_invalid_params_raises_error(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be greater than overlap"):
            TextChunker(chunk_size=10, overlap=20)

    def test_chunk_text_basic(self) -> None:
        chunks = TextChunker(chunk_size=5, overlap=2).chunk_text(
            "one two three four five six seven eight nine ten"
        )
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.strip()

    def test_chunk_text_overlap(self) -> None:
        chunks = TextChunker(chunk_size=3, overlap=1).chunk_text("A B C D E F")
        # First chunk: A B C; second starts at C (overlap=1)
        assert "A B C" in chunks[0]
        assert "C" in chunks[0] and "C" in chunks[1]

    def test_chunk_empty_text(self) -> None:
        assert TextChunker(chunk_size=10, overlap=2).chunk_text("") == []

    def test_chunk_single_word(self) -> None:
        assert TextChunker(chunk_size=10, overlap=2).chunk_text("word") == ["word"]

    def test_chunk_preserves_words(self) -> None:
        all_text = " ".join(TextChunker(chunk_size=3, overlap=1).chunk_text("hello world foo bar"))
        for word in ("hello", "world", "foo", "bar"):
            assert word in all_text


# ─── VectorStoreManager ───────────────────────────────────────────────────────

@skip_if_no_server
class TestVectorStoreManager:
    """Tests for the VectorStoreManager class."""

    def test_manager_initialization(self) -> None:
        manager = _make_manager("test_collection")
        assert manager.host == _CHROMA_HOST
        assert manager.port == _CHROMA_PORT
        assert manager.collection_name == "test_collection"
        assert manager.collection_id is None  # Not initialized yet

    def test_manager_initialize(self) -> None:
        manager = _make_manager("test_init_collection")
        try:
            manager.initialize(reset=False)
            assert manager.collection_id is not None
        finally:
            _cleanup(manager)

    def test_manager_connection_error(self) -> None:
        manager = VectorStoreManager(host=_CHROMA_HOST, port=9999, collection_name="test_collection")
        with pytest.raises(httpx.HTTPError):
            manager.initialize()

    def test_add_documents_not_initialized_raises_error(self) -> None:
        manager = _make_manager("test_collection")
        with pytest.raises(RuntimeError, match="not initialized"):
            manager.add_documents(
                [Document(content="Test content", filename="test.txt", filepath="/test.txt")],
                TextChunker(),
            )

    def test_add_documents_empty_list(self) -> None:
        manager = _make_manager("test_empty_collection")
        manager.initialize(reset=True)
        try:
            assert manager.add_documents([], TextChunker()) == 0
        finally:
            _cleanup(manager)

    @pytest.mark.slow
    def test_add_documents_integration(self) -> None:
        manager = _make_manager("test_integration_collection")
        manager.initialize(reset=True)
        try:
            documents = [
                Document(
                    content="This is a test document with some content for testing.",
                    filename="test1.txt",
                    filepath="/test1.txt",
                ),
                Document(
                    content="Another test document with different content.",
                    filename="test2.txt",
                    filepath="/test2.txt",
                ),
            ]
            num_chunks = manager.add_documents(documents, TextChunker(chunk_size=5, overlap=1))
            assert num_chunks > 0
            assert manager.count() == num_chunks
        finally:
            _cleanup(manager)


# ─── End-to-end ───────────────────────────────────────────────────────────────

@skip_if_no_server
class TestEndToEnd:
    """End-to-end integration tests."""

    @pytest.fixture
    def test_environment(self) -> Generator[dict[str, str], None, None]:
        docs_dir = tempfile.mkdtemp()
        test_docs = {
            "doc1.md": "# Machine Learning\n\nMachine learning is a subset of AI.",
            "doc2.txt": "Deep learning uses neural networks with multiple layers.",
            "doc3.md": "# Natural Language Processing\n\nNLP deals with text processing.",
        }
        for filename, content in test_docs.items():
            (Path(docs_dir) / filename).write_text(content)
        yield {"docs_dir": docs_dir}
        shutil.rmtree(docs_dir)

    @pytest.mark.slow
    def test_complete_pipeline(self, test_environment: dict[str, str]) -> None:
        docs_dir = test_environment["docs_dir"]

        documents = DocumentLoader(docs_dir).load_documents()
        assert len(documents) == 3

        manager = _make_manager("test_pipeline_collection")
        manager.initialize(reset=True)
        try:
            num_chunks = manager.add_documents(documents, TextChunker(chunk_size=10, overlap=2))
            assert num_chunks > 0

            results = manager.query(["What is machine learning?"], n_results=2)
            assert len(results["documents"]) > 0
            assert len(results["documents"][0]) > 0
        finally:
            _cleanup(manager)


# ─── Performance ──────────────────────────────────────────────────────────────

class TestPerformance:
    """Performance benchmarking tests."""

    @pytest.mark.benchmark
    def test_chunking_performance(self, benchmark: Any) -> None:
        chunker = TextChunker(chunk_size=100, overlap=10)
        text = " ".join(["word"] * 10000)
        assert len(benchmark(chunker.chunk_text, text)) > 0

    @pytest.mark.benchmark
    def test_document_loading_performance(self, benchmark: Any, tmp_path: Path) -> None:
        for i in range(100):
            (tmp_path / f"doc{i}.txt").write_text(f"Document {i} content")
        loader = DocumentLoader(str(tmp_path))
        assert len(benchmark(loader.load_documents)) == 100


# ─── Server availability smoke test ───────────────────────────────────────────

def test_chromadb_server_available() -> None:
    """Smoke test: verify the ChromaDB server responds to a heartbeat."""
    if not CHROMADB_AVAILABLE:
        pytest.skip("ChromaDB server not available")
    httpx.get(_HEARTBEAT_URL, timeout=5).raise_for_status()
    print(f"\n✅ ChromaDB server is running at {_HEARTBEAT_URL}")


if __name__ == "__main__":
    if CHROMADB_AVAILABLE:
        print("✅ ChromaDB server is available")
    else:
        print("❌ ChromaDB server is NOT available")
        print("   Start it with: ./chromadb-docker.sh start")
        print("   Tests requiring server will be skipped")
    pytest.main([__file__, "-v", "--tb=short"])