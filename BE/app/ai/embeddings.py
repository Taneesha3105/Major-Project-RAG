"""Local open-source embeddings via Sentence-Transformers (default: BAAI/bge-small-en-v1.5)."""

from __future__ import annotations

import asyncio
import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def _load():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model %s", settings.embedding_model)
                model = SentenceTransformer(
                    settings.embedding_model,
                    device=settings.embedding_device,
                    cache_folder=str(settings.model_cache_path),
                )
                dimension = model.get_embedding_dimension()
                if dimension != settings.embedding_dimension:
                    raise RuntimeError(
                        f"Embedding model outputs {dimension} dimensions but EMBEDDING_DIMENSION="
                        f"{settings.embedding_dimension}. Update the setting and create a migration."
                    )
                _model = model
    return _model


def _encode(texts: list[str]) -> list[list[float]]:
    vectors = _load().encode(
        texts,
        batch_size=settings.embedding_batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()


async def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(_encode, texts)


async def embed_query(text: str) -> list[float]:
    vectors = await asyncio.to_thread(_encode, [f"{settings.embedding_query_prefix}{text}"])
    return vectors[0]


def warmup() -> None:
    _encode(["warm up"])


def is_loaded() -> bool:
    return _model is not None
