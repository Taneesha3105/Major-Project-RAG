from __future__ import annotations

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.retrieval.schemas import RetrievalMatch


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def flashrank_dependency_available() -> bool:
    try:
        __import__("flashrank")
    except Exception:
        return False
    return True


@dataclass(slots=True)
class RerankResult:
    matches: list[RetrievalMatch]
    rerank_ms: float
    candidate_count: int


class BaseChatReranker(ABC):
    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Return whether the reranker can be used for neural modes."""

    @property
    @abstractmethod
    def model_name(self) -> str | None:
        """Return the active model name when available."""

    @abstractmethod
    async def warmup(self) -> None:
        """Warm the reranker model if possible."""

    @abstractmethod
    async def rerank(self, question: str, matches: list[RetrievalMatch]) -> RerankResult:
        """Rerank the provided matches for the question."""


class NoopChatReranker(BaseChatReranker):
    @property
    def enabled(self) -> bool:
        return False

    @property
    def model_name(self) -> str | None:
        return None

    async def warmup(self) -> None:
        return None

    async def rerank(self, question: str, matches: list[RetrievalMatch]) -> RerankResult:
        return RerankResult(matches=list(matches), rerank_ms=0.0, candidate_count=len(matches))


class FlashRankChatReranker(BaseChatReranker):
    def __init__(self, *, model_name: str) -> None:
        self._configured_model_name = model_name
        self._ranker: Any | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return flashrank_dependency_available()

    @property
    def model_name(self) -> str | None:
        return self._configured_model_name if self.enabled else None

    async def warmup(self) -> None:
        if not self.enabled:
            logger.warning("FlashRank warmup skipped because the flashrank dependency is unavailable.")
            return
        await asyncio.to_thread(self._ensure_ranker)

    async def rerank(self, question: str, matches: list[RetrievalMatch]) -> RerankResult:
        if len(matches) <= 1:
            return RerankResult(matches=list(matches), rerank_ms=0.0, candidate_count=len(matches))

        start = time.perf_counter()
        reranked_matches = await asyncio.to_thread(self._rerank_sync, question, list(matches))
        rerank_ms = round((time.perf_counter() - start) * 1000, 2)
        return RerankResult(
            matches=reranked_matches,
            rerank_ms=rerank_ms,
            candidate_count=len(matches),
        )

    def _ensure_ranker(self) -> Any:
        if self._ranker is not None:
            return self._ranker
        if not self.enabled:
            raise RuntimeError("FlashRank dependency is not available.")

        with self._lock:
            if self._ranker is not None:
                return self._ranker

            from flashrank import Ranker

            self._ranker = Ranker(model_name=self._configured_model_name)
            return self._ranker

    def _rerank_sync(self, question: str, matches: list[RetrievalMatch]) -> list[RetrievalMatch]:
        ranker = self._ensure_ranker()

        from flashrank import RerankRequest

        passages = [
            {
                "id": str(match.chunk_id),
                "text": match.chunk_text,
                "meta": {
                    "chunk_id": match.chunk_id,
                },
            }
            for match in matches
        ]
        rerank_request = RerankRequest(query=question, passages=passages)
        ranked_passages = ranker.rerank(rerank_request)
        return self._order_matches_from_ranked_passages(matches, ranked_passages)

    @staticmethod
    def _order_matches_from_ranked_passages(
        matches: list[RetrievalMatch],
        ranked_passages: list[dict[str, Any]],
    ) -> list[RetrievalMatch]:
        original_positions = {match.chunk_id: index for index, match in enumerate(matches)}
        match_by_chunk_id = {match.chunk_id: match for match in matches}

        scored_ids: list[tuple[int, float | None]] = []
        seen_chunk_ids: set[int] = set()
        for ranked_index, passage in enumerate(ranked_passages):
            chunk_id = FlashRankChatReranker._extract_chunk_id(passage)
            if chunk_id is None or chunk_id not in match_by_chunk_id or chunk_id in seen_chunk_ids:
                continue

            score_value = passage.get("score")
            score = float(score_value) if isinstance(score_value, (int, float)) else None
            scored_ids.append((chunk_id, score))
            seen_chunk_ids.add(chunk_id)

        if not scored_ids:
            return matches

        if any(score is None for _, score in scored_ids):
            ordered_chunk_ids = [chunk_id for chunk_id, _ in scored_ids]
            reranked = [match_by_chunk_id[chunk_id] for chunk_id in ordered_chunk_ids]
            leftovers = [match for match in matches if match.chunk_id not in seen_chunk_ids]
            return reranked + leftovers

        score_map = {chunk_id: score for chunk_id, score in scored_ids}
        reranked = sorted(
            (match_by_chunk_id[chunk_id] for chunk_id in seen_chunk_ids),
            key=lambda match: (
                score_map.get(match.chunk_id, float("-inf")),
                -original_positions[match.chunk_id],
            ),
            reverse=True,
        )
        leftovers = [match for match in matches if match.chunk_id not in seen_chunk_ids]
        return reranked + leftovers

    @staticmethod
    def _extract_chunk_id(passage: dict[str, Any]) -> int | None:
        meta = passage.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("chunk_id"), int):
            return meta["chunk_id"]

        raw_id = passage.get("id")
        if isinstance(raw_id, int):
            return raw_id
        if isinstance(raw_id, str) and raw_id.isdigit():
            return int(raw_id)
        return None


def build_chat_reranker(*, enabled: bool, model_name: str) -> BaseChatReranker:
    if not enabled:
        return NoopChatReranker()
    return FlashRankChatReranker(model_name=model_name)
