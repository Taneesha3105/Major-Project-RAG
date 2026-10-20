"""Cross-encoder reranking with FlashRank (open-source, CPU-friendly ONNX models)."""

from __future__ import annotations

import asyncio
import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

_ranker = None
_lock = threading.Lock()
_unavailable = False


def _load():
    global _ranker, _unavailable
    if _ranker is None and not _unavailable:
        with _lock:
            if _ranker is None and not _unavailable:
                try:
                    from flashrank import Ranker

                    settings.model_cache_path.mkdir(parents=True, exist_ok=True)
                    _ranker = Ranker(model_name=settings.reranker_model, cache_dir=str(settings.model_cache_path))
                    logger.info("Loaded FlashRank model %s", settings.reranker_model)
                except Exception:  # noqa: BLE001 - reranking is an optimisation, never fatal
                    logger.exception("FlashRank unavailable; falling back to fused retrieval order.")
                    _unavailable = True
    return _ranker


def _rerank(query: str, passages: list[tuple[int, str]]) -> dict[int, float]:
    ranker = _load()
    if ranker is None:
        return {}
    from flashrank import RerankRequest

    request = RerankRequest(query=query, passages=[{"id": pid, "text": text} for pid, text in passages])
    return {int(item["id"]): float(item["score"]) for item in ranker.rerank(request)}


async def rerank(query: str, passages: list[tuple[int, str]]) -> dict[int, float]:
    """Return {passage_id: relevance score in [0, 1]}; empty dict when reranking is disabled."""
    if not settings.reranker_enabled or not passages:
        return {}
    return await asyncio.to_thread(_rerank, query, passages)


def warmup() -> None:
    if settings.reranker_enabled:
        _rerank("warm up", [(0, "warm up")])
