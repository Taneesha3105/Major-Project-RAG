"""Structure-aware chunking.

Paragraph boundaries are respected, long paragraphs are split on sentence boundaries, chunks never
cross a page (so citations point at one page), and consecutive chunks share a sentence-level overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.extractors import TextBlock

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z0-9(\"'])|\n+")


@dataclass
class Chunk:
    content: str
    page: int | None
    section: str | None
    is_ocr: bool


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in (s.strip() for s in _SENTENCE_SPLIT.split(text)):
        if not sentence:
            continue
        while len(sentence) > max_chars:  # no sentence boundary at all: hard wrap on whitespace
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return ""
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    tail = ""
    for sentence in reversed(sentences):
        candidate = f"{sentence.strip()} {tail}".strip()
        if len(candidate) > overlap:
            break
        tail = candidate
    return tail


def chunk_blocks(blocks: list[TextBlock], chunk_size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0
    page: int | None = None
    section: str | None = None
    is_ocr = False

    def flush(carry_overlap: bool) -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        content = "\n\n".join(buffer).strip()
        if content:
            chunks.append(Chunk(content=content, page=page, section=section, is_ocr=is_ocr))
        tail = _overlap_tail(content, overlap) if carry_overlap else ""
        buffer = [tail] if tail else []
        buffer_len = len(tail)

    for block in blocks:
        if buffer and block.page != page:
            flush(carry_overlap=False)
        if not buffer:
            page, section, is_ocr = block.page, block.section, block.is_ocr
        if block.is_heading:
            # Start a new chunk at headings so sections stay coherent.
            if buffer_len > chunk_size * 0.3:
                flush(carry_overlap=False)
                page, is_ocr = block.page, block.is_ocr
            section = block.section
        is_ocr = is_ocr or block.is_ocr

        # Leave room for the overlap carried into the next chunk.
        for piece in _split_long(block.text, max(chunk_size - overlap - 2, chunk_size // 2)):
            if buffer_len + len(piece) + 2 > chunk_size and buffer_len > 0:
                flush(carry_overlap=True)
                section = block.section or section
                if buffer_len + len(piece) + 2 > chunk_size:
                    buffer, buffer_len = [], 0
            buffer.append(piece)
            buffer_len += len(piece) + 2

    flush(carry_overlap=False)
    return [chunk for chunk in chunks if len(chunk.content) >= 20 or len(chunks) == 1]
