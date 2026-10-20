"""Text normalisation applied before chunking."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.ingestion.extractors import TextBlock

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_SPACE = re.compile(r"[ \t ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_DIGITS = re.compile(r"\d+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = "\n".join(_MULTI_SPACE.sub(" ", line).strip() for line in text.split("\n"))
    return _MULTI_NEWLINE.sub("\n\n", text).strip()


def _line_signature(line: str) -> str:
    return _DIGITS.sub("#", line.strip().lower())


def strip_repeated_page_furniture(blocks: list[TextBlock], min_pages: int = 4, ratio: float = 0.6) -> list[TextBlock]:
    """Drop headers/footers (e.g. 'Confidential - Page 3 of 40') that repeat on most pages."""
    pages = {block.page for block in blocks if block.page is not None}
    if len(pages) < min_pages:
        return blocks

    counts: Counter[str] = Counter()
    for page in pages:
        page_lines = {
            _line_signature(line)
            for block in blocks
            if block.page == page
            for line in (block.text.split("\n")[:2] + block.text.split("\n")[-2:])
            if 0 < len(line.strip()) <= 120
        }
        counts.update(page_lines)

    threshold = max(min_pages, int(len(pages) * ratio))
    furniture = {signature for signature, count in counts.items() if count >= threshold}
    if not furniture:
        return blocks

    cleaned = []
    for block in blocks:
        lines = [line for line in block.text.split("\n") if _line_signature(line) not in furniture]
        text = "\n".join(lines).strip()
        if text:
            cleaned.append(TextBlock(text, page=block.page, section=block.section, is_ocr=block.is_ocr, is_heading=block.is_heading))
    return cleaned


def clean_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    normalised = []
    for block in blocks:
        text = normalize_text(block.text)
        if text:
            normalised.append(
                TextBlock(text, page=block.page, section=block.section, is_ocr=block.is_ocr, is_heading=block.is_heading)
            )
    return strip_repeated_page_furniture(normalised)
