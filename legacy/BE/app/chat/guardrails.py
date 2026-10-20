from __future__ import annotations

from dataclasses import dataclass
import re

from app.core.config import settings
from app.retrieval.schemas import RetrievalMatch


QUERY_INTENT_CLARIFY_FRAGMENT = "clarify_fragment"
QUERY_INTENT_DEFINITION = "definition"
QUERY_INTENT_COMPARISON = "comparison"
QUERY_INTENT_RESPONSIBILITY = "responsibility"
QUERY_INTENT_DEADLINE = "deadline"
QUERY_INTENT_INCLUSION_EXCLUSION = "inclusion_exclusion"
QUERY_INTENT_CALCULATION_METHOD = "calculation_method"
QUERY_INTENT_PROCESS_EXPLANATION = "process_explanation"
QUERY_INTENT_BROAD_SUMMARY = "broad_summary"
QUERY_INTENT_DEFAULT_FACT = "default_fact"

QUERY_SUBTYPE_DEADLINE_FAST = "deadline_fast"
QUERY_SUBTYPE_DEADLINE_STANDARD = "deadline_standard"
QUERY_SUBTYPE_RESPONSIBILITY_ACTOR = "responsibility"
QUERY_SUBTYPE_PROCESS_EXPLANATION = "process_explanation"
QUERY_SUBTYPE_CALCULATION_BASIS = "calculation"
QUERY_SUBTYPE_LIST_INCLUDES = "list_includes"
QUERY_SUBTYPE_LIST_EXCLUDES = "list_excludes"
QUERY_SUBTYPE_REQUIREMENT = "requirement"
QUERY_SUBTYPE_OVERVIEW = "overview"

QUERY_POLARITY_INCLUDES = "includes"
QUERY_POLARITY_EXCLUDES = "excludes"
QUERY_POLARITY_REQUIRES = "requires"
QUERY_POLARITY_FREE = "free"

STOP_WORDS = {
    "a",
    "about",
    "an",
    "are",
    "by",
    "do",
    "does",
    "for",
    "how",
    "i",
    "is",
    "it",
    "me",
    "my",
    "of",
    "the",
    "to",
    "what",
    "who",
    "why",
}

LOW_INFORMATION_TERMS = {
    "anything",
    "it",
    "know",
    "something",
    "stuff",
    "that",
    "these",
    "thing",
    "things",
    "this",
    "those",
    "you",
}

GENERIC_BROAD_TERMS = {
    "account",
    "app",
    "company",
    "document",
    "feature",
    "file",
    "page",
    "person",
    "policy",
    "process",
    "product",
    "program",
    "report",
    "service",
    "system",
    "team",
    "tool",
    "topic",
    "user",
}

QUESTION_SHAPE_TERMS = {
    "allow",
    "allowed",
    "answer",
    "calculate",
    "calculated",
    "compare",
    "difference",
    "exclude",
    "excluded",
    "free",
    "happen",
    "included",
    "means",
    "need",
    "required",
    "responsible",
    "timeline",
    "when",
    "who",
    "why",
}

GENERIC_REPLACEMENTS = {
    "cant": "can't",
    "doesnt": "doesn't",
    "dont": "don't",
    "whats": "what's",
}

FILLER_PHRASES = {"by the way"}

CLARIFY_FRAGMENT_PATTERNS = (
    re.compile(r"^\s*(?:is|are|was|were|can|could|should|would)\s+(?:this|that|it|these|those)\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+this\s*[?!.,]*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+that\s*[?!.,]*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+are\s+these\s*[?!.,]*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+are\s+those\s*[?!.,]*$", re.IGNORECASE),
)

DEFINITION_PATTERNS = (
    re.compile(r"^\bwhat\s+is\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+does\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+counts\s+as\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+qualifies\s+as\b", re.IGNORECASE),
    re.compile(r"^\bdefine\b", re.IGNORECASE),
)

