import unittest
from unittest.mock import patch

from app.chat.guardrails import (
    QUERY_INTENT_DEADLINE,
    QUERY_INTENT_DEFAULT_FACT,
    QUERY_INTENT_INCLUSION_EXCLUSION,
    QUERY_INTENT_PROCESS_EXPLANATION,
    QUERY_POLARITY_INCLUDES,
    QUERY_SUBTYPE_CALCULATION_BASIS,
    QUERY_SUBTYPE_REQUIREMENT,
    route_query,
)
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


class FakeRetrievalService:
    async def search(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=1,
            matches=[
                RetrievalMatch(
                    chunk_id=11,
                    document_id=7,
                    filename="architecture.md",
                    chunk_index=0,
                    chunk_text="The chatbot retrieves chunks and then asks the LLM.",
                    metadata={"source": "test"},
                    similarity_score=0.91,
                )
            ],
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


class FailIfCalledProvider:
    display_name = "groq:test"

    async def generate_answer(self, request):
        raise AssertionError("Provider should not be called when no context is retrieved.")

    async def stream_answer(self, request):
        raise AssertionError("Streaming provider should not be called when no context is retrieved.")
        if False:
            yield ""


class EmptyRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=0,
            matches=[],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.2,
                vector_search_ms=6.8,
                total_ms=10.5,
            ),
            message="No matching chunks were found.",
        )


class WeakRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=3,
            matches=[
                RetrievalMatch(
                    chunk_id=21,
                    document_id=7,
                    filename="coverage.txt",
                    chunk_index=0,
                    chunk_text="Members may refuse treatment in some situations.",
                    metadata={},
                    similarity_score=0.44,
                ),
                RetrievalMatch(
                    chunk_id=22,
                    document_id=7,
                    filename="coverage.txt",
                    chunk_index=1,
                    chunk_text="Some treatment decisions depend on medical necessity.",
                    metadata={},
                    similarity_score=0.43,
                ),
                RetrievalMatch(
                    chunk_id=23,
                    document_id=7,
                    filename="coverage.txt",
                    chunk_index=2,
                    chunk_text="Providers may discuss treatment options with members.",
                    metadata={},
                    similarity_score=0.42,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.7,
                vector_search_ms=7.4,
                total_ms=11.6,
            ),
            message="Top matching chunks returned.",
        )


class StrongTopNoisyTailRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=4,
            matches=[
                RetrievalMatch(
                    chunk_id=41,
                    document_id=9,
                    filename="coverage.txt",
                    chunk_index=0,
                    chunk_text="Hospital outpatient observation stays are billed as outpatient services.",
                    metadata={},
                    similarity_score=0.81,
                ),
                RetrievalMatch(
                    chunk_id=42,
                    document_id=9,
                    filename="coverage.txt",
                    chunk_index=1,
                    chunk_text="Miscellaneous unrelated note.",
                    metadata={},
                    similarity_score=0.12,
                ),
                RetrievalMatch(
                    chunk_id=43,
                    document_id=9,
                    filename="coverage.txt",
                    chunk_index=2,
                    chunk_text="Another loosely related note.",
                    metadata={},
                    similarity_score=0.11,
                ),
                RetrievalMatch(
                    chunk_id=44,
                    document_id=9,
                    filename="coverage.txt",
                    chunk_index=3,
                    chunk_text="A fourth weak candidate.",
                    metadata={},
                    similarity_score=0.10,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.4,
                vector_search_ms=6.2,
                total_ms=10.1,
            ),
            message="Top matching chunks returned.",
        )


class TopThreeStrongTailWeakRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=4,
            matches=[
                RetrievalMatch(
                    chunk_id=51,
                    document_id=10,
                    filename="benefits.txt",
                    chunk_index=0,
                    chunk_text="Hospital benefits include outpatient observation and inpatient coverage rules.",
                    metadata={},
                    similarity_score=0.60,
                ),
                RetrievalMatch(
                    chunk_id=52,
                    document_id=10,
                    filename="benefits.txt",
                    chunk_index=1,
                    chunk_text="Coverage details explain cost sharing for observation stays.",
                    metadata={},
                    similarity_score=0.43,
                ),
                RetrievalMatch(
                    chunk_id=53,
                    document_id=10,
                    filename="benefits.txt",
                    chunk_index=2,
                    chunk_text="Members can review hospital service benefits in the plan materials.",
                    metadata={},
                    similarity_score=0.42,
                ),
                RetrievalMatch(
                    chunk_id=54,
                    document_id=10,
                    filename="benefits.txt",
                    chunk_index=3,
                    chunk_text="An unrelated low-similarity tail chunk.",
                    metadata={},
                    similarity_score=0.05,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.6,
                vector_search_ms=6.5,
                total_ms=10.6,
            ),
            message="Top matching chunks returned.",
        )


class PrimaryCareTableRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=4,
            matches=[
                RetrievalMatch(
                    chunk_id=2620,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=690,
                    chunk_text=(
                        "Complaint process information. Copayment (or copay) is an amount you may be "
                        "required to pay as your share of the cost for a medical service or supply, "
                        "like a doctor's visit, hospital outpatient visit, or a prescription drug."
                    ),
                    metadata={},
                    similarity_score=0.614,
                ),
                RetrievalMatch(
                    chunk_id=2203,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=273,
                    chunk_text=(
                        "$70 copayment for each Medicare-covered exam. Our plan covers certain telehealth "
                        "services including additional virtual medical visits, primary care provider visits, "
                        "and specialist visits."
                    ),
                    metadata={},
                    similarity_score=0.533,
                ),
                RetrievalMatch(
                    chunk_id=2250,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=320,
                    chunk_text=(
                        "Covered service chart for preventive visits. The visit includes a review of your "
                        "health and referrals for other care if needed. There is no coinsurance, copayment, "
                        "or deductible for a one-time Medicare-covered EKG screening."
                    ),
                    metadata={},
                    similarity_score=0.547,
                ),
                RetrievalMatch(
                    chunk_id=1962,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=32,
                    chunk_text=(
                        "Maximum out-of-pocket amounts. Primary care office visits $0 copayment per visit "
                        "(in-network). $25 copayment per visit (out-of-network). Specialist office visits "
                        "$40 copayment per visit (in-network)."
                    ),
                    metadata={},
                    similarity_score=0.515,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=5.1,
                vector_search_ms=9.7,
                total_ms=15.2,
            ),
            message="Top matching chunks returned.",
        )


class MedicalEmergencyDefinitionRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=4,
            matches=[
                RetrievalMatch(
                    chunk_id=2001,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=108,
                    chunk_text=(
                        "When you receive emergency care outside of the United States under the worldwide "
                        "emergency benefit, only the medical services directly related to the immediate "
                        "medical emergency are covered while you remain in a foreign country. Coverage is "
                        "limited to emergency services required to stabilize your condition."
                    ),
                    metadata={},
                    similarity_score=0.700,
                ),
                RetrievalMatch(
                    chunk_id=2002,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=439,
                    chunk_text=(
                        "Important message about what you pay for vaccines. Some vaccines are considered "
                        "medical benefits and are covered under Part B. Other vaccines are considered "
                        "Part D drugs."
                    ),
                    metadata={},
                    similarity_score=0.687,
                ),
                RetrievalMatch(
                    chunk_id=2003,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=106,
                    chunk_text=(
                        "A medical emergency is when you, or any other prudent layperson with an average "
                        "knowledge of health and medicine, believe that you have medical symptoms that "
                        "require immediate medical attention to prevent loss of life, loss of a limb, or "
                        "serious impairment to a bodily function."
                    ),
                    metadata={},
                    similarity_score=0.648,
                ),
                RetrievalMatch(
                    chunk_id=2004,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=105,
                    chunk_text=(
                        "If you have already paid for the covered services, we'll reimburse you for our "
                        "share of the cost for covered services."
                    ),
                    metadata={},
                    similarity_score=0.583,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=5.0,
                vector_search_ms=12.3,
                total_ms=17.8,
            ),
            message="Top matching chunks returned.",
        )


class AppealComplaintComparisonRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=5,
            matches=[
                RetrievalMatch(
                    chunk_id=2115,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=115,
                    chunk_text=(
                        "Research study information. Certain clinical research studies are approved by "
                        "Medicare and may ask for volunteers to participate in the study."
                    ),
                    metadata={},
                    similarity_score=0.650,
                ),
                RetrievalMatch(
                    chunk_id=2116,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=116,
                    chunk_text=(
                        "If you already paid the Original Medicare cost-sharing amount, we'll reimburse "
                        "the difference between what you paid and the in-network cost-sharing."
                    ),
                    metadata={},
                    similarity_score=0.650,
                ),
                RetrievalMatch(
                    chunk_id=2683,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=683,
                    chunk_text=(
                        "Appeal – An appeal is something you do if you disagree with our decision to "
                        "deny a request for coverage of health care services or prescription drugs or "
                        "payment for services or drugs you already got."
                    ),
                    metadata={},
                    similarity_score=0.560,
                ),
                RetrievalMatch(
                    chunk_id=2699,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=699,
                    chunk_text=(
                        "Grievance – A type of complaint you make about our plan, providers, or "
                        "pharmacies, including a complaint concerning the quality of your care. "
                        "This doesn't involve coverage or payment disputes."
                    ),
                    metadata={},
                    similarity_score=0.540,
                ),
                RetrievalMatch(
                    chunk_id=2628,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=628,
                    chunk_text=(
                        "Complaint process examples include problems related to quality of care, waiting "
                        "times, and the customer service you get."
                    ),
                    metadata={},
                    similarity_score=0.530,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.9,
                vector_search_ms=10.8,
                total_ms=16.4,
            ),
            message="Top matching chunks returned.",
        )

    async def search_comparison_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=2683,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=683,
                chunk_text=(
                    "Appeal – An appeal is something you do if you disagree with our decision to deny "
                    "a request for coverage of health care services or prescription drugs or payment "
                    "for services or drugs you already got."
                ),
                metadata={},
                similarity_score=0.62,
            ),
            RetrievalMatch(
                chunk_id=2700,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=700,
                chunk_text=(
                    "Grievance – A type of complaint you make about our plan, providers, or pharmacies, "
                    "including a complaint concerning the quality of your care. This doesn't involve "
                    "coverage or payment disputes."
                ),
                metadata={},
                similarity_score=0.61,
            ),
        ][:limit]


class PriorAuthorizationResponsibilityRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=4,
            matches=[
                RetrievalMatch(
                    chunk_id=2034,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=104,
                    chunk_text=(
                        "You don’t need a referral or prior authorization when you get care from out-of-network "
                        "providers. However, before getting services from out-of-network providers, ask for a "
                        "pre-visit coverage decision to confirm that the services you get are covered."
                    ),
                    metadata={},
                    similarity_score=0.463,
                ),
                RetrievalMatch(
                    chunk_id=2068,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=138,
                    chunk_text=(
                        "Covered services that may need approval in advance to be covered as in-network services "
                        "are marked in the Medical Benefits Chart. Network providers agree by contract to obtain "
                        "prior authorization from the plan and agree not to balance bill you."
                    ),
                    metadata={},
                    similarity_score=0.447,
                ),
                RetrievalMatch(
                    chunk_id=2653,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=723,
                    chunk_text=(
                        "For certain drugs, you or your provider must receive approval in advance before certain "
                        "drugs will be provided or payable. In the network portion of a PPO, some in-network "
                        "medical services are covered only if your doctor or other network provider gets prior "
                        "authorization from our plan."
                    ),
                    metadata={},
                    similarity_score=0.426,
                ),
                RetrievalMatch(
                    chunk_id=2031,
                    document_id=9,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=103,
                    chunk_text=(
                        "Some services require prior authorization from the plan in order to be covered. "
                        "Obtaining prior authorization is the responsibility of the PCP or treating provider."
                    ),
                    metadata={},
                    similarity_score=0.401,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=5.1,
                vector_search_ms=11.4,
                total_ms=17.2,
            ),
            message="Top matching chunks returned.",
        )

    async def search_responsibility_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=2031,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=103,
                chunk_text=(
                    "Some services require prior authorization from the plan in order to be covered. "
                    "Obtaining prior authorization is the responsibility of the PCP or treating provider."
                ),
                metadata={},
                similarity_score=0.66,
            ),
            RetrievalMatch(
                chunk_id=2653,
                document_id=9,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=723,
                chunk_text=(
                    "For certain drugs, you or your provider must receive approval in advance before certain "
                    "drugs will be provided or payable. In the network portion of a PPO, some in-network "
                    "medical services are covered only if your doctor or other network provider gets prior "
                    "authorization from our plan."
                ),
                metadata={},
                similarity_score=0.63,
            ),
        ][:limit]


class ExactPhraseLowScoreRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=3,
            matches=[
                RetrievalMatch(
                    chunk_id=61,
                    document_id=11,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=132,
                    chunk_text=(
                        "Your combined maximum out-of-pocket amount is $6,300. "
                        "This is the most you pay during the calendar year for covered Medicare Part A and Part B services."
                    ),
                    metadata={},
                    similarity_score=0.416,
                ),
                RetrievalMatch(
                    chunk_id=62,
                    document_id=11,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=130,
                    chunk_text=(
                        "Under our plan, there are limits on what you pay out-of-pocket for covered medical services."
                    ),
                    metadata={},
                    similarity_score=0.397,
                ),
                RetrievalMatch(
                    chunk_id=63,
                    document_id=11,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=689,
                    chunk_text=(
                        "Combined Maximum Out-of-Pocket Amount means the most you will pay in a year for Part A and Part B services."
                    ),
                    metadata={},
                    similarity_score=0.391,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.8,
                vector_search_ms=7.9,
                total_ms=12.9,
            ),
            message="Top matching chunks returned.",
        )


class DeadlineSupportRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=3,
            matches=[
                RetrievalMatch(
                    chunk_id=401,
                    document_id=12,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=578,
                    chunk_text=(
                        "If the independent review organization says yes to part or all of your request for "
                        "coverage, the plan must provide the drug coverage within 24 hours after we receive "
                        "the decision from the review organization."
                    ),
                    metadata={},
                    similarity_score=0.725,
                ),
                RetrievalMatch(
                    chunk_id=402,
                    document_id=12,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=543,
                    chunk_text=(
                        "For a fast coverage decision about a Part D drug, we must give you an answer within "
                        "24 hours after we receive your request."
                    ),
                    metadata={},
                    similarity_score=0.601,
                ),
                RetrievalMatch(
                    chunk_id=403,
                    document_id=12,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=589,
                    chunk_text=(
                        "Fast appeals are handled quickly when your health requires it."
                    ),
                    metadata={},
                    similarity_score=0.637,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.2,
                vector_search_ms=8.4,
                total_ms=13.2,
            ),
            message="Top matching chunks returned.",
        )

    async def search_deadline_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=402,
                document_id=12,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=543,
                chunk_text=(
                    "For a fast coverage decision about a Part D drug, we must give you an answer within "
                    "24 hours after we receive your request."
                ),
                metadata={"support_intent": "deadline"},
                similarity_score=0.74,
            )
        ][:limit]


class DeadlineSafetyValveRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=1,
            matches=[
                RetrievalMatch(
                    chunk_id=410,
                    document_id=12,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=570,
                    chunk_text=(
                        "A standard coverage decision is made within 72 hours after we receive your request."
                    ),
                    metadata={},
                    similarity_score=0.683,
                )
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.0,
                vector_search_ms=6.5,
                total_ms=11.5,
            ),
            message="Top matching chunks returned.",
        )

    async def search_deadline_support_matches(self, question, document_id, *, limit):
        return []


class WeakSummaryRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=501,
                    document_id=13,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=383,
                    chunk_text=(
                        "You can ask the plan to make an exception and cover a drug even though it is not "
                        "on the Drug List."
                    ),
                    metadata={},
                    similarity_score=0.667,
                ),
                RetrievalMatch(
                    chunk_id=502,
                    document_id=13,
                    filename="Evidence of Coverage 2026.txt",
                    chunk_index=388,
                    chunk_text=(
                        "If your request is approved, coverage for the drug will be authorized before the "
                        "change takes effect."
                    ),
                    metadata={},
                    similarity_score=0.641,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.9,
                vector_search_ms=6.1,
                total_ms=10.8,
            ),
            message="Top matching chunks returned.",
        )

    async def search_summary_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=503,
                document_id=13,
                filename="Evidence of Coverage 2026.txt",
                chunk_index=390,
                chunk_text="Benefits and costs vary by service category.",
                metadata={"support_intent": "broad_summary", "summary_anchor": True},
                similarity_score=0.54,
            )
        ][:limit]


class FailIfRetrievedService:
    async def search_for_chat(self, payload):
        raise AssertionError("Retrieval should not be called for vague clarification queries.")


class CaptureQueryRetrievalService:
    def __init__(self) -> None:
        self.seen_query: str | None = None

    async def search_for_chat(self, payload):
        self.seen_query = payload.query
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=1,
            matches=[
                RetrievalMatch(
                    chunk_id=31,
                    document_id=8,
                    filename="hospital.txt",
                    chunk_index=0,
                    chunk_text="Hospital outpatient stays may still be billed as outpatient observation.",
                    metadata={},
                    similarity_score=0.62,
                )
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.1,
                vector_search_ms=6.9,
                total_ms=11.4,
            ),
            message="Top matching chunks returned.",
        )


class GenericDeadlineComposerRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=801,
                    document_id=21,
                    filename="operations-handbook.txt",
                    chunk_index=12,
                    chunk_text=(
                        "For an urgent incident request, the vendor must answer within 2 hours after the request is received."
                    ),
                    metadata={},
                    similarity_score=0.69,
                ),
                RetrievalMatch(
                    chunk_id=802,
                    document_id=21,
                    filename="operations-handbook.txt",
                    chunk_index=13,
                    chunk_text="Standard requests are handled during the normal service window.",
                    metadata={},
                    similarity_score=0.52,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.8,
                vector_search_ms=6.7,
                total_ms=11.2,
            ),
            message="Top matching chunks returned.",
        )

    async def search_deadline_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=801,
                document_id=21,
                filename="operations-handbook.txt",
                chunk_index=12,
                chunk_text=(
                    "For an urgent incident request, the vendor must answer within 2 hours after the request is received."
                ),
                metadata={"support_intent": "deadline"},
                similarity_score=0.74,
            )
        ][:limit]


class GenericReimbursementDeadlineComposerRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=806,
                    document_id=21,
                    filename="expense-policy.txt",
                    chunk_index=18,
                    chunk_text=(
                        "You must submit your reimbursement request within 12 months from the date the services are received."
                    ),
                    metadata={},
                    similarity_score=0.73,
                ),
                RetrievalMatch(
                    chunk_id=807,
                    document_id=21,
                    filename="expense-policy.txt",
                    chunk_index=19,
                    chunk_text="Include the itemized bill and proof of payment with your submission.",
                    metadata={},
                    similarity_score=0.64,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.6,
                vector_search_ms=6.4,
                total_ms=10.9,
            ),
            message="Top matching chunks returned.",
        )

    async def search_appeal_depth_or_reimbursement_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=806,
                document_id=21,
                filename="expense-policy.txt",
                chunk_index=18,
                chunk_text=(
                    "You must submit your reimbursement request within 12 months from the date the services are received."
                ),
                metadata={"support_intent": "appeal_depth_or_reimbursement"},
                similarity_score=0.74,
            ),
            RetrievalMatch(
                chunk_id=807,
                document_id=21,
                filename="expense-policy.txt",
                chunk_index=19,
                chunk_text="Include the itemized bill and proof of payment with your submission.",
                metadata={"support_intent": "appeal_depth_or_reimbursement"},
                similarity_score=0.69,
            ),
        ][:limit]


class InlineReimbursementDeadlineComposerRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=1,
            matches=[
                RetrievalMatch(
                    chunk_id=808,
                    document_id=21,
                    filename="expense-policy.txt",
                    chunk_index=20,
                    chunk_text=(
                        "You must request reimbursement from the plan within 12 months from the date services are "
                        "received. Include the itemized bill and proof of payment with your submission."
                    ),
                    metadata={},
                    similarity_score=0.75,
                )
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=3.5,
                vector_search_ms=6.1,
                total_ms=10.2,
            ),
            message="Top matching chunks returned.",
        )

    async def search_appeal_depth_or_reimbursement_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=808,
                document_id=21,
                filename="expense-policy.txt",
                chunk_index=20,
                chunk_text=(
                    "You must request reimbursement from the plan within 12 months from the date services are "
                    "received. Include the itemized bill and proof of payment with your submission."
                ),
                metadata={"support_intent": "appeal_depth_or_reimbursement"},
                similarity_score=0.76,
            )
        ][:limit]


class GenericResponsibilityComposerRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=811,
                    document_id=22,
                    filename="vendor-policy.txt",
                    chunk_index=4,
                    chunk_text=(
                        "Submitting the security review request is the responsibility of the project owner."
                    ),
                    metadata={},
                    similarity_score=0.63,
                ),
                RetrievalMatch(
                    chunk_id=812,
                    document_id=22,
                    filename="vendor-policy.txt",
                    chunk_index=5,
                    chunk_text="Security reviews must be completed before production access is granted.",
                    metadata={},
                    similarity_score=0.49,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.0,
                vector_search_ms=7.2,
                total_ms=11.9,
            ),
            message="Top matching chunks returned.",
        )

    async def search_responsibility_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=811,
                document_id=22,
                filename="vendor-policy.txt",
                chunk_index=4,
                chunk_text="Submitting the security review request is the responsibility of the project owner.",
                metadata={"support_intent": "responsibility"},
                similarity_score=0.71,
            )
        ][:limit]


class GenericInclusionComposerRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=821,
                    document_id=23,
                    filename="expense-policy.txt",
                    chunk_index=7,
                    chunk_text=(
                        "Project expenses do not count personal meals, commuting costs, or entertainment purchases."
                    ),
                    metadata={},
                    similarity_score=0.68,
                ),
                RetrievalMatch(
                    chunk_id=822,
                    document_id=23,
                    filename="expense-policy.txt",
                    chunk_index=8,
                    chunk_text="Approved travel and lodging can be reimbursed when they are work-related.",
                    metadata={},
                    similarity_score=0.47,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.2,
                vector_search_ms=7.1,
                total_ms=11.8,
            ),
            message="Top matching chunks returned.",
        )

    async def search_inclusion_exclusion_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=821,
                document_id=23,
                filename="expense-policy.txt",
                chunk_index=7,
                chunk_text=(
                    "Project expenses do not count personal meals, commuting costs, or entertainment purchases."
                ),
                metadata={"support_intent": "inclusion_exclusion"},
                similarity_score=0.72,
            )
        ][:limit]


class GenericProcessPolicyRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=831,
                    document_id=24,
                    filename="onboarding-guide.txt",
                    chunk_index=2,
                    chunk_text=(
                        "During onboarding, the manager starts the request, the new hire completes the required forms, "
                        "and IT activates access after the approvals are complete."
                    ),
                    metadata={},
                    similarity_score=0.66,
                ),
                RetrievalMatch(
                    chunk_id=832,
                    document_id=24,
                    filename="onboarding-guide.txt",
                    chunk_index=3,
                    chunk_text="The process usually finishes after the approvals and access checks are done.",
                    metadata={},
                    similarity_score=0.53,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.1,
                vector_search_ms=7.0,
                total_ms=11.7,
            ),
            message="Top matching chunks returned.",
        )

    async def search_process_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=831,
                document_id=24,
                filename="onboarding-guide.txt",
                chunk_index=2,
                chunk_text=(
                    "During onboarding, the manager starts the request, the new hire completes the required forms, "
                    "and IT activates access after the approvals are complete."
                ),
                metadata={"support_intent": "process_explanation"},
                similarity_score=0.70,
            )
        ][:limit]


class GenericOverviewComposerRetrievalService:
    async def search_for_chat(self, payload):
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=2,
            matches=[
                RetrievalMatch(
                    chunk_id=841,
                    document_id=25,
                    filename="team-handbook.txt",
                    chunk_index=0,
                    chunk_text=(
                        "Team Handbook\n"
                        "Use this guide to understand:\n"
                        "• Account setup and access\n"
                        "• Required training and compliance tasks\n"
                        "• Equipment, support, and workplace policies\n"
                        "• Key contacts for help"
                    ),
                    metadata={},
                    similarity_score=0.73,
                ),
                RetrievalMatch(
                    chunk_id=842,
                    document_id=25,
                    filename="team-handbook.txt",
                    chunk_index=1,
                    chunk_text="The handbook also explains office hours and support coverage.",
                    metadata={},
                    similarity_score=0.58,
                ),
            ],
            latency=RetrievalLatency(
                document_lookup_ms=None,
                query_embedding_ms=4.0,
                vector_search_ms=6.8,
                total_ms=11.3,
            ),
            message="Top matching chunks returned.",
        )

    async def search_summary_support_matches(self, question, document_id, *, limit):
        return [
            RetrievalMatch(
                chunk_id=841,
                document_id=25,
                filename="team-handbook.txt",
                chunk_index=0,
                chunk_text=(
                    "Use this guide to understand:\n"
                    "• Account setup and access\n"
                    "• Required training and compliance tasks\n"
                    "• Equipment, support, and workplace policies\n"
                    "• Key contacts for help"
                ),
                metadata={"support_intent": "broad_summary", "summary_anchor": True},
                similarity_score=0.74,
            )
        ][:limit]


