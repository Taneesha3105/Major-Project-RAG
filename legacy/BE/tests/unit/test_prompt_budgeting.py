import unittest
from unittest.mock import patch

from app.chat.prompt_builder import build_chat_prompt, budget_chat_context
from app.chat.schemas import ChatRequest
from app.chat.service import ChatService
from app.retrieval.schemas import RetrievalLatency, RetrievalMatch, RetrievalResponse


def _match(index: int, text: str) -> RetrievalMatch:
    return RetrievalMatch(
        chunk_id=index,
        document_id=1,
        filename=f"doc-{index}.md",
        chunk_index=index,
        chunk_text=text,
        metadata={"source": "test"},
        similarity_score=1.0 - (index * 0.01),
    )


class FakeProvider:
    display_name = "mock:test"

    async def generate_answer(self, request):
        return "Synthetic answer"


class MultiMatchRetrievalService:
    def __init__(self, matches: list[RetrievalMatch]) -> None:
        self.matches = matches

    async def search(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=len(self.matches),
            matches=self.matches,
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.5,
                vector_search_ms=8.75,
                total_ms=13.25,
            ),
            message="Top matching chunks returned.",
        )

    async def search_for_chat(self, payload):
        return await self.search(payload)


class PromptBudgetingTests(unittest.IsolatedAsyncioTestCase):
    def test_build_chat_prompt_uses_neutral_source_labels_and_polished_instructions(self):
        prompt = build_chat_prompt(
            "Who is eligible for membership in this plan?",
            [_match(22, "You are eligible for membership if you meet these conditions.")],
        )

        self.assertIn("Source 1:", prompt)
        self.assertNotIn("Document:", prompt)
        self.assertNotIn("Chunk:", prompt)
        self.assertIn("Document excerpts:", prompt)
        self.assertIn("Question:", prompt)
        self.assertIn("Style rules:", prompt)
        self.assertIn(
            "Keep the answer concise, but include all directly relevant details needed to fully answer the question.",
            prompt,
        )
        self.assertIn(
            "For short factual answers drawn from tables, charts, or benefit rows, rewrite the answer as a complete natural sentence.",
            prompt,
        )
        self.assertIn(
            "Do not start those fact answers with bare dollar amounts, numbers, or labels like 'From network providers:'.",
            prompt,
        )
        self.assertIn(
            "If the excerpts show multiple directly relevant values for the same benefit, such as in-network and out-of-network amounts, include each of them in the answer.",
            prompt,
        )
        self.assertIn("Do not mention sources, excerpts, filenames, chunk numbers, section names, or chapter names.", prompt)
        self.assertIn("Do not say things like 'in this document', 'see Section 5.3', or 'as described in Chapter 4'.", prompt)
        self.assertIn("Give the answer directly instead of referring the user back to the document structure.", prompt)
        self.assertIn("If the excerpts are enough, answer confidently and stop.", prompt)
        self.assertIn("Do not add notes, caveats, side details, or follow-up commentary after the answer.", prompt)
        self.assertTrue(prompt.rstrip().endswith("Answer:"))

    def test_build_chat_prompt_adds_direct_rules_for_comparison_questions(self):
        prompt = build_chat_prompt(
            "What is the difference between an appeal and a complaint?",
            [
                _match(59, "Appeal - An appeal is something you do if you disagree with our decision."),
                _match(700, "Grievance - A type of complaint you make about our plan."),
            ],
        )

        self.assertIn('For this comparison question, explain what "appeal" means and what "complaint" means directly.', prompt)
        self.assertIn('Prefer a direct format such as: "Appeal is ..." and "Complaint is ..."', prompt)
        self.assertIn(
            "Do not add setup definitions for related internal terms unless they are necessary to define one of the compared terms.",
            prompt,
        )

    def test_build_chat_prompt_adds_no_section_reference_rules_for_process_questions(self):
        prompt = build_chat_prompt(
            "How far can a drug appeal go?",
            [_match(1, "Drug appeals can continue through multiple levels.")],
            intent="appeal_depth_or_reimbursement",
        )

        self.assertIn(
            "Do not tell the user to see another section or chapter; summarize the needed process directly.",
            prompt,
        )

    def test_build_chat_prompt_adds_no_document_reference_rule_for_summary_questions(self):
        prompt = build_chat_prompt(
            "Tell me about benefits.",
            [_match(1, "This plan includes medical and drug benefits.")],
            intent="broad_summary",
        )

        self.assertIn(
            "Do not describe the answer as being 'in this document'; give the summary directly.",
            prompt,
        )

    def test_build_chat_prompt_adds_direct_rules_for_inclusion_questions(self):
        prompt = build_chat_prompt(
            "What does not count toward project expenses?",
            [_match(1, "Project expenses do not count personal meals or entertainment purchases.")],
            intent="inclusion_exclusion",
            subtype="list_excludes",
            polarity="excludes",
        )

        self.assertIn("For inclusion or exclusion questions, answer the asked direction directly.", prompt)
        self.assertIn(
            "If the question asks what does not count or what is excluded, do not answer with what does count.",
            prompt,
        )

    def test_budget_chat_context_respects_total_budget_and_order(self):
        matches = [
            _match(0, "A" * 500),
            _match(1, "B" * 500),
            _match(2, "C" * 500),
        ]

        budgeted = budget_chat_context(
            matches,
            max_total_chars=1100,
            max_chunks=3,
            max_chars_per_chunk=900,
        )

        self.assertEqual([match.chunk_id for match in budgeted], [0, 1, 2])
        self.assertEqual(len(budgeted[0].chunk_text), 500)
        self.assertEqual(len(budgeted[1].chunk_text), 500)
        self.assertEqual(len(budgeted[2].chunk_text), 100)

    def test_budget_chat_context_respects_max_chunks(self):
        matches = [
            _match(0, "A" * 200),
            _match(1, "B" * 200),
            _match(2, "C" * 200),
            _match(3, "D" * 200),
        ]

        budgeted = budget_chat_context(
            matches,
            max_total_chars=5000,
            max_chunks=2,
            max_chars_per_chunk=900,
        )

        self.assertEqual([match.chunk_id for match in budgeted], [0, 1])

    def test_budget_chat_context_trims_final_chunk_with_ellipsis(self):
        matches = [_match(0, "A" * 950)]

        budgeted = budget_chat_context(
            matches,
            max_total_chars=900,
            max_chunks=3,
            max_chars_per_chunk=900,
        )

        self.assertEqual(len(budgeted), 1)
        self.assertEqual(len(budgeted[0].chunk_text), 900)
        self.assertTrue(budgeted[0].chunk_text.endswith("..."))

    def test_budget_chat_context_continues_after_truncated_chunk_when_budget_remains(self):
        matches = [
            _match(0, "A" * 950),
            _match(1, "B" * 250),
            _match(2, "C" * 250),
        ]

        budgeted = budget_chat_context(
            matches,
            max_total_chars=1500,
            max_chunks=3,
            max_chars_per_chunk=900,
        )

        self.assertEqual([match.chunk_id for match in budgeted], [0, 1, 2])
        self.assertEqual(len(budgeted[0].chunk_text), 900)
        self.assertTrue(budgeted[0].chunk_text.endswith("..."))
        self.assertEqual(len(budgeted[1].chunk_text), 250)
        self.assertEqual(len(budgeted[2].chunk_text), 250)

    async def test_chat_service_uses_only_budgeted_context_for_prompt_and_metadata(self):
        matches = [
            _match(0, "A" * 600),
            _match(1, "B" * 600),
            _match(2, "C" * 600),
            _match(3, "D" * 600),
        ]
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = MultiMatchRetrievalService(matches)
        service.provider = FakeProvider()

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch("app.chat.service.settings.chat_context_max_chars", 1500),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 900),
        ):
            response = await service.ask(
                ChatRequest(question="Explain the chat flow.", include_debug=True, top_k=4)
            )

        self.assertEqual(response.context_count, 3)
        self.assertEqual([item.chunk_id for item in response.context_refs], [0, 1, 2])
        self.assertIsNotNone(response.context_chunks)
        self.assertEqual(len(response.context_chunks), 3)
        self.assertEqual(len(response.context_chunks[0].chunk_text), 600)
        self.assertEqual(len(response.context_chunks[1].chunk_text), 600)
        self.assertEqual(len(response.context_chunks[2].chunk_text), 300)
        self.assertIn("Source 3:", response.prompt)
        self.assertNotIn("Document:", response.prompt)

    async def test_chat_service_expands_chat_retrieval_window_before_budgeting(self):
        matches = [
            _match(0, "A" * 350),
            _match(1, "B" * 350),
            _match(2, "C" * 350),
            _match(3, "D" * 350),
        ]

        class RecordingRetrievalService(MultiMatchRetrievalService):
            def __init__(self, inner_matches: list[RetrievalMatch]) -> None:
                super().__init__(inner_matches)
                self.requested_top_k: int | None = None

            async def search_for_chat(self, payload):
                self.requested_top_k = payload.top_k
                return await super().search_for_chat(payload)

        retrieval_service = RecordingRetrievalService(matches)
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = retrieval_service
        service.provider = FakeProvider()

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch("app.chat.service.settings.chat_retrieval_fetch_k", 10),
            patch("app.chat.service.settings.chat_context_max_chars", 900),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 400),
        ):
            response = await service.ask(
                ChatRequest(question="Who is eligible for this plan?", include_debug=True, top_k=3)
            )

        self.assertEqual(retrieval_service.requested_top_k, 10)
        self.assertEqual(response.context_count, 3)
        self.assertEqual([item.chunk_id for item in response.context_refs], [0, 1, 2])

    async def test_chat_service_reranks_prompt_candidates_by_question_term_overlap(self):
        matches = [
            RetrievalMatch(
                chunk_id=22,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=22,
                chunk_text=(
                    "Section 2.1 Eligibility requirements\n"
                    "You are eligible for membership in our plan as long as you meet all these conditions:"
                ),
                metadata={"source": "test"},
                similarity_score=0.52,
            ),
            RetrievalMatch(
                chunk_id=720,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=720,
                chunk_text=(
                    "Preferred Provider Organization plan and late enrollment penalty information "
                    "for a Part D plan."
                ),
                metadata={"source": "test"},
                similarity_score=0.50,
            ),
            RetrievalMatch(
                chunk_id=23,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=23,
                chunk_text=(
                    "You are eligible for membership in our plan as long as you meet all these conditions: "
                    "You have both Medicare Part A and Medicare Part B."
                ),
                metadata={"source": "test"},
                similarity_score=0.46,
            ),
        ]
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = MultiMatchRetrievalService(matches)
        service.provider = FakeProvider()

        with (
            patch.object(ChatService, "_resolve_provider", return_value=service.provider),
            patch("app.chat.service.settings.chat_retrieval_fetch_k", 10),
            patch("app.chat.service.settings.chat_context_max_chars", 2400),
            patch("app.chat.service.settings.chat_context_max_chunks", 3),
            patch("app.chat.service.settings.chat_context_per_chunk_max_chars", 900),
        ):
            response = await service.ask(
                ChatRequest(question="Who is eligible for membership in this plan?", include_debug=True, top_k=3)
            )

        self.assertEqual([item.chunk_index for item in response.context_refs], [22, 23, 720])


if __name__ == "__main__":
    unittest.main()