COMPARISON_PATTERNS = (
    re.compile(r"\bdifference\s+between\b", re.IGNORECASE),
    re.compile(r"\bcompare\b", re.IGNORECASE),
    re.compile(r"\bcompared\s+(?:with|to)\b", re.IGNORECASE),
    re.compile(r"\bversus\b", re.IGNORECASE),
    re.compile(r"\bvs\b", re.IGNORECASE),
)

RESPONSIBILITY_PATTERNS = (
    re.compile(r"^\bwho\s+is\s+responsible\s+for\b", re.IGNORECASE),
    re.compile(r"^\bwhose\s+responsibility\s+is\b", re.IGNORECASE),
    re.compile(r"^\bwho\s+needs\s+to\b", re.IGNORECASE),
    re.compile(r"^\bwho\s+must\b", re.IGNORECASE),
    re.compile(r"^\bwho\s+has\s+to\b", re.IGNORECASE),
    re.compile(r"^\bwho\s+is\s+required\s+to\b", re.IGNORECASE),
)

DEADLINE_PATTERNS = (
    re.compile(r"\bhow\s+fast\b", re.IGNORECASE),
    re.compile(r"\bhow\s+long\b", re.IGNORECASE),
    re.compile(r"\bwithin\s+how\s+many\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+must\b", re.IGNORECASE),
    re.compile(r"\bhow\s+quick(?:ly)?\b", re.IGNORECASE),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
)

CALCULATION_PATTERNS = (
    re.compile(r"\bhow\s+is\b.+\b(?:calculated|determined|computed)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+are\b.+\b(?:calculated|determined|computed)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+is\s+the\s+basis\s+for\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+does\b.+\bmean\b", re.IGNORECASE),
)

INCLUSION_EXCLUSION_PATTERNS = (
    re.compile(r"\bcount(?:s|ed)?\s+toward\b", re.IGNORECASE),
    re.compile(r"\bincluded?\b", re.IGNORECASE),
    re.compile(r"\bexcluded?\b", re.IGNORECASE),
    re.compile(r"\bfree\b", re.IGNORECASE),
    re.compile(r"\bno\s+cost\b", re.IGNORECASE),
    re.compile(r"\bcover(?:ed|s)?\b", re.IGNORECASE),
    re.compile(r"\bcovered?\b", re.IGNORECASE),
    re.compile(r"\ballowed?\b", re.IGNORECASE),
    re.compile(r"\brequired?\b", re.IGNORECASE),
    re.compile(r"\bneed(?:ed|s)?\b", re.IGNORECASE),
)

PROCESS_PATTERNS = (
    re.compile(r"^\bhow\s+does\b.+\bwork\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+happens\s+if\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+if\b", re.IGNORECASE),
    re.compile(r"^\bhow\s+far\s+can\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+kinds?\s+of\s+problems?\s+use\b", re.IGNORECASE),
    re.compile(r"\bsteps?\b", re.IGNORECASE),
)

BROAD_SUMMARY_PATTERNS = (
    re.compile(r"^\btell\s+me\s+about\b", re.IGNORECASE),
    re.compile(r"^\bgive\s+me\s+(?:an?\s+)?overview\s+of\b", re.IGNORECASE),
    re.compile(r"^\bwhat\s+should\s+i\s+know\s+about\b", re.IGNORECASE),
)


@dataclass(slots=True)
class QueryNormalizationResult:
    original_question: str
    normalized_question: str
    changed_terms: dict[str, str]


@dataclass(slots=True)
class QueryRoute:
    intent: str
    clarification_message: str | None = None
    normalized_question: str = ""
    subtype: str | None = None
    polarity: str | None = None
    required_evidence: tuple[str, ...] = ()


