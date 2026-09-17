import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api.routes.providers import get_provider_status
from app.chat.reranker import NoopChatReranker
from app.chat.schemas import ChatRequest
from app.chat.service import ChatService
from app.retrieval.schemas import RetrievalLatency, RetrievalMatch, RetrievalResponse


class FakeProvider:
    display_name = "mock:test"

    async def generate_answer(self, request):
        return "Synthetic answer"

    async def stream_answer(self, request):
        if False:
            yield ""


class StaticRetrievalService:
    def __init__(self, matches: list[RetrievalMatch]) -> None:
        self.matches = matches

    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=len(self.matches),
            matches=self.matches,
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.2,
                vector_search_ms=8.1,
                total_ms=12.9,
            ),
            message="Top matching chunks returned.",
        )


class RecordingReranker:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.enabled = True
        self.model_name = "ms-marco-TinyBERT-L-2-v2"
        self.should_fail = should_fail
        self.calls: list[list[int]] = []

    async def warmup(self) -> None:
        return None

    async def rerank(self, question: str, matches: list[RetrievalMatch]):
        self.calls.append([match.chunk_id for match in matches])
        if self.should_fail:
            raise RuntimeError("rerank_failed")
        return SimpleNamespace(
            matches=list(reversed(matches)),
            rerank_ms=6.75,
            candidate_count=len(matches),
        )


def build_match(chunk_id: int, text: str, similarity_score: float) -> RetrievalMatch:
    return RetrievalMatch(
        chunk_id=chunk_id,
        document_id=1,
        filename="coverage.txt",
        chunk_index=chunk_id,
        chunk_text=text,
        metadata={"source": "test"},
        similarity_score=similarity_score,
    )


class FlashRankRerankingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.matches = [
            build_match(1, "Eligibility conditions include Medicare Part A and Part B.", 0.93),
            build_match(2, "You must live in the geographic service area.", 0.92),
            build_match(3, "You must be lawfully present in the United States.", 0.91),
        ]

    def test_chat_request_accepts_rerank_strategy(self) -> None:
        payload = ChatRequest(question="Who is eligible?", rerank_strategy="hybrid")
        self.assertEqual(payload.rerank_strategy, "hybrid")

    def test_chat_request_rejects_invalid_rerank_strategy(self) -> None:
        with self.assertRaisesRegex(ValueError, "rerank_strategy must be one of"):
            ChatRequest(question="Who is eligible?", rerank_strategy="invalid")

    async def test_fast_strategy_does_not_call_flashrank(self) -> None:
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = StaticRetrievalService(self.matches)
        service.provider = FakeProvider()
        service.reranker = RecordingReranker()

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch.object(ChatService, "_rerank_prompt_matches", return_value=[self.matches[1], self.matches[0], self.matches[2]]),
            patch("app.chat.service.settings.chat_context_max_chars", 2400),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 900),
        ):
            response = await service.ask(
                ChatRequest(question="Who is eligible for membership in this plan?", rerank_strategy="fast", include_debug=True)
            )

        self.assertEqual([item.chunk_id for item in response.context_refs], [2, 1, 3])
        self.assertEqual(service.reranker.calls, [])
        self.assertEqual(response.latency.rerank_ms, 0.0)
        self.assertFalse(response.debug_trace.flashrank_used)

    async def test_hybrid_strategy_uses_heuristic_top_n_then_flashrank(self) -> None:
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = StaticRetrievalService(self.matches)
        service.provider = FakeProvider()
        service.reranker = RecordingReranker()

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch.object(ChatService, "_rerank_prompt_matches", return_value=[self.matches[1], self.matches[0], self.matches[2]]),
            patch("app.chat.service.settings.flashrank_hybrid_top_n", 2),
            patch("app.chat.service.settings.chat_context_max_chars", 2400),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 900),
        ):
            response = await service.ask(
                ChatRequest(question="Who is eligible for membership in this plan?", rerank_strategy="hybrid", include_debug=True)
            )

        self.assertEqual(service.reranker.calls, [[2, 1]])
        self.assertEqual([item.chunk_id for item in response.context_refs], [1, 2, 3])
        self.assertTrue(response.debug_trace.flashrank_used)
        self.assertEqual(response.debug_trace.flashrank_before_order, [1, 2, 3])
        self.assertEqual(response.debug_trace.flashrank_after_order, [1, 2, 3])
        self.assertEqual(response.latency.rerank_ms, 6.75)

    async def test_neural_strategy_uses_fused_order_without_heuristic_rerank(self) -> None:
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = StaticRetrievalService(self.matches)
        service.provider = FakeProvider()
        service.reranker = RecordingReranker()

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch.object(ChatService, "_rerank_prompt_matches", side_effect=AssertionError("heuristic reranker should not run in neural mode")),
            patch("app.chat.service.settings.flashrank_neural_top_n", 2),
            patch("app.chat.service.settings.chat_context_max_chars", 2400),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 900),
        ):
            response = await service.ask(
                ChatRequest(question="Who is eligible for membership in this plan?", rerank_strategy="neural", include_debug=True)
            )

        self.assertEqual(service.reranker.calls, [[1, 2]])
        self.assertEqual([item.chunk_id for item in response.context_refs], [2, 1, 3])
        self.assertTrue(response.debug_trace.flashrank_used)
        self.assertEqual(response.debug_trace.flashrank_candidate_count, 2)

    async def test_flashrank_failure_falls_back_to_fast_order(self) -> None:
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = StaticRetrievalService(self.matches)
        service.provider = FakeProvider()
        service.reranker = RecordingReranker(should_fail=True)

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch.object(ChatService, "_rerank_prompt_matches", return_value=[self.matches[2], self.matches[1], self.matches[0]]),
            patch("app.chat.service.settings.flashrank_hybrid_top_n", 2),
            patch("app.chat.service.settings.chat_context_max_chars", 2400),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 900),
        ):
            response = await service.ask(
                ChatRequest(question="Who is eligible for membership in this plan?", rerank_strategy="hybrid", include_debug=True)
            )

        self.assertEqual([item.chunk_id for item in response.context_refs], [3, 2, 1])
        self.assertTrue(response.debug_trace.flashrank_fallback_used)
        self.assertEqual(response.debug_trace.flashrank_fallback_reason, "RuntimeError")
        self.assertEqual(response.latency.rerank_ms, 0.0)

    async def test_provider_status_reports_reranker_capabilities(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(chat_reranker=NoopChatReranker())))

        with (
            patch("app.api.routes.providers.settings.chat_rerank_strategy_default", "fast"),
            patch("app.api.routes.providers.settings.flashrank_enabled", True),
        ):
            payload = await get_provider_status(request)

        self.assertEqual(payload["defaults"]["rerank_strategy"], "fast")
        self.assertEqual(payload["reranker"]["available_strategies"], ["fast"])
        self.assertFalse(payload["reranker"]["flashrank_available"])


if __name__ == "__main__":
    unittest.main()
