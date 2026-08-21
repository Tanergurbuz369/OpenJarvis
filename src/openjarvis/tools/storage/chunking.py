"""Document chunking with configurable size and overlap.

Splits text into fixed-size chunks (measured in whitespace-split tokens)
with a configurable overlap.  Paragraph boundaries are respected when they
fall within the chunk window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class ChunkConfig:
    """Parameters controlling the chunking strategy."""

    chunk_size: int = 512
    chunk_overlap: int = 64
    min_chunk_size: int = 50


@dataclass(slots=True)
class Chunk:
    """A single chunk produced by the chunking pipeline."""

    content: str
    source: str = ""
    offset: int = 0
    index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


def _count_tokens(text: str) -> int:
    """Approximate token count via whitespace split."""
    return len(text.split())


def chunk_text(
    text: str,
    *,
    source: str = "",
    config: Optional[ChunkConfig] = None,
) -> List[Chunk]:
    """Split *text* into chunks respecting paragraph boundaries.

    Parameters
    ----------
    text:
        The full document text.
    source:
        Originating filename or identifier.
    config:
        Chunking parameters (uses defaults if ``None``).

    Returns
    -------
    List of :class:`Chunk` objects, in order.
    """
    if not text or not text.strip():
        return []

    cfg = config or ChunkConfig()

    # Split into paragraphs (double newline)
    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    chunks: List[Chunk] = []
    current_tokens: List[str] = []
    current_offset = 0
    chunk_start_offset = 0

    for para in paragraphs:
        para_tokens = para.split()

        # Split an oversized paragraph directly.  Any sub-floor content that
        # precedes it must travel with the first window instead of being
        # discarded by the pre-flush (#754).
        if len(para_tokens) > cfg.chunk_size:
            window_tokens = para_tokens
            window_offset = current_offset

            if current_tokens:
                chunk_content = " ".join(current_tokens)
                if _count_tokens(chunk_content) >= cfg.min_chunk_size:
                    chunks.append(
                        Chunk(
                            content=chunk_content,
                            source=source,
                            offset=chunk_start_offset,
                            index=len(chunks),
                        )
                    )
                    if (
                        cfg.chunk_overlap > 0
                        and len(current_tokens) > cfg.chunk_overlap
                    ):
                        prefix = current_tokens[-cfg.chunk_overlap :]
                        window_tokens = [*prefix, *para_tokens]
                        window_offset = current_offset - len(prefix)
                else:
                    window_tokens = [*current_tokens, *para_tokens]
                    window_offset = chunk_start_offset
                current_tokens = []

            idx = 0
            while idx < len(window_tokens):
                window = window_tokens[idx : idx + cfg.chunk_size]
                chunk_content = " ".join(window)
                if _count_tokens(chunk_content) >= cfg.min_chunk_size:
                    chunks.append(
                        Chunk(
                            content=chunk_content,
                            source=source,
                            offset=window_offset + idx,
                            index=len(chunks),
                        )
                    )
                step = max(1, cfg.chunk_size - cfg.chunk_overlap)
                idx += step

            current_offset += len(para_tokens)
            chunk_start_offset = current_offset
            continue

        # If adding this paragraph would exceed chunk_size and we already
        # have content, flush the current chunk first.
        if current_tokens and len(current_tokens) + len(para_tokens) > cfg.chunk_size:
            chunk_content = " ".join(current_tokens)
            if _count_tokens(chunk_content) >= cfg.min_chunk_size:
                chunks.append(
                    Chunk(
                        content=chunk_content,
                        source=source,
                        offset=chunk_start_offset,
                        index=len(chunks),
                    )
                )
                # Keep the overlap tail for the next chunk.  If the buffered
                # content is below the floor, leave it intact so the next
                # paragraph can make it large enough to emit.
                if cfg.chunk_overlap > 0 and len(current_tokens) > cfg.chunk_overlap:
                    overlap = current_tokens[-cfg.chunk_overlap :]
                    current_tokens = list(overlap)
                else:
                    current_tokens = []
                chunk_start_offset = current_offset

        current_tokens.extend(para_tokens)
        current_offset += len(para_tokens)

    # Flush remaining tokens.
    #
    # ``min_chunk_size`` exists to discard tiny *trailing* fragments once a
    # document has already produced at least one chunk. It must NOT silently
    # drop an entire short document: indexing a folder of short notes would
    # otherwise report success while storing nothing (#502 follow-up). So if no
    # chunk has been emitted yet, keep the remaining content regardless of the
    # floor.
    if current_tokens:
        chunk_content = " ".join(current_tokens)
        if not chunks or _count_tokens(chunk_content) >= cfg.min_chunk_size:
            chunks.append(
                Chunk(
                    content=chunk_content,
                    source=source,
                    offset=chunk_start_offset,
                    index=len(chunks),
                )
            )

    return chunks


__all__ = ["Chunk", "ChunkConfig", "chunk_text"]
