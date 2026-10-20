from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ingestion.parsers import ParsedBlock, ParsedDocument


@dataclass(slots=True)
class IngestionChunk:
    index: int
    text: str
    start_char: int
    end_char: int
    metadata: dict[str, Any] = field(default_factory=dict)


BOUNDARY_MARKERS = ("\n\n", "\n", ". ", "? ", "! ", "; ", ": ", ", ", " ")
MIN_BOUNDARY_RATIO = 0.6
PARSED_SOFT_OVERFLOW_CHARS = 120
MIN_PREFERRED_PARSED_CHUNK_CHARS = 160


def _choose_chunk_end(text: str, start: int, raw_end: int, chunk_size: int) -> int:
    if raw_end >= len(text):
        return len(text)

    min_end = min(len(text), start + max(int(chunk_size * MIN_BOUNDARY_RATIO), 1))
    if min_end >= raw_end:
        return raw_end

    search_window = text[min_end:raw_end]

    for marker in BOUNDARY_MARKERS:
        marker_index = search_window.rfind(marker)
        if marker_index != -1:
            return min_end + marker_index + len(marker)

    return raw_end


def _adjust_chunk_start(text: str, proposed_start: int) -> int:
    if proposed_start <= 0 or proposed_start >= len(text):
        return proposed_start

    start = proposed_start

    while start < len(text) and text[start].isspace():
        start += 1

    if start > 0 and start < len(text) and text[start - 1].isalnum() and text[start].isalnum():
        while start < len(text) and text[start].isalnum():
            start += 1
        while start < len(text) and text[start].isspace():
            start += 1

    return min(start, len(text))


def split_text_into_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[IngestionChunk]:
    chunks: list[IngestionChunk] = []
    start = 0
    chunk_index = 0

    while start < len(text):
        raw_end = min(start + chunk_size, len(text))
        end = _choose_chunk_end(text=text, start=start, raw_end=raw_end, chunk_size=chunk_size)
        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                IngestionChunk(
                    index=chunk_index,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                )
            )
            chunk_index += 1

        if end >= len(text):
            break

        next_start = max(end - chunk_overlap, start + 1)
        start = _adjust_chunk_start(text=text, proposed_start=next_start)

    return chunks


def split_parsed_document_into_chunks(
    parsed_document: ParsedDocument,
    chunk_size: int,
) -> list[IngestionChunk]:
    chunks: list[IngestionChunk] = []
    current_blocks: list[ParsedBlock] = []
    chunk_index = 0
    current_start = 0
    cursor = 0
    active_heading_path: list[str] = []

    def current_text() -> str:
        return "\n\n".join(block.text for block in current_blocks if block.text).strip()

    def current_has_content() -> bool:
        return any(block.kind != "heading" for block in current_blocks)

    def make_heading_context_blocks() -> list[ParsedBlock]:
        if not active_heading_path:
            return []
        return [
            ParsedBlock(kind="heading", text=heading, heading_path=active_heading_path[: index + 1])
            for index, heading in enumerate(active_heading_path)
        ]

    def flush_chunk() -> None:
        nonlocal chunk_index, current_blocks, current_start
        chunk_text = current_text()
        if not chunk_text:
            current_blocks = []
            current_start = cursor
            return

        chunks.append(
            IngestionChunk(
                index=chunk_index,
                text=chunk_text,
                start_char=current_start,
                end_char=current_start + len(chunk_text),
                metadata=_build_parsed_chunk_metadata(parsed_document, current_blocks),
            )
        )
        chunk_index += 1
        current_blocks = []
        current_start = cursor

    for block in parsed_document.blocks:
        block_text = block.text.strip()
        if not block_text:
            continue

        if block.kind == "heading":
            active_heading_path = list(block.heading_path or [block_text])
            if current_has_content():
                flush_chunk()
            current_blocks = make_heading_context_blocks()
            current_start = cursor
            cursor = current_start + len(current_text())
            continue

        if not current_blocks:
            current_blocks = make_heading_context_blocks()
            current_start = cursor

        candidate_blocks = current_blocks + [block]
        candidate_text = "\n\n".join(item.text for item in candidate_blocks if item.text).strip()
        soft_chunk_limit = chunk_size + PARSED_SOFT_OVERFLOW_CHARS

        if current_has_content() and len(candidate_text) > soft_chunk_limit:
            flush_chunk()
            current_blocks = make_heading_context_blocks()
            current_start = cursor
            candidate_blocks = current_blocks + [block]
            candidate_text = "\n\n".join(item.text for item in candidate_blocks if item.text).strip()

        if len(candidate_text) <= soft_chunk_limit:
            current_blocks = candidate_blocks
            cursor = current_start + len(candidate_text)
            continue

        split_blocks = _split_large_block(
            block=block,
            heading_context=make_heading_context_blocks(),
            chunk_size=chunk_size,
            start_offset=cursor,
            parsed_document=parsed_document,
            start_index=chunk_index,
        )
        chunks.extend(split_blocks)
        chunk_index += len(split_blocks)
        current_blocks = []
        current_start = split_blocks[-1].end_char if split_blocks else cursor
        cursor = current_start

    if current_blocks:
        flush_chunk()

    return _coalesce_small_parsed_chunks(chunks, chunk_size=chunk_size)


