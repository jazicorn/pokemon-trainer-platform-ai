"""Tests for document chunking (ROADMAP.md Phase 9)."""

from __future__ import annotations

from rag.chunking import MAX_DOCUMENT_BYTES, chunk_document


class TestChunkDocument:
    def test_short_document_is_a_single_chunk(self) -> None:
        chunks = chunk_document("doc-1", "Pokemon: Pikachu. Types: Electric.")

        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].source_document_id == "doc-1"
        assert chunks[0].chunk_id == "doc-1::0"

    def test_short_document_preserves_metadata(self) -> None:
        chunks = chunk_document("doc-1", "short text", metadata={"name": "Pikachu"})

        assert chunks[0].metadata == {"name": "Pikachu"}

    def test_oversized_document_is_split_into_multiple_chunks(self) -> None:
        # Each line is short, but there are enough of them to exceed the limit.
        line = "x" * 100
        text = "\n".join([line] * 300)  # ~30KB, well over the 16KB limit

        chunks = chunk_document("doc-1", text)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text.encode("utf-8")) <= MAX_DOCUMENT_BYTES

    def test_chunk_indices_are_sequential_and_source_id_is_shared(self) -> None:
        text = "\n".join(["x" * 100] * 300)

        chunks = chunk_document("doc-1", text)

        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        assert all(c.source_document_id == "doc-1" for c in chunks)

    def test_chunk_ids_are_unique(self) -> None:
        text = "\n".join(["x" * 100] * 300)

        chunks = chunk_document("doc-1", text)

        assert len({c.chunk_id for c in chunks}) == len(chunks)

    def test_reassembling_chunks_preserves_all_original_lines(self) -> None:
        lines = [f"line-{i}: {'x' * 100}" for i in range(300)]
        text = "\n".join(lines)

        chunks = chunk_document("doc-1", text)
        reassembled_lines = "\n".join(c.text for c in chunks).split("\n")

        assert reassembled_lines == lines

    def test_a_single_line_longer_than_the_limit_is_hard_split(self) -> None:
        text = "x" * (MAX_DOCUMENT_BYTES * 2)

        chunks = chunk_document("doc-1", text)

        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.text.encode("utf-8")) <= MAX_DOCUMENT_BYTES
        assert "".join(c.text for c in chunks) == text

    def test_hard_split_does_not_break_multibyte_characters(self) -> None:
        # Each "é" is 2 bytes in UTF-8 — a naive character-count slice at an odd boundary
        # would be fine here, but a naive *byte*-count slice could split mid-character.
        text = "é" * (MAX_DOCUMENT_BYTES)

        chunks = chunk_document("doc-1", text)

        for chunk in chunks:
            # Would raise UnicodeDecodeError if a multi-byte character got split.
            chunk.text.encode("utf-8").decode("utf-8")
        assert "".join(c.text for c in chunks) == text

    def test_custom_max_bytes_is_respected(self) -> None:
        text = "\n".join(["x" * 10] * 20)  # ~220 bytes

        chunks = chunk_document("doc-1", text, max_bytes=50)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text.encode("utf-8")) <= 50
