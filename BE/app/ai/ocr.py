"""OCR for scanned PDFs and images.

Default engine is RapidOCR (open-source PP-OCR models on ONNX Runtime, no system binaries).
Set OCR_ENGINE=gemini to transcribe pages with Gemini's vision model instead.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading

import numpy as np
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine = None
_lock = threading.Lock()


def _rapid_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from rapidocr import LangRec, RapidOCR

                _engine = RapidOCR(params={"Rec.lang_type": LangRec.EN, "Global.log_level": "warning"})
    return _engine


def _group_lines(result) -> str:
    """RapidOCR returns text boxes; merge boxes that share a baseline into reading-order lines."""
    boxes = []
    for box, text, score in zip(result.boxes, result.txts, result.scores, strict=False):
        if not text or float(score) < 0.5:
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        boxes.append((min(ys), max(ys), min(xs), text))
    boxes.sort(key=lambda b: (b[0], b[2]))

    lines: list[list[tuple]] = []
    for top, bottom, left, text in boxes:
        center = (top + bottom) / 2
        if lines:
            last = lines[-1]
            last_top = min(b[0] for b in last)
            last_bottom = max(b[1] for b in last)
            if last_top <= center <= last_bottom:
                last.append((top, bottom, left, text))
                continue
        lines.append([(top, bottom, left, text)])
    return "\n".join(" ".join(b[3] for b in sorted(line, key=lambda b: b[2])) for line in lines)


def ocr_image_sync(image: Image.Image) -> str:
    """Run local OCR on a PIL image. Blocking: call from a worker thread."""
    rgb = image.convert("RGB")
    result = _rapid_engine()(np.asarray(rgb))
    return _group_lines(result) if result.txts else ""


async def ocr_image(image: Image.Image) -> str:
    if settings.ocr_engine == "gemini":
        from app.ai.llm import transcribe_image

        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return await transcribe_image(buffer.getvalue())
    return await asyncio.to_thread(ocr_image_sync, image)