def _split_large_block(
    *,
    block: ParsedBlock,
    heading_context: list[ParsedBlock],
    chunk_size: int,
    start_offset: int,
    parsed_document: ParsedDocument,
    start_index: int,
) -> list[IngestionChunk]:
    context_text = "\n\n".join(item.text for item in heading_context if item.text).strip()
    available_size = max(chunk_size - len(context_text) - (2 if context_text else 0), 200)
    sub_chunks = split_text_into_chunks(block.text, chunk_size=available_size, chunk_overlap=0)

    chunks: list[IngestionChunk] = []
    cursor = start_offset

    for relative_index, sub_chunk in enumerate(sub_chunks):
        all_blocks = heading_context + [
            ParsedBlock(
                kind=block.kind,
                text=sub_chunk.text,
                heading_path=list(block.heading_path),
                page_number=block.page_number,
                table_id=block.table_id,
                row_index=block.row_index,
            )
        ]
        chunk_text = "\n\n".join(item.text for item in all_blocks if item.text).strip()
        chunks.append(
            IngestionChunk(
                index=start_index + relative_index,
                text=chunk_text,
                start_char=cursor,
                end_char=cursor + len(chunk_text),
                metadata=_build_parsed_chunk_metadata(parsed_document, all_blocks),
            )
        )
        cursor += len(chunk_text)

    return chunks


def _build_parsed_chunk_metadata(
    parsed_document: ParsedDocument,
    blocks: list[ParsedBlock],
) -> dict[str, Any]:
    block_kinds = list(dict.fromkeys(block.kind for block in blocks if block.kind))
    heading_path: list[str] = []
    page_numbers = [block.page_number for block in blocks if block.page_number is not None]
    table_rows = [block for block in blocks if block.kind == "table_row"]

    for block in reversed(blocks):
        if block.heading_path:
            heading_path = list(block.heading_path)
            break

    table_ids = {block.table_id for block in table_rows if block.table_id}
    row_indexes = [block.row_index for block in table_rows if block.row_index is not None]

    return {
        "source_format": parsed_document.source_format,
        "parser_name": parsed_document.parser_name,
        "parser_mode": str(parsed_document.parse_metadata.get("parser_mode", "structured")),
        "heading_path": heading_path,
        "section_anchor": heading_path[-1] if heading_path else None,
        "line_kind": _derive_line_kind(block_kinds, table_rows),
        "page_start": min(page_numbers) if page_numbers else None,
        "page_end": max(page_numbers) if page_numbers else None,
        "table_like_row": bool(table_rows),
        "label_value_row": any(_looks_label_value_text(block.text) for block in blocks),
        "table_id": next(iter(table_ids)) if len(table_ids) == 1 else None,
        "row_index": row_indexes[0] if len(row_indexes) == 1 else None,
        "block_kinds": block_kinds,
        "sentence_offsets": _extract_sentence_offsets("\n\n".join(block.text for block in blocks if block.text).strip()),
    }


def _derive_line_kind(block_kinds: list[str], table_rows: list[ParsedBlock]) -> str:
    if table_rows:
        return "table_like"
    if block_kinds == ["list_item"]:
        return "list"
    if "heading" in block_kinds and len(block_kinds) == 1:
        return "heading"
    return "narrative"


def _extract_sentence_offsets(chunk_text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"(?<=[.!?])\s+", chunk_text):
        offsets.append(match.end())
    return sorted(set(offset for offset in offsets if offset < len(chunk_text)))