class ChatServiceLatencyTests(unittest.IsolatedAsyncioTestCase):
    def test_router_does_not_treat_long_term_care_as_deadline_question(self):
        routed_query = route_query("How does long-term care work?")

        self.assertNotEqual(routed_query.intent, QUERY_INTENT_DEADLINE)

    async def test_ask_returns_lean_payload_and_stage_latency_breakdown_by_default(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FakeRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="Explain the chat flow."))

        self.assertEqual(response.provider, "mock:test")
        self.assertEqual(response.context_count, 1)
        self.assertEqual(len(response.context_refs), 1)
        self.assertIsNone(response.prompt)
        self.assertIsNone(response.context_chunks)
        self.assertEqual(response.answer, "Synthetic answer")
        self.assertEqual(response.latency.retrieval.query_embedding_ms, 4.5)
        self.assertEqual(response.latency.retrieval.vector_search_ms, 8.75)
        self.assertGreaterEqual(response.latency.prompt_build_ms, 0.0)
        self.assertGreaterEqual(response.latency.llm_generation_ms, 0.0)
        self.assertGreaterEqual(response.latency.total_ms, 0.0)
        self.assertEqual(response.latency.retrieval.total_ms, 13.25)

    async def test_ask_includes_debug_payload_when_requested(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FakeRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="Explain the chat flow.", include_debug=True)
            )

        self.assertIsNotNone(response.prompt)
        self.assertIsNotNone(response.context_chunks)
        self.assertEqual(len(response.context_chunks), 1)
        self.assertEqual(response.context_chunks[0].chunk_text, "The chatbot retrieves chunks and then asks the LLM.")

    async def test_ask_returns_guardrail_message_without_calling_provider_when_no_context(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = EmptyRetrievalService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="What is the color of the sky?"))

        self.assertEqual(response.provider, "groq:test")
        self.assertEqual(response.context_count, 0)
        self.assertEqual(response.context_refs, [])
        self.assertEqual(
            response.answer,
            "I don't have enough information to answer that right now.",
        )
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_stream_returns_guardrail_message_without_calling_provider_when_no_context(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = EmptyRetrievalService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            events = [event async for event in service.stream(ChatRequest(question="What is gravity?"))]

        self.assertEqual(len(events), 3)
        self.assertIn('"context_count": 0', events[0])
        self.assertIn(
            "I don't have enough information to answer that right now.",
            events[1],
        )
        self.assertIn("Streaming completed.", events[2])

    async def test_ask_returns_clarification_for_vague_query_without_retrieval_or_provider(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="what are benefits?"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_generic_clarification_for_single_word_broad_topic_query(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="doctor"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_generic_clarification_for_any_single_word_query(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="nurse"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_generic_clarification_for_incomplete_question_fragment(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="what is"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_generic_clarification_for_filler_phrase(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="by the way"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_generic_clarification_for_low_information_multiword_prompt(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="what is this you know what is that"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def legacy_test_ask_returns_generic_clarification_for_short_broad_phrase_query(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="primary care"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_same_generic_clarification_for_punctuation_variant(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = FailIfRetrievedService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="hospital?"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.latency.retrieval.total_ms, 0.0)
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_returns_fallback_for_low_confidence_matches_without_provider_call(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = WeakRetrievalService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="i dont want healthcare"))

        self.assertEqual(response.context_count, 0)
        self.assertEqual(
            response.answer,
            "I don't have enough information to answer that right now.",
        )
        self.assertEqual(response.latency.llm_generation_ms, 0.0)

    async def test_ask_allows_high_confidence_top_chunk_even_when_tail_chunks_are_weak(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = StrongTopNoisyTailRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="hospital observation"))

        self.assertEqual(response.answer, "Synthetic answer")
        self.assertEqual(response.context_count, 3)

    async def test_ask_checks_average_only_on_prompt_limited_chunks(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = TopThreeStrongTailWeakRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="hospital benefits"))

        self.assertEqual(response.answer, "Synthetic answer")
        self.assertEqual(response.context_count, 3)

    async def test_prepare_chat_normalizes_generic_replacements_before_retrieval(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        capture_service = CaptureQueryRetrievalService()
        service.retrieval_service = capture_service
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="whats the deployment process"))

        self.assertEqual(capture_service.seen_query, "what's the deployment process")
        self.assertEqual(response.context_count, 1)
        self.assertEqual(response.answer, "Synthetic answer")

    async def test_short_specific_phrase_still_reaches_retrieval(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        capture_service = CaptureQueryRetrievalService()
        service.retrieval_service = capture_service
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="primary care copay"))

        self.assertEqual(capture_service.seen_query, "primary care copay")
        self.assertEqual(response.context_count, 1)
        self.assertEqual(response.answer, "Synthetic answer")

    async def test_rerank_promotes_primary_care_price_chunk_into_prompt_context(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = PrimaryCareTableRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="What is the copay for a primary care visit?"))

        chunk_indexes = [context_ref.chunk_index for context_ref in response.context_refs]
        self.assertIn(32, chunk_indexes)

    async def legacy_test_rerank_promotes_definition_chunk_for_definition_style_question(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = MedicalEmergencyDefinitionRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="What is considered a medical emergency under this plan?")
            )

        chunk_indexes = [context_ref.chunk_index for context_ref in response.context_refs]
        self.assertEqual(chunk_indexes[0], 106)
        self.assertIn(106, chunk_indexes)
        self.assertNotEqual(chunk_indexes[0], 108)

    async def legacy_test_rerank_promotes_comparison_definition_chunks_for_difference_questions(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = AppealComplaintComparisonRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="What is the difference between an appeal and a complaint?")
            )

        chunk_indexes = [context_ref.chunk_index for context_ref in response.context_refs]
        self.assertEqual(chunk_indexes, [683, 700])
        self.assertEqual(response.context_count, 2)

    async def legacy_test_rerank_promotes_direct_responsibility_chunks_for_responsibility_questions(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = PriorAuthorizationResponsibilityRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="Who is responsible for getting prior authorization?")
            )

        chunk_indexes = [context_ref.chunk_index for context_ref in response.context_refs]
        self.assertEqual(chunk_indexes, [103, 723])
        self.assertEqual(response.context_count, 2)

    async def test_deadline_support_prefers_direct_deadline_chunk(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = DeadlineSupportRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="How fast must the plan answer a fast drug coverage decision request?")
            )

        chunk_indexes = [context_ref.chunk_index for context_ref in response.context_refs]
        self.assertEqual(chunk_indexes[0], 543)
        self.assertIn(543, chunk_indexes)

    async def test_specialized_intent_without_support_falls_back_to_default_fact_path(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = DeadlineSafetyValveRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="How fast must the plan answer a standard drug coverage decision request?")
            )

        self.assertEqual(response.answer, "Synthetic answer")
        self.assertEqual(response.context_refs[0].chunk_index, 570)
        self.assertTrue(response.provider_used)
        self.assertEqual(response.answer_path, "llm")

    async def test_broad_summary_question_clarifies_when_summary_support_is_too_weak(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = WeakSummaryRetrievalService()
        service.provider = FailIfCalledProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="Tell me about benefits."))

        self.assertEqual(
            response.answer,
            "Could you say a bit more about what you want to know?",
        )
        self.assertEqual(response.context_count, 0)

    async def test_include_debug_returns_detected_intent_and_candidate_source_trace(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = DeadlineSupportRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(
                    question="How fast must the plan answer a fast drug coverage decision request?",
                    include_debug=True,
                )
            )

        self.assertIsNotNone(response.debug_trace)
        assert response.debug_trace is not None
        self.assertEqual(response.debug_trace.detected_intent, "deadline")
        self.assertTrue(response.debug_trace.support_retrieval_used)
        self.assertTrue(response.debug_trace.support_retrieval_succeeded)
        self.assertGreaterEqual(len(response.debug_trace.candidate_sources), 1)
        self.assertIsNotNone(response.debug_trace.candidate_sources[0].document_id)
        self.assertIsNotNone(response.debug_trace.candidate_sources[0].chunk_index)

    async def test_exact_phrase_grounding_can_bypass_low_similarity_guardrail(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = ExactPhraseLowScoreRetrievalService()
        service.provider = FakeProvider()

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(ChatRequest(question="What is the out-of-pocket maximum?"))

        self.assertEqual(response.answer, "Synthetic answer")
        self.assertEqual(response.context_count, 3)

    async def legacy_test_rerank_prefers_stronger_summary_chunk_for_two_term_queries(self):
        query = "What is the out-of-pocket maximum?"
        noisy_match = RetrievalMatch(
            chunk_id=2237,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=307,
            chunk_text=(
                "You pay these amounts until you reach the out-of-pocket maximum for covered services."
            ),
            metadata={},
            similarity_score=0.40,
        )
        summary_match = RetrievalMatch(
            chunk_id=1962,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=32,
            chunk_text=(
                "Maximum out-of-pocket amounts. This is the most you will pay out-of-pocket "
                "for your covered Part A and Part B services. From network providers: $3,900."
            ),
            metadata={},
            similarity_score=0.74,
        )

        reranked = ChatService._rerank_prompt_matches(query, [noisy_match, summary_match])

        self.assertEqual([match.chunk_index for match in reranked], [32, 307])

    def legacy_test_rerank_prefers_definition_chunk_over_followup_coverage_chunk(self):
        query = "What is considered a medical emergency under this plan?"
        followup_match = RetrievalMatch(
            chunk_id=108,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=108,
            chunk_text=(
                "When you receive emergency care outside of the United States under the worldwide "
                "emergency benefit, only the medical services directly related to the immediate "
                "medical emergency are covered while you remain in a foreign country."
            ),
            metadata={},
            similarity_score=0.700,
        )
        definition_match = RetrievalMatch(
            chunk_id=106,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=106,
            chunk_text=(
                "A medical emergency is when you, or any other prudent layperson with an average "
                "knowledge of health and medicine, believe that you have medical symptoms that "
                "require immediate medical attention."
            ),
            metadata={},
            similarity_score=0.648,
        )

        reranked = ChatService._rerank_prompt_matches(query, [followup_match, definition_match])

        self.assertEqual([match.chunk_index for match in reranked], [106, 108])

    def legacy_test_rerank_prefers_matching_tier_row_for_stage_cost_question(self):
        query = "What is the Tier 1 Part D copay during the initial coverage stage?"
        tier_two_match = RetrievalMatch(
            chunk_id=3001,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=35,
            chunk_text=(
                "Drug Tier 2: Standard retail cost sharing (in-network) $0 copayment during the Initial Coverage Stage."
            ),
            metadata={},
            similarity_score=0.72,
        )
        tier_one_match = RetrievalMatch(
            chunk_id=3002,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=34,
            chunk_text=(
                "Drug Tier 1: Standard retail cost sharing (in-network) $0 copayment during the Initial Coverage Stage."
            ),
            metadata={},
            similarity_score=0.70,
        )

        reranked = ChatService._rerank_prompt_matches(query, [tier_two_match, tier_one_match])

        self.assertEqual([match.chunk_index for match in reranked], [34, 35])

    def test_rerank_prefers_exact_labeled_row_over_generic_stage_summary_for_structured_fact_lookup(self):
        query = "What is the Tier 1 Part D copay during the initial coverage stage?"
        generic_stage_match = RetrievalMatch(
            chunk_id=3003,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=47,
            chunk_text=(
                "You stay in the Initial Coverage Stage until your total out-of-pocket costs reach $2,100. "
                "$0 copayment $0 copayment 21% coinsurance."
            ),
            metadata={"table_like_row": True, "label_value_row": True},
            similarity_score=0.78,
        )
        exact_row_match = RetrievalMatch(
            chunk_id=3004,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=27,
            chunk_text=(
                "Drug Tier 1: Standard retail cost sharing (in-network) $0 copayment during the Initial Coverage Stage."
            ),
            metadata={"table_like_row": True, "label_value_row": True},
            similarity_score=0.70,
        )

        reranked = ChatService._rerank_prompt_matches(query, [generic_stage_match, exact_row_match])

        self.assertEqual([match.chunk_index for match in reranked], [27, 47])

    def legacy_test_structured_fact_value_evidence_requires_exact_label_and_value(self):
        exact_value_match = RetrievalMatch(
            chunk_id=3005,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=28,
            chunk_text="Drug Tier 2: Standard retail cost sharing (in-network) $0 copayment.",
            metadata={},
            similarity_score=0.72,
        )
        generic_summary_match = RetrievalMatch(
            chunk_id=3006,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=335,
            chunk_text="During the Initial Coverage Stage, your share of the cost will vary depending on the drug.",
            metadata={},
            similarity_score=0.80,
        )

        self.assertTrue(
            ChatService._has_structured_fact_value_evidence(
                "What is the Tier 2 Part D copay during the initial coverage stage?",
                [exact_value_match, generic_summary_match],
            )
        )
        self.assertFalse(
            ChatService._has_structured_fact_value_evidence(
                "What is the Tier 4 Part D cost during the initial coverage stage?",
                [generic_summary_match],
            )
        )

    def legacy_test_structured_fact_value_evidence_rejects_narrative_example_amount_for_wrong_tier(self):
        narrative_match = RetrievalMatch(
            chunk_id=3007,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=339,
            chunk_text=(
                "With this plan, you pay part of the cost of Tier 3, Tier 4 and Tier 5 drugs. "
                "For example, if your coinsurance is 25% and the total cost of your prescription is $100, "
                "you would pay $25."
            ),
            metadata={},
            similarity_score=0.81,
        )
        scope_match = RetrievalMatch(
            chunk_id=3008,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=335,
            chunk_text="During the Initial Coverage Stage, your share of the cost will vary depending on the drug.",
            metadata={},
            similarity_score=0.80,
        )

        self.assertFalse(
            ChatService._has_structured_fact_value_evidence(
                "What is the Tier 5 Part D cost during the initial coverage stage?",
                [narrative_match, scope_match],
            )
        )

    def legacy_test_structured_fact_value_evidence_requires_subject_alignment_for_network_maximum(self):
        wrong_value_type_match = RetrievalMatch(
            chunk_id=3009,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=28,
            chunk_text="Drug Tier 2: Standard retail cost sharing (in-network) $0 copayment.",
            metadata={},
            similarity_score=0.72,
        )
        correct_maximum_match = RetrievalMatch(
            chunk_id=3010,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=140,
            chunk_text="Your in-network maximum out-of-pocket amount is $3,900.",
            metadata={},
            similarity_score=0.74,
        )

        self.assertFalse(
            ChatService._has_structured_fact_value_evidence(
                "What is the in-network maximum out-of-pocket amount?",
                [wrong_value_type_match],
            )
        )
        self.assertTrue(
            ChatService._has_structured_fact_value_evidence(
                "What is the in-network maximum out-of-pocket amount?",
                [wrong_value_type_match, correct_maximum_match],
            )
        )

    def test_rerank_prefers_network_maximum_chunk_over_in_network_copay_rows(self):
        query = "What is the in-network maximum out-of-pocket amount?"
        maximum_match = RetrievalMatch(
            chunk_id=3011,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=140,
            chunk_text="Your in-network maximum out-of-pocket amount is $3,900.",
            metadata={"label_value_row": True},
            similarity_score=0.74,
        )
        copay_match = RetrievalMatch(
            chunk_id=3012,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=28,
            chunk_text="Drug Tier 2: Standard retail cost sharing (in-network) $0 copayment.",
            metadata={"label_value_row": True},
            similarity_score=0.74,
        )

        reranked = ChatService._rerank_prompt_matches(query, [copay_match, maximum_match])

        self.assertEqual([match.chunk_index for match in reranked], [140, 28])

    def legacy_test_structured_fact_proximity_accepts_network_providers_as_in_network_equivalent(self):
        self.assertTrue(
            ChatService._has_exact_label_value_proximity(
                {"in-network"},
                "Maximum out-of-pocket amounts From network providers: $3,900.",
            )
        )

    def legacy_test_valid_structured_fact_match_requires_subject_alignment(self):
        self.assertFalse(
            ChatService._is_valid_structured_fact_match(
                "What is specialist visit cost in-network?",
                "Primary care office visits $0 copayment per visit (in-network).",
            )
        )
        self.assertTrue(
            ChatService._is_valid_structured_fact_match(
                "What is specialist visit cost in-network?",
                "Specialist office visits $40 copayment per visit (in-network).",
            )
        )

    def legacy_test_structured_fact_proximity_accepts_broken_pdf_network_spacing(self):
        self.assertTrue(
            ChatService._has_exact_label_value_proximity(
                {"in-network"},
                "Specialist office visits $40 copayment per visit (in- network).",
            )
        )

    def test_rerank_prefers_move_out_membership_consequence_chunk_for_process_question(self):
        query = "What if a member moves out of the service area?"
        generic_service_area_match = RetrievalMatch(
            chunk_id=4101,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=10,
            chunk_text=(
                "This means we can change the costs and benefits of the plan after December 31, 2026. "
                "We can also choose to stop offering the plan, or to offer it in a different service area."
            ),
            metadata={},
            similarity_score=0.79,
        )
        consequence_match = RetrievalMatch(
            chunk_id=4102,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=564,
            chunk_text=(
                "We must end your membership in our plan if you move out of our service area. "
                "When you move, you may be eligible for a Special Enrollment Period."
            ),
            metadata={"support_intent": "process_explanation"},
            similarity_score=0.68,
        )

        reranked = ChatService._rerank_prompt_matches(
            query,
            [generic_service_area_match, consequence_match],
            intent="process_explanation",
        )

        self.assertEqual([match.chunk_index for match in reranked], [564, 10])

    def legacy_test_rerank_prefers_standard_drug_deadline_chunk_over_medical_service_deadline_chunk(self):
        query = "How fast must the plan answer a standard drug coverage decision request?"
        medical_service_match = RetrievalMatch(
            chunk_id=4201,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=455,
            chunk_text=(
                "A standard coverage decision is usually made within 7 calendar days or 14 calendar days "
                "for all other medical items and services, or 72 hours for Part B drugs."
            ),
            metadata={"support_intent": "deadline"},
            similarity_score=0.78,
        )
        drug_coverage_match = RetrievalMatch(
            chunk_id=4202,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=487,
            chunk_text=(
                "Standard coverage decisions are made within 72 hours after we receive your doctor's statement. "
                "A fast coverage decision is made within 24 hours."
            ),
            metadata={"support_intent": "deadline"},
            similarity_score=0.70,
        )

        reranked = ChatService._rerank_prompt_matches(
            query,
            [medical_service_match, drug_coverage_match],
            intent=QUERY_INTENT_DEADLINE,
            subtype="deadline_standard",
        )

        self.assertEqual([match.chunk_index for match in reranked], [487, 455])

    def legacy_test_rerank_penalizes_fast_complaint_chunk_for_standard_drug_deadline_question(self):
        query = "How fast must the plan answer a standard drug coverage decision request?"
        complaint_match = RetrievalMatch(
            chunk_id=4203,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=489,
            chunk_text=(
                "You can file a fast complaint about our decision to give you a standard coverage decision "
                "instead of the fast coverage decision you requested. We will answer your complaint within 24 hours."
            ),
            metadata={"support_intent": "deadline"},
            similarity_score=0.79,
        )
        drug_coverage_match = RetrievalMatch(
            chunk_id=4204,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=487,
            chunk_text=(
                "Standard coverage decisions are made within 72 hours after we receive your doctor's statement. "
                "Fast coverage decisions are made within 24 hours."
            ),
            metadata={"support_intent": "deadline"},
            similarity_score=0.70,
        )

        reranked = ChatService._rerank_prompt_matches(
            query,
            [complaint_match, drug_coverage_match],
            intent=QUERY_INTENT_DEADLINE,
            subtype="deadline_standard",
        )

        self.assertEqual([match.chunk_index for match in reranked], [487, 489])

    def legacy_test_rerank_prefers_drug_appeal_right_chunk_over_generic_coverage_determination(self):
        query = "What if the member disagrees with a plan decision about a covered drug?"
        generic_match = RetrievalMatch(
            chunk_id=4301,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=478,
            chunk_text=(
                "Part D coverage decisions and appeals. An initial coverage decision about your Part D drugs is "
                "called a coverage determination."
            ),
            metadata={"support_subtype": "drug_decision_disagreement", "support_intent": "process_explanation"},
            similarity_score=0.74,
        )
        appeal_right_match = RetrievalMatch(
            chunk_id=4302,
            document_id=9,
            filename="Evidence of Coverage 2026.pdf",
            chunk_index=494,
            chunk_text=(
                "If we say no, you have the right to ask us to reconsider this decision by making an appeal. "
                "This means asking again to get the drug coverage you want."
            ),
            metadata={"support_subtype": "drug_decision_disagreement", "support_intent": "process_explanation"},
            similarity_score=0.71,
        )

        reranked = ChatService._rerank_prompt_matches(
            query,
            [generic_match, appeal_right_match],
            intent="process_explanation",
            subtype="drug_decision_disagreement",
        )

        self.assertEqual([match.chunk_index for match in reranked], [494, 478])

    def test_rerank_prefers_glossary_definitions_for_comparison_questions(self):
        query = "What is the difference between an appeal and a complaint?"
        noisy_match = RetrievalMatch(
            chunk_id=2116,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=116,
            chunk_text=(
                "If you already paid the Original Medicare cost-sharing amount, we'll reimburse the "
                "difference between what you paid and the in-network cost-sharing."
            ),
            metadata={},
            similarity_score=0.650,
        )
        appeal_match = RetrievalMatch(
            chunk_id=2683,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=683,
            chunk_text=(
                "Appeal – An appeal is something you do if you disagree with our decision to deny a "
                "request for coverage of health care services or prescription drugs."
            ),
            metadata={},
            similarity_score=0.560,
        )
        complaint_match = RetrievalMatch(
            chunk_id=2699,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=699,
            chunk_text=(
                "Grievance – A type of complaint you make about our plan, providers, or pharmacies, "
                "including a complaint concerning the quality of your care. This doesn't involve "
                "coverage or payment disputes."
            ),
            metadata={},
            similarity_score=0.540,
        )

        reranked = ChatService._rerank_prompt_matches(query, [noisy_match, complaint_match, appeal_match])

        self.assertEqual([match.chunk_index for match in reranked], [683, 699, 116])

    def legacy_test_rerank_prefers_direct_responsibility_chunk_over_related_policy_chunk(self):
        query = "Who is responsible for getting prior authorization?"
        related_policy_match = RetrievalMatch(
            chunk_id=2034,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=104,
            chunk_text=(
                "You don’t need a referral or prior authorization when you get care from out-of-network "
                "providers. However, before getting services from out-of-network providers, ask for a "
                "pre-visit coverage decision to confirm that the services you get are covered."
            ),
            metadata={},
            similarity_score=0.463,
        )
        direct_responsibility_match = RetrievalMatch(
            chunk_id=2031,
            document_id=9,
            filename="Evidence of Coverage 2026.txt",
            chunk_index=103,
            chunk_text=(
                "Some services require prior authorization from the plan in order to be covered. "
                "Obtaining prior authorization is the responsibility of the PCP or treating provider."
            ),
            metadata={},
            similarity_score=0.401,
        )

        reranked = ChatService._rerank_prompt_matches(
            query,
            [related_policy_match, direct_responsibility_match],
        )

        self.assertEqual([match.chunk_index for match in reranked], [103, 104])

    def test_route_query_assigns_subtype_and_polarity_for_inclusion_exclusion_questions(self):
        routed_query = route_query("What does not count toward project expenses?")

        self.assertEqual(routed_query.intent, "inclusion_exclusion")
        self.assertEqual(routed_query.subtype, "list_excludes")
        self.assertEqual(routed_query.polarity, "excludes")

    def test_route_query_prefers_reimbursement_deadline_over_generic_deadline(self):
        routed_query = route_query("How long does a member have to request reimbursement for foreign services?")

        self.assertEqual(routed_query.intent, QUERY_INTENT_DEADLINE)
        self.assertIsNone(routed_query.subtype)

    def test_route_query_detects_prior_authorization_requirement_subtype(self):
        routed_query = route_query("Do out-of-network services need prior authorization?")

        self.assertEqual(routed_query.subtype, QUERY_SUBTYPE_REQUIREMENT)
        self.assertEqual(routed_query.polarity, "requires")

    def test_route_query_detects_current_accuracy_subtypes(self):
        self.assertEqual(
            route_query("What kinds of problems use the coverage decision and appeal process?").intent,
            QUERY_INTENT_PROCESS_EXPLANATION,
        )
        self.assertEqual(
            route_query("What if the member disagrees with a plan decision about a covered drug?").intent,
            QUERY_INTENT_PROCESS_EXPLANATION,
        )
        self.assertEqual(
            route_query("What out-of-pocket costs count toward Part D drug spending?").subtype,
            "list_includes",
        )
        self.assertEqual(
            route_query("How are coinsurance amounts calculated for different providers?").subtype,
            QUERY_SUBTYPE_CALCULATION_BASIS,
        )
        coverage_route = route_query("Can the plan cover emergency care outside the U.S.?")
        self.assertEqual(coverage_route.intent, QUERY_INTENT_INCLUSION_EXCLUSION)
        self.assertEqual(coverage_route.polarity, QUERY_POLARITY_INCLUDES)
        self.assertIn(
            route_query("What is the Tier 1 Part D copay during the initial coverage stage?").intent,
            {QUERY_INTENT_DEFAULT_FACT, "definition"},
        )

    def test_route_query_does_not_clarify_named_subject_question_with_is_this_phrase(self):
        routed_query = route_query("What card is this benefits guide for?")

        self.assertNotEqual(routed_query.intent, "clarify_fragment")
        self.assertIsNone(routed_query.clarification_message)

    async def test_deadline_route_uses_llm_when_composer_is_not_allowlisted(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericDeadlineComposerRetrievalService()
        service.provider = FakeProvider()

        async def deadline_answer(request):
            return "The plan must answer within 2 hours for an urgent incident request."

        service.provider.generate_answer = deadline_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="How fast must the plan answer an urgent incident request?", include_debug=True)
            )

        self.assertEqual(
            response.answer,
            "The plan must answer within 2 hours for an urgent incident request.",
        )
        self.assertGreaterEqual(response.context_count, 1)
        self.assertTrue(response.provider_used)
        self.assertEqual(response.answer_path, "llm")
        assert response.debug_trace is not None
        self.assertFalse(response.debug_trace.composer_allowed)
        self.assertIn(response.debug_trace.composer_block_reason, {None, "subtype_not_allowlisted"})

    async def test_generic_filing_deadline_question_uses_llm_without_local_composer(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericReimbursementDeadlineComposerRetrievalService()
        service.provider = FakeProvider()

        async def filing_answer(request):
            return "You must submit your reimbursement request within 12 months from the date the services are received."

        service.provider.generate_answer = filing_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="How long does a member have to request reimbursement for foreign services?")
            )

        self.assertEqual(
            response.answer,
            "You must submit your reimbursement request within 12 months from the date the services are received.",
        )
        self.assertGreaterEqual(response.context_count, 1)
        self.assertTrue(response.provider_used)
        self.assertEqual(response.answer_path, "llm")

    async def test_generic_filing_deadline_question_with_inline_details_uses_llm(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = InlineReimbursementDeadlineComposerRetrievalService()
        service.provider = FakeProvider()

        async def filing_answer(request):
            return "You must request reimbursement from the plan within 12 months from the date services are received."

        service.provider.generate_answer = filing_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="How long does a member have to request reimbursement for foreign services?")
            )

        self.assertEqual(
            response.answer,
            "You must request reimbursement from the plan within 12 months from the date services are received.",
        )
        self.assertGreaterEqual(response.context_count, 1)
        self.assertTrue(response.provider_used)
        self.assertEqual(response.answer_path, "llm")

    async def legacy_test_responsibility_route_uses_llm_when_composer_is_not_allowlisted(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericResponsibilityComposerRetrievalService()
        service.provider = FakeProvider()

        async def responsibility_answer(request):
            return "Project owner is responsible for submitting the security review request."

        service.provider.generate_answer = responsibility_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="Who is responsible for submitting the security review request?", include_debug=True)
            )

        self.assertEqual(
            response.answer,
            "Project owner is responsible for submitting the security review request.",
        )
        self.assertEqual(response.context_count, 1)
        self.assertTrue(response.provider_used)
        self.assertEqual(response.answer_path, "llm")
        assert response.debug_trace is not None
        self.assertEqual(response.debug_trace.composer_block_reason, "subtype_not_allowlisted")

    async def test_inclusion_exclusion_route_uses_llm_when_composer_is_not_allowlisted(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericInclusionComposerRetrievalService()
        service.provider = FakeProvider()

        async def inclusion_answer(request):
            return "Project expenses do not count personal meals, commuting costs, or entertainment purchases."

        service.provider.generate_answer = inclusion_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="What does not count toward project expenses?", include_debug=True)
            )

        self.assertEqual(
            response.answer,
            "Project expenses do not count personal meals, commuting costs, or entertainment purchases.",
        )
        self.assertGreaterEqual(response.context_count, 1)
        self.assertTrue(response.provider_used)
        self.assertEqual(response.answer_path, "llm")
        assert response.debug_trace is not None
        self.assertEqual(response.debug_trace.composer_block_reason, "subtype_not_allowlisted")

    async def test_process_question_applies_answer_policy_guardrail_for_specialized_routes(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericProcessPolicyRetrievalService()
        service.provider = FakeProvider()

        async def leaking_answer(request):
            return "Follow the onboarding process in Section 3.2."

        service.provider.generate_answer = leaking_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="How does onboarding work?", include_debug=True)
            )

        self.assertEqual(
            response.answer,
            "I don't have enough information to answer that right now.",
        )
        self.assertIsNotNone(response.debug_trace)
        assert response.debug_trace is not None
        self.assertEqual(response.debug_trace.detected_subtype, "process_explanation")
        self.assertTrue(response.debug_trace.answer_policy_rejected)

    async def test_specialized_stream_path_applies_answer_policy_guardrail(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericProcessPolicyRetrievalService()
        service.provider = FakeProvider()

        async def leaking_answer(request):
            return "Follow the onboarding process in Section 3.2."

        service.provider.generate_answer = leaking_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            events = [
                event
                async for event in service.stream(
                    ChatRequest(question="How does onboarding work?", include_debug=True)
                )
            ]

        self.assertIn('"detected_intent": "process_explanation"', events[0].lower())
        self.assertIn("I don't have enough information to answer that right now.", "".join(events))

    async def test_overview_route_uses_llm_when_composer_is_not_allowlisted(self):
        service = ChatService.__new__(ChatService)
        service.session = None
        service.retrieval_service = GenericOverviewComposerRetrievalService()
        service.provider = FakeProvider()

        async def overview_answer(request):
            return "Onboarding includes account setup, training, approvals, and first-week support."

        service.provider.generate_answer = overview_answer

        with patch.object(ChatService, "_resolve_provider", return_value=service.provider):
            response = await service.ask(
                ChatRequest(question="Tell me about onboarding.", include_debug=True)
            )

        self.assertIn("Onboarding includes", response.answer)
        self.assertNotIn("document", response.answer.lower())
        self.assertIsNotNone(response.debug_trace)
        assert response.debug_trace is not None
        self.assertEqual(response.debug_trace.detected_subtype, "overview")
        self.assertEqual(response.debug_trace.answer_path, "llm")
        self.assertEqual(response.debug_trace.composer_block_reason, "subtype_not_allowlisted")

if __name__ == "__main__":
    unittest.main()

