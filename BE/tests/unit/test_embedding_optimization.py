import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.embeddings import provider as embedding_provider_module
from app.embeddings.provider import BaseEmbeddingProvider, warm_configured_embedding_provider
from app.embeddings.service import DocumentEmbeddingService


class FakeLocalProvider(BaseEmbeddingProvider):
    provider_name = "local"
    model_name = "fake-local"
    dimensions = 384

    def __init__(self, preferred_request_batch_size: int | None = None) -> None:
        self._preferred_request_batch_size = preferred_request_batch_size

    @property
    def preferred_request_batch_size(self) -> int | None:
        return self._preferred_request_batch_size

    @property
    def display_name(self) -> str:
        return "local:fake-local"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(index)] for index, _ in enumerate(texts, start=1)]


class EmbeddingOptimizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_embedding_service_uses_provider_batch_size_when_available(self):
        service = DocumentEmbeddingService.__new__(DocumentEmbeddingService)
        service.session = None
        service.provider = FakeLocalProvider(preferred_request_batch_size=3)

        batches = service._build_embedding_batches(["a", "b", "c", "d", "e", "f", "g"])

        self.assertEqual(batches, [["a", "b", "c"], ["d", "e", "f"], ["g"]])

    async def test_document_embedding_service_falls_back_to_global_batch_size(self):
        service = DocumentEmbeddingService.__new__(DocumentEmbeddingService)
        service.session = None
        service.provider = FakeLocalProvider(preferred_request_batch_size=None)

        original_batch_size = settings.embedding_batch_size
        settings.embedding_batch_size = 2
        try:
            batches = service._build_embedding_batches(["a", "b", "c", "d", "e"])
        finally:
            settings.embedding_batch_size = original_batch_size

        self.assertEqual(batches, [["a", "b"], ["c", "d"], ["e"]])

    async def test_warm_configured_embedding_provider_warms_local_provider_when_enabled(self):
        provider = FakeLocalProvider(preferred_request_batch_size=64)
        provider.warmup = AsyncMock()

        with (
            patch("app.embeddings.provider.settings.embedding_provider", "local"),
            patch("app.embeddings.provider.settings.local_embedding_warmup_enabled", True),
            patch("app.embeddings.provider.get_embedding_provider", return_value=provider),
        ):
            await warm_configured_embedding_provider()

        provider.warmup.assert_awaited_once()

    async def test_warm_configured_embedding_provider_skips_when_not_local(self):
        provider = FakeLocalProvider(preferred_request_batch_size=64)
        provider.warmup = AsyncMock()

        with (
            patch("app.embeddings.provider.settings.embedding_provider", "openai"),
            patch("app.embeddings.provider.get_embedding_provider", return_value=provider),
        ):
            await warm_configured_embedding_provider()

        provider.warmup.assert_not_awaited()

    async def test_sentence_transformer_loader_reuses_cached_model(self):
        created_models: list[object] = []

        class FakeSentenceTransformer:
            def __init__(self, model_name_or_path: str, device: str, **kwargs) -> None:
                created_models.append((model_name_or_path, device, kwargs))

        embedding_provider_module._SENTENCE_TRANSFORMER_MODEL_CACHE.clear()

        with patch.dict(
            "sys.modules",
            {"sentence_transformers": SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)},
        ):
            first = embedding_provider_module._load_sentence_transformer_model(
                "demo-model",
                "cpu",
                runtime="sentence_transformers",
            )
            second = embedding_provider_module._load_sentence_transformer_model(
                "demo-model",
                "cpu",
                runtime="sentence_transformers",
            )

        self.assertIs(first, second)
        self.assertEqual(created_models, [("demo-model", "cpu", {})])

    async def test_sentence_transformer_loader_uses_onnx_runtime_when_configured(self):
        created_sessions: list[tuple[str, dict[str, object]]] = []

        class FakeTokenizer:
            @classmethod
            def from_pretrained(cls, model_name: str) -> "FakeTokenizer":
                return cls()

        class FakeConfig:
            hidden_size = 384

            @classmethod
            def from_pretrained(cls, model_name: str) -> "FakeConfig":
                return cls()

        class FakeInferenceSession:
            def __init__(self, model_path: str, **kwargs) -> None:
                created_sessions.append((model_path, kwargs))

            def get_inputs(self):
                return [
                    SimpleNamespace(name="input_ids"),
                    SimpleNamespace(name="attention_mask"),
                    SimpleNamespace(name="token_type_ids"),
                ]

        fake_onnxruntime = SimpleNamespace(
            SessionOptions=lambda: SimpleNamespace(),
            InferenceSession=FakeInferenceSession,
        )
        fake_transformers = SimpleNamespace(AutoTokenizer=FakeTokenizer, AutoConfig=FakeConfig)
        fake_huggingface_hub = SimpleNamespace(
            hf_hub_download=lambda **kwargs: "cached-model/onnx/model.onnx",
        )
        embedding_provider_module._SENTENCE_TRANSFORMER_MODEL_CACHE.clear()

        with patch.dict(
            "sys.modules",
            {
                "onnxruntime": fake_onnxruntime,
                "transformers": fake_transformers,
                "huggingface_hub": fake_huggingface_hub,
            },
        ):
            model = embedding_provider_module._load_sentence_transformer_model(
                "demo-model",
                "cpu",
                runtime="onnx",
                onnx_model_dir="",
                onnx_intra_op_threads=0,
                onnx_inter_op_threads=0,
            )

        self.assertEqual(model.get_sentence_embedding_dimension(), 384)
        self.assertEqual(len(created_sessions), 1)
        model_path, kwargs = created_sessions[0]
        self.assertEqual(Path(model_path).as_posix(), "cached-model/onnx/model.onnx")
        self.assertEqual(kwargs["providers"], ["CPUExecutionProvider"])