def normalize_query_text(question: str, *, cutoff: float = 0.88) -> QueryNormalizationResult:
    del cutoff
    changed_terms: dict[str, str] = {}
    normalized_parts: list[str] = []

    for token in re.findall(r"[A-Za-z']+|[^A-Za-z']+", question):
        if not token.isalpha():
            normalized_parts.append(token)
            continue
        lowered = token.lower()
        replacement = GENERIC_REPLACEMENTS.get(lowered, lowered)
        if replacement != lowered:
            changed_terms[lowered] = replacement
        normalized_parts.append(replacement)

    normalized_question = "".join(normalized_parts).strip() or question.strip()
    return QueryNormalizationResult(
        original_question=question,
        normalized_question=normalized_question,
        changed_terms=changed_terms,
    )


def route_query(question: str) -> QueryRoute:
    normalized_question = _normalize_for_intent_routing(question)
    clarification_response = settings.chat_clarification_response
    if not normalized_question:
        return QueryRoute(
            intent=QUERY_INTENT_CLARIFY_FRAGMENT,
            clarification_message=clarification_response,
            normalized_question=normalized_question,
        )

    query_terms = [term for term in re.findall(r"[a-z0-9']+", normalized_question) if term not in STOP_WORDS]
    significant_terms = _extract_significant_terms(normalized_question)

    if _should_clarify_fragment(normalized_question, query_terms):
        return QueryRoute(
            intent=QUERY_INTENT_CLARIFY_FRAGMENT,
            clarification_message=clarification_response,
            normalized_question=normalized_question,
        )

    routed_intent, subtype, polarity, required_evidence = _detect_query_route(normalized_question, significant_terms)
    return QueryRoute(
        intent=routed_intent,
        clarification_message=clarification_response if routed_intent == QUERY_INTENT_CLARIFY_FRAGMENT else None,
        normalized_question=normalized_question,
        subtype=subtype,
        polarity=polarity,
        required_evidence=required_evidence,
    )


def maybe_build_clarification(question: str) -> str | None:
    return route_query(question).clarification_message


def should_fallback_for_low_confidence(
    matches: list[RetrievalMatch],
    *,
    minimum_top_score: float,
    high_confidence_top_score: float,
    minimum_average_score: float,
    average_top_n: int,
) -> bool:
    if not matches:
        return False

    top_score = matches[0].similarity_score
    if top_score >= high_confidence_top_score:
        return False
    if top_score < minimum_top_score:
        return True

    scored_matches = matches[:average_top_n]
    average_score = sum(match.similarity_score for match in scored_matches) / len(scored_matches)
    return average_score < minimum_average_score