def _looks_label_value_text(text: str) -> bool:
    single_line = re.sub(r"\s+", " ", text).strip()
    if not single_line:
        return False
    if ":" in single_line:
        return True
    return bool(
        re.match(r"^[A-Za-z][A-Za-z0-9 /&()'-]{3,}\s+[$\d%][A-Za-z0-9 $%.,()-]*$", single_line)
    )


def _coalesce_small_parsed_chunks(chunks: list[IngestionChunk], *, chunk_size: int) -> list[IngestionChunk]:
    if not chunks:
        return []

    merged_chunks: list[IngestionChunk] = []
    index = 0
    max_merge_length = chunk_size + PARSED_SOFT_OVERFLOW_CHARS

    while index < len(chunks):
        current = chunks[index]
        if index + 1 < len(chunks) and _should_merge_small_chunk(current, chunks[index + 1], max_merge_length=max_merge_length):
            merged_chunks.append(_merge_ingestion_chunks(current, chunks[index + 1]))
            index += 2
            continue

        merged_chunks.append(current)
        index += 1

    for new_index, chunk in enumerate(merged_chunks):
        chunk.index = new_index

    return merged_chunks


def _should_merge_small_chunk(current: IngestionChunk, next_chunk: IngestionChunk, *, max_merge_length: int) -> bool:
    current_text = current.text.strip()
    next_text = next_chunk.text.strip()
    if not current_text or not next_text:
        return False

    current_line_kind = str(current.metadata.get("line_kind") or "")
    next_line_kind = str(next_chunk.metadata.get("line_kind") or "")
    current_section = current.metadata.get("section_anchor")
    next_section = next_chunk.metadata.get("section_anchor")
    same_section = bool(current_section and current_section == next_section)
    same_page = current.metadata.get("page_end") == next_chunk.metadata.get("page_start")

    combined_length = len(current_text) + 2 + len(next_text)
    if combined_length > max_merge_length:
        return False

    if len(current_text) >= MIN_PREFERRED_PARSED_CHUNK_CHARS and len(next_text) >= MIN_PREFERRED_PARSED_CHUNK_CHARS:
        return False

    if current_line_kind == "table_like" or next_line_kind == "table_like":
        current_table_id = current.metadata.get("table_id")
        next_table_id = next_chunk.metadata.get("table_id")
        same_table = bool(current_table_id and current_table_id == next_table_id)
        short_table_fragment = min(len(current_text), len(next_text)) <= 120
        return same_table or (short_table_fragment and same_section and same_page)

    return same_section or same_page


def _merge_ingestion_chunks(current: IngestionChunk, next_chunk: IngestionChunk) -> IngestionChunk:
    combined_text = f"{current.text.rstrip()}\n\n{next_chunk.text.lstrip()}".strip()
    current_block_kinds = list(current.metadata.get("block_kinds") or [])
    next_block_kinds = list(next_chunk.metadata.get("block_kinds") or [])
    merged_block_kinds = list(dict.fromkeys(current_block_kinds + next_block_kinds))

    current_heading_path = list(current.metadata.get("heading_path") or [])
    next_heading_path = list(next_chunk.metadata.get("heading_path") or [])

    current_sentence_offsets = list(current.metadata.get("sentence_offsets") or [])
    next_sentence_offsets = list(next_chunk.metadata.get("sentence_offsets") or [])
    offset_shift = len(current.text.rstrip()) + 2
    merged_sentence_offsets = sorted(
        set(current_sentence_offsets + [offset + offset_shift for offset in next_sentence_offsets])
    )

    return IngestionChunk(
        index=current.index,
        text=combined_text,
        start_char=current.start_char,
        end_char=current.start_char + len(combined_text),
        metadata={
            **current.metadata,
            "heading_path": current_heading_path or next_heading_path,
            "section_anchor": current.metadata.get("section_anchor") or next_chunk.metadata.get("section_anchor"),
            "line_kind": next_chunk.metadata.get("line_kind") or current.metadata.get("line_kind"),
            "page_start": current.metadata.get("page_start"),
            "page_end": next_chunk.metadata.get("page_end"),
            "table_like_row": bool(current.metadata.get("table_like_row") or next_chunk.metadata.get("table_like_row")),
            "label_value_row": bool(current.metadata.get("label_value_row") or next_chunk.metadata.get("label_value_row")),
            "table_id": current.metadata.get("table_id") or next_chunk.metadata.get("table_id"),
            "row_index": current.metadata.get("row_index"),
            "block_kinds": merged_block_kinds,
            "sentence_offsets": merged_sentence_offsets,
        },
    )
