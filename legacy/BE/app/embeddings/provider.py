from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import threading
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI
from httpx import ResponseNotRead

from app.core.config import settings

logger = logging.getLogger(__name__)
_SENTENCE_TRANSFORMER_MODEL_CACHE: dict[tuple[str, str], object] = {}
_SENTENCE_TRANSFORMER_MODEL_LOCK = threading.Lock()
_DEFAULT_ONNX_MODEL_FILENAME = "onnx/model.onnx"


class EmbeddingProviderError(Exception):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseEmbeddingProvider(ABC):
    provider_name: str
    model_name: str
    dimensions: int

    @property
    def display_name(self) -> str:
        if self.provider_name == "mock":
            return "mock"
        return f"{self.provider_name}:{self.model_name}"

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text."""

    @property
    def preferred_request_batch_size(self) -> int | None:
        return None

    async def warmup(self) -> None:
        """Load any expensive local state before the first real request."""


class LocalHashEmbeddingProvider(BaseEmbeddingProvider):
    """Simple deterministic embedding provider for local development."""

    token_pattern = re.compile(r"\b\w+\b", re.UNICODE)

    def __init__(self, vector_size: int) -> None:
        self.provider_name = "mock"
        self.model_name = "local-hash"
        self.dimensions = vector_size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self.token_pattern.findall(text.lower())

        if not tokens:
            tokens = list(text.strip().lower())

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()

            primary_index = int.from_bytes(digest[:4], "big") % self.dimensions
            secondary_index = int.from_bytes(digest[4:8], "big") % self.dimensions

            primary_sign = 1.0 if digest[8] % 2 == 0 else -1.0
            secondary_sign = 1.0 if digest[9] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 20) / 20.0

            vector[primary_index] += primary_sign * weight
            vector[secondary_index] += secondary_sign * (weight / 2.0)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector

        return [value / norm for value in vector]


class LocalSentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Local semantic embeddings using a SentenceTransformers model."""

    def __init__(
        self,
        *,
        model_name: str,
        dimensions: int,
        device: str,
        runtime: str,
        onnx_model_dir: str,
        onnx_intra_op_threads: int,
        onnx_inter_op_threads: int,
    ) -> None:
        self.provider_name = "local"
        self.model_name = model_name
        self.dimensions = dimensions
        self.device = device
        self.runtime = runtime
        self.onnx_model_dir = onnx_model_dir
        self.onnx_intra_op_threads = onnx_intra_op_threads
        self.onnx_inter_op_threads = onnx_inter_op_threads

    @property
    def display_name(self) -> str:
        if self.runtime == "sentence_transformers":
            return super().display_name
        return f"{self.provider_name}:{self.runtime}:{self.model_name}"

    @property
    def preferred_request_batch_size(self) -> int:
        return settings.local_embedding_batch_size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        normalized_texts = [text if text.strip() else " " for text in texts]
        return await asyncio.to_thread(self._encode_sync, normalized_texts)

    async def warmup(self) -> None:
        warmup_text = settings.local_embedding_warmup_text.strip() or " "
        logger.info(
            "Warming local embedding model %s on device %s.",
            self.model_name,
            self.device,
        )
        await asyncio.to_thread(self._encode_sync, [warmup_text])

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        model = _load_sentence_transformer_model(
            self.model_name,
            self.device,
            runtime=self.runtime,
            onnx_model_dir=self.onnx_model_dir,
            onnx_intra_op_threads=self.onnx_intra_op_threads,
            onnx_inter_op_threads=self.onnx_inter_op_threads,
        )
        model_dimensions = model.get_sentence_embedding_dimension()

        if model_dimensions != self.dimensions:
            raise EmbeddingProviderError(
                "The local embedding model output dimension does not match VECTOR_SIZE. "
                f"Model dimension: {model_dimensions}. VECTOR_SIZE: {self.dimensions}.",
                status_code=500,
            )

        embeddings = model.encode(
            texts,
            batch_size=settings.local_embedding_encode_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()


class _OnnxSentenceEmbeddingModel:
    """Small ONNX Runtime wrapper that matches the SentenceTransformer encode contract we use."""

    def __init__(
        self,
        *,
        model_name: str,
        model_path: Path,
        intra_op_threads: int,
        inter_op_threads: int,
    ) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
            from transformers import AutoConfig, AutoTokenizer
        except ImportError as exc:
            raise EmbeddingProviderError(
                "onnxruntime, numpy, and transformers are required for LOCAL_EMBEDDING_RUNTIME=onnx.",
                status_code=500,
            ) from exc

        session_options = _build_onnx_session_options(
            intra_op_threads=intra_op_threads,
            inter_op_threads=inter_op_threads,
        )
        session_kwargs: dict[str, Any] = {"providers": ["CPUExecutionProvider"]}
        if session_options is not None:
            session_kwargs["sess_options"] = session_options

        self._np = np
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._dimension = int(AutoConfig.from_pretrained(model_name).hidden_size)
        self._session = ort.InferenceSession(str(model_path), **session_kwargs)
        self._input_names = {model_input.name for model_input in self._session.get_inputs()}

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ):
        del show_progress_bar
        if not texts:
            empty_result = self._np.empty((0, self._dimension), dtype=self._np.float32)
            return empty_result if convert_to_numpy else empty_result.tolist()

        batches = []
        for batch_start in range(0, len(texts), batch_size):
            batch_texts = texts[batch_start : batch_start + batch_size]
            encoded_inputs = self._tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                return_tensors="np",
            )
            session_inputs = {
                name: value
                for name, value in encoded_inputs.items()
                if name in self._input_names
            }
            model_outputs = self._session.run(None, session_inputs)
            token_embeddings = model_outputs[0]
            embeddings = self._mean_pool(token_embeddings, encoded_inputs["attention_mask"])
            if normalize_embeddings:
                norms = self._np.linalg.norm(embeddings, axis=1, keepdims=True)
                embeddings = embeddings / self._np.clip(norms, a_min=1e-12, a_max=None)
            batches.append(embeddings.astype(self._np.float32))

        result = self._np.vstack(batches)
        return result if convert_to_numpy else result.tolist()

    def _mean_pool(self, token_embeddings, attention_mask):
        mask = attention_mask.astype(self._np.float32)
        masked_embeddings = token_embeddings * self._np.expand_dims(mask, axis=-1)
        token_sums = masked_embeddings.sum(axis=1)
        token_counts = self._np.clip(mask.sum(axis=1, keepdims=True), a_min=1e-12, a_max=None)
        return token_sums / token_counts


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider for better semantic retrieval quality."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        dimensions: int,
        base_url: str | None,
        timeout_seconds: float,
    ) -> None:
        self.provider_name = "openai"
        self.model_name = model_name
        self.dimensions = dimensions
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        normalized_texts = [text if text.strip() else " " for text in texts]
        request_kwargs: dict[str, object] = {
            "model": self.model_name,
            "input": normalized_texts,
        }

        if self.model_name.startswith("text-embedding-3"):
            request_kwargs["dimensions"] = self.dimensions

        try:
            response = await self.client.embeddings.create(**request_kwargs)
        except Exception as exc:
            raise EmbeddingProviderError(
                "OpenAI embedding request failed. Check your API key, model, timeout, and account limits.",
            ) from exc

        sorted_data = sorted(response.data, key=lambda item: item.index)
        embeddings = [item.embedding for item in sorted_data]

        for embedding in embeddings:
            if len(embedding) != self.dimensions:
                raise ValueError(
                    f"Embedding dimensions mismatch. Expected {self.dimensions}, received {len(embedding)}."
                )

        return embeddings


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Gemini embedding provider using the public Gemini REST API."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        dimensions: int,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.provider_name = "gemini"
        self.model_name = model_name
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload = {
            "requests": [
                {
                    "model": f"models/{self.model_name}",
                    "content": {
                        "parts": [
                            {
                                "text": text if text.strip() else " ",
                            }
                        ]
                    },
                    "output_dimensionality": self.dimensions,
                }
                for text in texts
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/models/{self.model_name}:batchEmbedContents",
                    headers={
                        "x-goog-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                await _raise_for_provider_status(
                    response,
                    provider_name="Gemini",
                    rate_limit_message=(
                        "Gemini embedding requests are currently rate-limited for this project. "
                        "Try again in a minute or reduce the embedding batch size."
                    ),
                )

                data = response.json()
                embeddings = [item["values"] for item in data["embeddings"]]
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError(
                "Gemini embedding request timed out. Try a smaller embedding batch size or upload a smaller file.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception("Gemini embedding HTTP request failed.")
            raise EmbeddingProviderError(
                "Gemini embedding request failed before the server returned a usable response.",
            ) from exc

        for embedding in embeddings:
            if len(embedding) != self.dimensions:
                raise ValueError(
                    f"Embedding dimensions mismatch. Expected {self.dimensions}, received {len(embedding)}."
                )

        return embeddings


@lru_cache
def get_embedding_provider(provider_name: str, vector_size: int) -> BaseEmbeddingProvider:
    normalized_provider = provider_name.strip().lower()

    if normalized_provider in {"mock", "local_hash"}:
        return LocalHashEmbeddingProvider(vector_size=vector_size)

    if normalized_provider in {"local", "sentence_transformers"}:
        return LocalSentenceTransformerEmbeddingProvider(
            model_name=settings.local_embedding_model,
            dimensions=vector_size,
            device=settings.local_embedding_device,
            runtime=settings.local_embedding_runtime,
            onnx_model_dir=settings.local_embedding_onnx_model_dir,
            onnx_intra_op_threads=settings.local_embedding_onnx_intra_op_threads,
            onnx_inter_op_threads=settings.local_embedding_onnx_inter_op_threads,
        )

    if normalized_provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model_name=settings.openai_embedding_model,
            dimensions=vector_size,
            base_url=settings.openai_base_url or None,
            timeout_seconds=settings.provider_timeout_seconds,
        )

    if normalized_provider == "gemini":
        if not settings.gemini_api_key.strip():
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER is gemini.")

        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_embedding_model,
            dimensions=vector_size,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
        )

    raise ValueError(f"Unsupported embedding provider: {provider_name}")


async def warm_configured_embedding_provider() -> None:
    if settings.embedding_provider != "local" or not settings.local_embedding_warmup_enabled:
        return

    provider = get_embedding_provider(
        provider_name=settings.embedding_provider,
        vector_size=settings.vector_size,
    )
    await provider.warmup()


def _load_sentence_transformer_model(
    model_name: str,
    device: str,
    *,
    runtime: str = "sentence_transformers",
    onnx_model_dir: str = "",
    onnx_intra_op_threads: int = 0,
    onnx_inter_op_threads: int = 0,
):
    cache_key = (
        model_name,
        device,
        runtime,
        onnx_model_dir,
        onnx_intra_op_threads,
        onnx_inter_op_threads,
    )
    cached_model = _SENTENCE_TRANSFORMER_MODEL_CACHE.get(cache_key)
    if cached_model is not None:
        return cached_model

    with _SENTENCE_TRANSFORMER_MODEL_LOCK:
        cached_model = _SENTENCE_TRANSFORMER_MODEL_CACHE.get(cache_key)
        if cached_model is not None:
            return cached_model

        logger.info("Loading local embedding model %s on device %s with runtime %s.", model_name, device, runtime)
        if runtime == "onnx":
            loaded_model = _load_onnx_sentence_transformer_model(
                model_name=model_name,
                device=device,
                onnx_model_dir=onnx_model_dir,
                onnx_intra_op_threads=onnx_intra_op_threads,
                onnx_inter_op_threads=onnx_inter_op_threads,
            )
        else:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingProviderError(
                    "sentence-transformers is not installed. Install backend dependencies again to use the local embedding provider.",
                ) from exc
            loaded_model = SentenceTransformer(model_name_or_path=model_name, device=device)
        _SENTENCE_TRANSFORMER_MODEL_CACHE[cache_key] = loaded_model
        return loaded_model


def _load_onnx_sentence_transformer_model(
    *,
    model_name: str,
    device: str,
    onnx_model_dir: str,
    onnx_intra_op_threads: int,
    onnx_inter_op_threads: int,
):
    if device != "cpu":
        raise EmbeddingProviderError(
            "The ONNX local embedding runtime currently supports only CPU in this project.",
            status_code=500,
        )

    model_path = _resolve_onnx_model_path(
        model_name=model_name,
        onnx_model_dir=onnx_model_dir,
    )
    return _OnnxSentenceEmbeddingModel(
        model_name=model_name,
        model_path=model_path,
        intra_op_threads=onnx_intra_op_threads,
        inter_op_threads=onnx_inter_op_threads,
    )


def _resolve_onnx_model_path(*, model_name: str, onnx_model_dir: str) -> Path:
    cache_dir = Path(onnx_model_dir).expanduser() if onnx_model_dir.strip() else None
    if cache_dir is not None:
        direct_candidates = [
            cache_dir / "model.onnx",
            cache_dir / _DEFAULT_ONNX_MODEL_FILENAME,
        ]
        for candidate in direct_candidates:
            if candidate.exists():
                return candidate

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise EmbeddingProviderError(
            "huggingface-hub is required to download the ONNX embedding model.",
            status_code=500,
        ) from exc

    downloaded_path = hf_hub_download(
        repo_id=model_name,
        filename=_DEFAULT_ONNX_MODEL_FILENAME,
        cache_dir=str(cache_dir) if cache_dir is not None else None,
    )
    return Path(downloaded_path)


def _build_onnx_session_options(*, intra_op_threads: int, inter_op_threads: int):
    if intra_op_threads <= 0 and inter_op_threads <= 0:
        return None

    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise EmbeddingProviderError(
            "onnxruntime is not installed. Install backend dependencies again to use the ONNX local embedding runtime.",
            status_code=500,
        ) from exc

    session_options = ort.SessionOptions()
    if intra_op_threads > 0:
        session_options.intra_op_num_threads = intra_op_threads
    if inter_op_threads > 0:
        session_options.inter_op_num_threads = inter_op_threads
    return session_options


async def _raise_for_provider_status(
    response: httpx.Response,
    *,
    provider_name: str,
    rate_limit_message: str,
) -> None:
    if response.is_success:
        return

    try:
        response_text = response.text.strip()
    except ResponseNotRead:
        await response.aread()
        response_text = response.text.strip()

    if response.status_code == 429:
        raise EmbeddingProviderError(rate_limit_message, status_code=429)

    if response.status_code == 401:
        raise EmbeddingProviderError(
            f"{provider_name} rejected the embedding API key. Check the configured credentials.",
            status_code=401,
        )

    if response.status_code == 403:
        raise EmbeddingProviderError(
            f"{provider_name} denied the embedding request. Check project permissions or billing.",
            status_code=403,
        )

    if response.status_code == 400:
        raise EmbeddingProviderError(
            f"{provider_name} rejected the embedding request. Check the selected model or request size.",
            status_code=400,
        )

    raise EmbeddingProviderError(
        f"{provider_name} embedding request failed with status {response.status_code}. "
        f"{response_text[:200]}",
        status_code=502,
    )