def _normalize_for_intent_routing(question: str) -> str:
    normalized = question.strip().lower()
    normalized = normalized.replace("â€™", "'").replace("â€˜", "'")
    normalized = normalized.replace("â€œ", '"').replace("â€", '"')
    normalized = re.sub(r"\bu\.\s*s\.?\b", "united states", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _extract_significant_terms(question: str) -> list[str]:
    terms = [term for term in re.findall(r"[a-z0-9']+", question) if term not in STOP_WORDS]
    return [term for term in terms if len(term) >= 4]


def _should_clarify_fragment(question: str, query_terms: list[str]) -> bool:
    stripped_question = question.strip(" ?!.,")
    if stripped_question in FILLER_PHRASES:
        return True
    if any(pattern.search(question) for pattern in CLARIFY_FRAGMENT_PATTERNS):
        return True
    if not query_terms or all(term in LOW_INFORMATION_TERMS for term in query_terms):
        return True
    if len(query_terms) == 1 and not any(pattern.search(question) for pattern in DEFINITION_PATTERNS):
        return True
    if len(query_terms) <= 2 and _looks_like_vague_short_query(query_terms, question):
        return True
    return False


def _looks_like_vague_short_query(query_terms: list[str], question: str) -> bool:
    if any(char.isdigit() for char in question):
        return False
    if any(term in QUESTION_SHAPE_TERMS for term in query_terms):
        return False
    return all(term in GENERIC_BROAD_TERMS or term in LOW_INFORMATION_TERMS for term in query_terms)


def _detect_query_route(
    question: str,
    significant_terms: list[str],
) -> tuple[str, str | None, str | None, tuple[str, ...]]:
    if any(pattern.search(question) for pattern in COMPARISON_PATTERNS):
        return QUERY_INTENT_COMPARISON, None, None, ()
    if any(pattern.search(question) for pattern in RESPONSIBILITY_PATTERNS):
        return QUERY_INTENT_RESPONSIBILITY, QUERY_SUBTYPE_RESPONSIBILITY_ACTOR, None, ("actor",)
    if any(pattern.search(question) for pattern in DEADLINE_PATTERNS):
        return _detect_deadline_route(question)
    if any(pattern.search(question) for pattern in CALCULATION_PATTERNS):
        return QUERY_INTENT_CALCULATION_METHOD, QUERY_SUBTYPE_CALCULATION_BASIS, None, ("method",)
    if any(pattern.search(question) for pattern in PROCESS_PATTERNS):
        return QUERY_INTENT_PROCESS_EXPLANATION, QUERY_SUBTYPE_PROCESS_EXPLANATION, None, ("process",)
    if any(pattern.search(question) for pattern in INCLUSION_EXCLUSION_PATTERNS):
        return _detect_inclusion_exclusion_route(question)
    if _is_broad_summary_question(question):
        return QUERY_INTENT_BROAD_SUMMARY, QUERY_SUBTYPE_OVERVIEW, None, ("overview",)
    if any(pattern.search(question) for pattern in DEFINITION_PATTERNS):
        return QUERY_INTENT_DEFINITION, None, None, ()
    if len(significant_terms) <= 2 and _looks_like_vague_short_query(significant_terms, question):
        return QUERY_INTENT_CLARIFY_FRAGMENT, None, None, ()
    return QUERY_INTENT_DEFAULT_FACT, None, None, ()


def _detect_deadline_route(question: str) -> tuple[str, str | None, str | None, tuple[str, ...]]:
    lowered_question = question.lower()
    if "fast" in lowered_question or "expedited" in lowered_question:
        return QUERY_INTENT_DEADLINE, QUERY_SUBTYPE_DEADLINE_FAST, None, ("time_phrase", "fast")
    if "standard" in lowered_question:
        return QUERY_INTENT_DEADLINE, QUERY_SUBTYPE_DEADLINE_STANDARD, None, ("time_phrase", "standard")
    return QUERY_INTENT_DEADLINE, None, None, ("time_phrase",)


def _detect_inclusion_exclusion_route(
    question: str,
) -> tuple[str, str | None, str | None, tuple[str, ...]]:
    lowered_question = question.lower()
    if any(phrase in lowered_question for phrase in ("does not", "do not", "doesn't", "excluded", "not allowed", "not covered", "without")):
        return QUERY_INTENT_INCLUSION_EXCLUSION, QUERY_SUBTYPE_LIST_EXCLUDES, QUERY_POLARITY_EXCLUDES, ("negative",)
    if any(phrase in lowered_question for phrase in ("free", "no cost", "at no cost")):
        return QUERY_INTENT_INCLUSION_EXCLUSION, QUERY_SUBTYPE_LIST_INCLUDES, QUERY_POLARITY_FREE, ("free",)
    if any(term in lowered_question for term in ("require", "required", "needs", "need", "must", "permission", "approval", "authorization")):
        return QUERY_INTENT_INCLUSION_EXCLUSION, QUERY_SUBTYPE_REQUIREMENT, QUERY_POLARITY_REQUIRES, ("requirement",)
    return QUERY_INTENT_INCLUSION_EXCLUSION, QUERY_SUBTYPE_LIST_INCLUDES, QUERY_POLARITY_INCLUDES, ("positive",)


def _is_broad_summary_question(question: str) -> bool:
    return any(pattern.search(question) for pattern in BROAD_SUMMARY_PATTERNS)
