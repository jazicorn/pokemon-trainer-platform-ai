"""Document chunking for Chroma's 16 KiB per-document limit (ROADMAP.md Phase 9).

Every document ingested today (Pokemon stat blocks, Smogon strategy summaries — see
vector_store.py's _create_document_text and smogon_ingest.py) is well under this limit. This
exists defensively, for whatever longer content gets added later, not because current data
needs it.

Line-span splitting, not any of Chroma's own named strategies (recursive/structure-aware/
semantic splitting) — those need more document structure than this project's plain-text
documents have. Line spans are Chroma's own documented fallback when a smarter split still
produces an oversized piece: https://docs.trychroma.com/guides/build/chunking.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Chroma's own documented limit ("Chroma limits each record document size to 16KB").
MAX_DOCUMENT_BYTES = 16 * 1024


@dataclass
class DocumentChunk:
    """One chunk of a (possibly split) source document.

    `source_document_id` and `chunk_index` are what GroupBy dedup keys on at query time
    (vector_store.py's cloud query path) — collapsing multiple chunks of the same source
    document back down to its single best-scoring match.
    """

    text: str
    source_document_id: str
    chunk_index: int
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        """A stable, unique id for this chunk — source id and index, not content-derived."""
        return f"{self.source_document_id}::{self.chunk_index}"


def chunk_document(
    source_document_id: str,
    text: str,
    metadata: dict[str, str] | None = None,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> list[DocumentChunk]:
    """Split `text` into chunks no larger than `max_bytes` (measured as UTF-8 bytes, matching
    how Chroma itself measures the limit — a naive character count would undercount for any
    non-ASCII text).

    Returns a single chunk (chunk_index=0) when `text` already fits — the common case for this
    project's current documents. Only splits by line when it doesn't; a single line longer than
    `max_bytes` on its own is hard-split by character count as a last resort (rare — none of
    this project's current data has lines anywhere near this long).
    """
    base_metadata = metadata or {}

    if len(text.encode("utf-8")) <= max_bytes:
        return [
            DocumentChunk(
                text=text,
                source_document_id=source_document_id,
                chunk_index=0,
                metadata=dict(base_metadata),
            )
        ]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_bytes = 0

    def flush_current() -> None:
        if current_lines:
            chunks.append("\n".join(current_lines))

    for line in text.split("\n"):
        line_bytes = len(line.encode("utf-8")) + 1  # +1 for the joining newline

        if line_bytes > max_bytes:
            # A single line that alone exceeds the limit — hard-split by character count.
            # Rare: none of this project's current data has a line this long.
            flush_current()
            current_lines, current_bytes = [], 0
            chunks.extend(_hard_split(line, max_bytes))
            continue

        if current_bytes + line_bytes > max_bytes:
            flush_current()
            current_lines, current_bytes = [], 0

        current_lines.append(line)
        current_bytes += line_bytes

    flush_current()

    return [
        DocumentChunk(
            text=chunk_text,
            source_document_id=source_document_id,
            chunk_index=i,
            metadata=dict(base_metadata),
        )
        for i, chunk_text in enumerate(chunks)
    ]


def _hard_split(line: str, max_bytes: int) -> list[str]:
    """Split a single oversized line into UTF-8-safe pieces no larger than max_bytes.

    Encodes incrementally rather than slicing by character count directly, since a fixed
    character-count slice could land mid-multi-byte-character and produce invalid UTF-8.
    """
    pieces: list[str] = []
    current = ""
    current_bytes = 0

    for char in line:
        char_bytes = len(char.encode("utf-8"))
        if current_bytes + char_bytes > max_bytes and current:
            pieces.append(current)
            current, current_bytes = "", 0
        current += char
        current_bytes += char_bytes

    if current:
        pieces.append(current)

    return pieces
