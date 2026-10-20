import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.retrieval.schemas import RetrievalMatch, RetrievalRequest
from app.retrieval.service import RankedChunkRow, RetrievalService


class FakeResult:
    def __init__(self, rows=None, scalar=None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


def _chunk(chunk_id: int, *, document_id: int = 1, chunk_index: int = 0, text: str = "chunk") -> SimpleNamespace:
    return SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        chunk_text=text,
        chunk_metadata={"source": "test"},
    )


class RetrievalAnnTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_lexical_terms_ignores_comparison_scaffolding_words(self):
        terms = RetrievalService._extract_lexical_terms(
            "What is the difference between an appeal and a complaint?"
        )

        self.assertEqual(terms, ["appeal", "complaint"])

    def test_comparison_lexical_score_prefers_glossary_definition_chunks(self):
        query = "What is the difference between an appeal and a complaint?"
        query_terms = RetrievalService._extract_lexical_terms(query)
        comparison_terms = RetrievalService._extract_comparison_terms(query, query_terms)

        glossary_chunk = (
            "Appeal – An appeal is something you do if you disagree with our decision to deny a "
            "request for coverage of health care services or prescription drugs."
        )
        noisy_chunk = (
            "If you already paid the Original Medicare cost-sharing amount, we'll reimburse the "
            "difference between what you paid and the in-network cost-sharing."
        )

        glossary_score = RetrievalService._score_lexical_candidate(
            query_terms,
            glossary_chunk,
            comparison_terms=comparison_terms,
        )
        noisy_score = RetrievalService._score_lexical_candidate(
            query_terms,
            noisy_chunk,
            comparison_terms=comparison_terms,
        )

        self.assertGreater(glossary_score, noisy_score)

    def test_comparison_support_score_prefers_glossary_heading_over_process_chunk(self):
        glossary_chunk = (
            "Chapter 12: Definitions\n"
            "Appeal – An appeal is something you do if you disagree with our decision to deny a request "
            "for coverage of health care services or prescription drugs."
        )
        process_chunk = (
            "Calls to this number are free. How to ask for a coverage decision or appeal about your medical care. "
            "A coverage decision is a decision we make about your benefits and coverage. "
            "An appeal is a formal way of asking us to review and change a coverage decision."
        )

        glossary_score = RetrievalService._score_comparison_support_match("appeal", glossary_chunk)
        process_score = RetrievalService._score_comparison_support_match("appeal", process_chunk)

        self.assertGreater(glossary_score, process_score)

    def test_process_support_score_prefers_topic_overlap_over_generic_process_phrase(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What happens if a member moves out of the plan service area?"
        )
        direct_chunk = (
            "If you move out of our plan's service area, you can't stay a member of this plan. "
            "When you move, you'll have a Special Enrollment Period to switch coverage."
        )
        generic_chunk = (
            "Complaint process information. The complaint process is used for certain types of problems "
            "when our plan doesn't follow the time periods in the appeal process."
        )

        direct_score = RetrievalService._score_process_support_match(query_terms, direct_chunk)
        generic_score = RetrievalService._score_process_support_match(query_terms, generic_chunk)

        self.assertGreater(direct_score, generic_score)

    def test_reimbursement_support_score_prefers_filing_deadline_chunk_over_plan_answer_deadline_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "How long does a member have to request reimbursement for foreign services?"
        )
        filing_chunk = (
            "You must request reimbursement from the Health Plan within 12 months from the date services are received. "
            "Include the itemized bill and proof of payment."
        )
        plan_answer_chunk = (
            "A fast coverage decision means we'll answer within 72 hours if your request is for a medical item or service."
        )

        filing_score = RetrievalService._score_process_support_match(query_terms, filing_chunk)
        plan_answer_score = RetrievalService._score_process_support_match(query_terms, plan_answer_chunk)

        self.assertGreater(filing_score, plan_answer_score)

    def test_part_d_counts_support_score_prefers_positive_counts_chunk_over_exclusion_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What out-of-pocket costs count toward Part D drug spending?"
        )
        positive_chunk = (
            "Out-of-Pocket Costs: this is how much you paid. This includes what you paid when you get a covered "
            "Part D drug, any payments for your drugs made by family or friends, and payments made by certain "
            "other people and organizations also count toward your out-of-pocket costs."
        )
        negative_chunk = (
            "Payments made for drugs that aren't normally covered in a Medicare Prescription Drug Plan won't "
            "count toward your total out-of-pocket costs."
        )

        positive_score = RetrievalService._score_part_d_counts_toward_support_match(query_terms, positive_chunk)
        negative_score = RetrievalService._score_part_d_counts_toward_support_match(query_terms, negative_chunk)

        self.assertGreater(positive_score, negative_score)

    def test_process_support_score_prefers_broader_multi_step_chunk_over_narrow_single_step_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms("How far can a request go in review?")
        broad_chunk = (
            "The review process can continue through several levels, and the final level is external review by an "
            "independent authority."
        )
        narrow_chunk = (
            "The level 2 response explains how to ask for level 3 review."
        )

        broad_score = RetrievalService._score_process_support_match(query_terms, broad_chunk)
        narrow_score = RetrievalService._score_process_support_match(query_terms, narrow_chunk)

        self.assertGreater(broad_score, narrow_score)

    def test_drug_decision_disagreement_support_score_prefers_direct_appeal_right_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What if the member disagrees with a plan decision about a covered drug?"
        )
        direct_chunk = (
            "If you disagree with this coverage decision, you can make an appeal. An initial coverage decision "
            "about your Part D drugs is called a coverage determination."
        )
        generic_chunk = (
            "Some drugs require you to get approval before we'll cover it. If your pharmacy tells you that your "
            "prescription cannot be filled as written, you can contact us to ask for a coverage decision."
        )

        direct_score = RetrievalService._score_process_support_match(query_terms, direct_chunk)
        generic_score = RetrievalService._score_process_support_match(query_terms, generic_chunk)

        self.assertGreater(direct_score, generic_score)

    def test_trim_comparison_support_text_starts_at_definition_heading(self):
        chunk_text = (
            "between nonaffiliated financial companies that together market\n"
            "financial products or services to you.\n"
            "Appeal – An appeal is something you do if you disagree with our decision to deny a request "
            "for coverage."
        )

        trimmed = RetrievalService._trim_comparison_support_text("appeal", chunk_text)

        self.assertTrue(trimmed.startswith("Appeal – An appeal is"))

    def test_trim_phrase_support_text_skips_long_prefix_before_matched_phrase(self):
        chunk_text = (
            "Clinical Research Study - A clinical research study is a way that doctors and scientists test new "
            "types of medical care. Coinsurance - An amount you may be required to pay as your share of the "
            "cost for deductibles. Coinsurance for in-network services is based upon contractually negotiated "
            "rates or Medicare Allowable Cost."
        )

        trimmed = RetrievalService._trim_phrase_support_text(
            chunk_text,
            ("contractually negotiated rates",),
        )

        self.assertTrue(trimmed.startswith("Coinsurance for in-network services is based upon"))

    def test_facet_score_prefers_matching_tier_and_stage_row(self):
        query_facets = RetrievalService._extract_query_facets(
            "What is the Tier 1 Part D copay during the initial coverage stage?"
        )
        matching_chunk = (
            "Drug Tier 1: Standard retail cost sharing (in-network) $0 copayment during the Initial Coverage Stage."
        )
        mismatched_chunk = (
            "Drug Tier 2: Standard retail cost sharing (in-network) $0 copayment during the Initial Coverage Stage."
        )

        matching_score = RetrievalService._facet_match_score(
            query_facets,
            RetrievalService._extract_chunk_facets(matching_chunk),
        )
        mismatched_score = RetrievalService._facet_match_score(
            query_facets,
            RetrievalService._extract_chunk_facets(mismatched_chunk),
        )

        self.assertGreater(matching_score, mismatched_score)

    def test_deadline_support_score_prefers_direct_time_answer_over_vague_timing_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "How fast must the system answer a standard review request?"
        )
        direct_chunk = "Standard review requests are answered within 72 hours."
        vague_chunk = "Standard review requests are handled during the usual response window."

        direct_score = RetrievalService._score_deadline_support_match(query_terms, direct_chunk)
        vague_score = RetrievalService._score_deadline_support_match(query_terms, vague_chunk)

        self.assertGreater(direct_score, vague_score)

    def test_process_support_score_prefers_move_out_consequence_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What happens if a member moves out of the service area?"
        )
        direct_chunk = (
            "If you move out of our plan's service area, you can't stay a member of this plan. "
            "When you move, you'll have a Special Enrollment Period to switch coverage."
        )
        generic_chunk = (
            "This means we can change the costs and benefits of the plan after December 31, 2026. "
            "We can also choose to stop offering the plan, or to offer it in a different service area."
        )

        direct_score = RetrievalService._score_process_support_match(query_terms, direct_chunk)
        generic_score = RetrievalService._score_process_support_match(query_terms, generic_chunk)

        self.assertGreater(direct_score, generic_score)

    def test_extract_lexical_terms_normalizes_move_and_answer_verbs(self):
        terms = RetrievalService._extract_lexical_terms(
            "How fast must the plan answer after a member moves out of the service area?"
        )

        self.assertIn("answer", terms)
        self.assertIn("move", terms)
        self.assertNotIn("moves", terms)

    def test_extract_lexical_terms_normalizes_u_s_to_united_states_tokens(self):
        terms = RetrievalService._extract_lexical_terms(
            "Can the plan cover emergency care outside the U.S.?"
        )

        self.assertIn("united", terms)
        self.assertTrue("states" in terms or "state" in terms)

    def test_process_support_score_penalizes_generic_plan_change_chunk_for_move_out_question(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What if a member moves out of the service area?"
        )
        direct_chunk = (
            "We must end your membership in our plan if you move out of our service area. "
            "When you move, you may be eligible for a Special Enrollment Period."
        )
        generic_chunk = (
            "We can change the costs and benefits of the plan after December 31, 2026. "
            "We can also choose to stop offering the plan in a different service area."
        )

        direct_score = RetrievalService._score_process_support_match(query_terms, direct_chunk)
        generic_score = RetrievalService._score_process_support_match(query_terms, generic_chunk)

        self.assertGreater(direct_score, generic_score)

    def test_process_support_score_prefers_topic_aligned_disagreement_chunk_over_unrelated_disagreement_chunk(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What if the member disagrees with a plan decision about a covered drug?"
        )
        direct_chunk = (
            "If you disagree with the decision, you can ask us to reconsider it by making an appeal for the drug coverage you want."
        )
        unrelated_chunk = (
            "If you disagree about paying an extra surcharge, you can ask another agency to review that decision."
        )

        direct_score = RetrievalService._score_process_support_match(query_terms, direct_chunk)
        unrelated_score = RetrievalService._score_process_support_match(query_terms, unrelated_chunk)

        self.assertGreater(direct_score, unrelated_score)

    async def test_comparison_support_matches_accept_candidate_rows_with_chunk_metadata(self):
        session = AsyncMock()
        service = RetrievalService(session)
        service._search_comparison_definition_candidates = AsyncMock(
            return_value=[
                (
                    101,
                    9,
                    "Evidence of Coverage 2026.pdf",
                    59,
                    "Appeal – An appeal is something you do if you disagree with our decision to deny a request.",
                    {"table_like_row": False},
                    12.0,
                )
            ]
        )

        matches = await service.search_comparison_support_matches(
            "What is the difference between an appeal and a complaint?",
            23,
            limit=3,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].chunk_id, 101)
        self.assertEqual(matches[0].metadata.get("table_like_row"), False)

    async def test_exact_mode_uses_single_vector_query(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(rows=[(_chunk(7, chunk_index=2, text="Exact chunk"), "doc.md", 0.11)]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])

        with patch("app.retrieval.service.settings.retrieval_mode", "exact"):
            response = await service.search(RetrievalRequest(query="Explain the system", top_k=3))

        self.assertEqual(response.returned_count, 1)
        self.assertEqual(response.matches[0].chunk_id, 7)
        self.assertEqual(session.execute.await_count, 1)

    async def test_exact_mode_filters_out_weak_matches_below_similarity_threshold(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(rows=[]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch("app.retrieval.service.settings.retrieval_mode", "exact"),
            patch("app.retrieval.service.settings.retrieval_similarity_threshold", 0.2),
        ):
            response = await service.search(RetrievalRequest(query="Unrelated question", top_k=3))

        self.assertEqual(response.returned_count, 0)
        self.assertEqual(response.matches, [])
        self.assertIn("similarity threshold", response.message.lower())

    async def test_ann_rerank_mode_uses_candidate_query_then_exact_rerank(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(rows=[(2, 0.04), (1, 0.06), (3, 0.08)]),
                FakeResult(
                    rows=[
                        (_chunk(1, chunk_index=0, text="Best exact chunk"), "doc.md", 0.02),
                        (_chunk(2, chunk_index=1, text="Second exact chunk"), "doc.md", 0.03),
                    ]
                ),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch("app.retrieval.service.settings.retrieval_mode", "ann_rerank"),
            patch("app.retrieval.service.settings.retrieval_candidate_k", 5),
        ):
            response = await service.search(RetrievalRequest(query="Explain the system", top_k=2))

        self.assertEqual([match.chunk_id for match in response.matches], [1, 2])
        self.assertEqual(session.execute.await_count, 2)

    async def test_ann_rerank_mode_returns_no_matches_when_reranked_results_fail_threshold(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(rows=[(2, 0.45), (1, 0.49), (3, 0.6)]),
                FakeResult(rows=[]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch("app.retrieval.service.settings.retrieval_mode", "ann_rerank"),
            patch("app.retrieval.service.settings.retrieval_candidate_k", 5),
            patch("app.retrieval.service.settings.retrieval_similarity_threshold", 0.2),
        ):
            response = await service.search(RetrievalRequest(query="Weak match", top_k=2))

        self.assertEqual(response.returned_count, 0)
        self.assertEqual(response.matches, [])
        self.assertIn("similarity threshold", response.message.lower())

    async def test_ann_rerank_mode_keeps_document_filter_on_candidate_and_rerank_queries(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(scalar=9),
                FakeResult(rows=[(4, 0.03), (5, 0.04)]),
                FakeResult(rows=[(_chunk(4, document_id=9, text="Scoped chunk"), "doc.md", 0.02)]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch("app.retrieval.service.settings.retrieval_mode", "ann_rerank"),
            patch("app.retrieval.service.settings.retrieval_candidate_k", 5),
        ):
            response = await service.search(RetrievalRequest(query="Explain the system", top_k=2, document_id=9))

        self.assertEqual(response.returned_count, 1)
        self.assertEqual(response.matches[0].document_id, 9)
        executed_statements = [str(call.args[0]) for call in session.execute.await_args_list]
        self.assertTrue(any("chunks.document_id =" in statement for statement in executed_statements[1:]))

    async def test_search_for_chat_fetches_ranked_rows_then_chunk_text_only(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(rows=[(7, 3, "doc.md", 2, 0.11)]),
                FakeResult(rows=[(7, "Exact chunk text")]),
                FakeResult(rows=[]),
                FakeResult(rows=[]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])

        with patch("app.retrieval.service.settings.retrieval_mode", "exact"):
            response = await service.search_for_chat(RetrievalRequest(query="Explain the system", top_k=3))

        self.assertEqual(response.returned_count, 1)
        self.assertEqual(response.matches[0].chunk_id, 7)
        self.assertEqual(response.matches[0].chunk_text, "Exact chunk text")
        self.assertEqual(response.matches[0].metadata["base_source_kinds"], ["vector"])
        self.assertEqual(session.execute.await_count, 4)

    async def test_search_for_chat_merges_lexical_rescue_matches_for_benefit_queries(self):
        service = RetrievalService.__new__(RetrievalService)
        service.session = AsyncMock()
        service.embedding_service = AsyncMock()
        service.embedding_service.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2]])
        service._search_ranked = AsyncMock(
            return_value=[
                RankedChunkRow(
                    chunk_id=2620,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=690,
                    distance=0.386,
                )
            ]
        )
        vector_match = RetrievalMatch(
            chunk_id=2620,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=690,
            chunk_text=(
                "Complaint process information. Copayment (or copay) is an amount you may be "
                "required to pay as your share of the cost for a medical service or supply."
            ),
            metadata={},
            similarity_score=0.614,
        )
        lexical_match = RetrievalMatch(
            chunk_id=1962,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=32,
            chunk_text=(
                "Primary care office visits $0 copayment per visit (in-network). "
                "$25 copayment per visit (out-of-network)."
            ),
            metadata={},
            similarity_score=0.74,
        )
        service._hydrate_chat_matches = AsyncMock(return_value=[vector_match])
        service._search_sparse_matches = AsyncMock(return_value=[])
        service._search_lexical_rescue_matches = AsyncMock(return_value=[lexical_match])

        with (
            patch("app.retrieval.service.settings.retrieval_mode", "exact"),
            patch("app.retrieval.service.settings.chat_lexical_rescue_enabled", True),
            patch("app.retrieval.service.settings.chat_lexical_rescue_k", 5),
            patch("app.retrieval.service.settings.chat_retrieval_fetch_k", 10),
        ):
            response = await service.search_for_chat(
                RetrievalRequest(query="What is the copay for a primary care visit?", top_k=3)
            )

        self.assertEqual(response.returned_count, 2)
        self.assertEqual([match.chunk_index for match in response.matches], [32, 690])
        service._search_sparse_matches.assert_awaited_once()
        service._search_lexical_rescue_matches.assert_awaited_once()

    def test_build_sparse_query_text_returns_terms_for_fact_queries(self):
        sparse_query = RetrievalService.build_sparse_query_text(
            "What out-of-pocket costs count toward Part D drug spending?"
        )

        self.assertEqual(sparse_query, "pocket costs count toward part drug spending \"part d\"")

    def test_build_sparse_query_text_preserves_plural_faq_terms_for_stemming(self):
        sparse_query = RetrievalService.build_sparse_query_text(
            "What services do you offer?"
        )

        self.assertEqual(sparse_query, "services offer")

    def test_short_two_term_queries_now_trigger_lexical_rescue(self):
        query_terms = RetrievalService._extract_lexical_terms(
            "What services do you offer?"
        )

        self.assertEqual(query_terms, ["service", "offer"])
        self.assertTrue(RetrievalService._should_run_lexical_rescue(query_terms))

    async def test_load_neighbor_matches_clamps_lower_bound_at_zero(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(scalar=2),
                FakeResult(rows=[(11, "doc.md", 0, "Heading"), (12, "doc.md", 1, "Next chunk")]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        anchor = RetrievalMatch(
            chunk_id=11,
            document_id=1,
            filename="doc.md",
            chunk_index=0,
            chunk_text="Heading",
            metadata={"support_intent": "responsibility"},
            similarity_score=0.7,
        )

        matches = await service.load_neighbor_matches([anchor], window=1)

        self.assertEqual([match.chunk_index for match in matches], [0, 1])
        executed_statements = " ".join(str(call.args[0]) for call in session.execute.await_args_list)
        self.assertNotIn("-1", executed_statements)

    async def test_load_neighbor_matches_handles_last_chunk_without_error(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                FakeResult(scalar=2),
                FakeResult(rows=[(21, "doc.md", 1, "Previous chunk"), (22, "doc.md", 2, "Last chunk")]),
            ]
        )
        service = RetrievalService.__new__(RetrievalService)
        service.session = session
        anchor = RetrievalMatch(
            chunk_id=22,
            document_id=1,
            filename="doc.md",
            chunk_index=2,
            chunk_text="Last chunk",
            metadata={"support_intent": "deadline"},
            similarity_score=0.72,
        )

        matches = await service.load_neighbor_matches([anchor], window=1)

        self.assertEqual([match.chunk_index for match in matches], [1, 2])


if __name__ == "__main__":
    unittest.main()
