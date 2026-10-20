"""AI due-diligence analysis: per-workstream risk/contradiction/gap detection, executive summary,
and checklist evidence review. All findings carry citations back to the source chunks."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm
from app.ai.prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    CATEGORY_ANALYSIS_PROMPT,
    CHECKLIST_REVIEW_PROMPT,
    EXECUTIVE_SUMMARY_PROMPT,
    format_sources,
)
from app.ai.retrieval import RetrievedChunk, hybrid_search, to_citation
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, ServiceUnavailableError, ValidationFailedError
from app.db.session import SessionLocal
from app.models import AnalysisRun, Deal, RiskFinding, User
from app.models.enums import (
    AnalysisStatus,
    ChecklistStatus,
    DocumentCategory,
    EvidenceCoverage,
    FindingSource,
    FindingType,
    Severity,
)
from app.repositories.diligence_repository import AnalysisRunRepository, ChecklistRepository, RiskFindingRepository
from app.repositories.document_repository import DocumentRepository
from app.services.audit_service import AuditService
from app.services.checklist_templates import CORE_CATEGORIES
from app.services.job_queue import analysis_queue

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    DocumentCategory.FINANCIAL: "Financial due diligence",
    DocumentCategory.LEGAL: "Legal due diligence",
    DocumentCategory.TAX: "Tax due diligence",
    DocumentCategory.CONTRACTS: "Material contracts",
    DocumentCategory.HR: "HR & employment",
    DocumentCategory.INTELLECTUAL_PROPERTY: "Intellectual property",
    DocumentCategory.REGULATORY: "Regulatory & compliance",
    DocumentCategory.OPERATIONAL: "Operations",
    DocumentCategory.COMMERCIAL: "Commercial due diligence",
    DocumentCategory.IT: "IT & cybersecurity",
    DocumentCategory.ENVIRONMENTAL: "Environmental & ESG",
    DocumentCategory.CORPORATE: "Corporate structure & governance",
    DocumentCategory.OTHER: "Other documents",
}

# Targeted retrieval probes per workstream: what an experienced reviewer would look for.
CATEGORY_PROBES: dict[DocumentCategory, list[str]] = {
    DocumentCategory.FINANCIAL: [
        "revenue growth decline profitability EBITDA margins",
        "debt borrowings loan covenants security interest liabilities",
        "cash flow working capital liquidity going concern",
        "audit opinion qualification restatement accounting policy change",
        "related party transactions off-balance sheet contingent liabilities guarantees",
    ],
    DocumentCategory.LEGAL: [
        "litigation lawsuit claim dispute proceedings damages",
        "regulatory investigation penalty fine sanction",
        "indemnification warranty liability cap limitation",
        "change of control consent termination",
    ],
    DocumentCategory.TAX: [
        "tax audit assessment dispute penalty",
        "uncertain tax position deferred tax provision",
        "transfer pricing intercompany tax losses",
    ],
    DocumentCategory.CONTRACTS: [
        "change of control assignment consent clause",
        "termination for convenience exclusivity non-compete",
        "minimum purchase commitment penalty liquidated damages",
        "customer concentration key supplier dependency renewal",
    ],
    DocumentCategory.HR: [
        "key employee retention severance change of control bonus",
        "pension benefit obligation unfunded liability",
        "employment dispute union collective agreement",
    ],
    DocumentCategory.INTELLECTUAL_PROPERTY: [
        "patent trademark ownership registration expiry",
        "license royalty exclusivity infringement claim",
    ],
    DocumentCategory.REGULATORY: [
        "license permit compliance violation",
        "data protection privacy GDPR breach",
        "anti-bribery corruption AML sanctions antitrust",
    ],
    DocumentCategory.CORPORATE: [
        "share capital shareholders ownership structure options",
        "shareholder agreement drag tag pre-emption veto rights",
        "board resolution approval authority",
    ],
    DocumentCategory.COMMERCIAL: [
        "customer concentration revenue by customer churn",
        "market share competition pricing pressure",
    ],
    DocumentCategory.OPERATIONAL: ["operational dependency capacity disruption", "synergy integration cost"],
    DocumentCategory.IT: ["cybersecurity incident breach vulnerability", "legacy system license dependency"],
    DocumentCategory.ENVIRONMENTAL: ["environmental contamination remediation permit", "ESG emissions liability"],
    DocumentCategory.OTHER: ["risk liability obligation dispute", "material adverse change"],
}


class _Finding(BaseModel):
    title: str = Field(description="Concise headline, max 12 words")
    description: str = Field(description="What the issue is and why it matters, citing facts")
    finding_type: Literal["risk", "contradiction", "missing_information", "opportunity"]
    severity: Literal["low", "medium", "high", "critical"]
    recommendation: str = Field(description="Concrete next step: question to seller, SPA protection, etc.")
    financial_impact: str | None = Field(default=None, description="Quantified exposure if stated in sources")
    source_ids: list[int] = Field(description="Source numbers supporting the finding")


class _FindingList(BaseModel):
    findings: list[_Finding] = Field(default_factory=list)


class _ItemReview(BaseModel):
    item_number: int
    coverage: Literal["found", "partial", "missing"]
    note: str
    source_ids: list[int] = Field(default_factory=list)


class _ChecklistReview(BaseModel):
    reviews: list[_ItemReview] = Field(default_factory=list)


async def _gather_context(
    session: AsyncSession, deal_id: uuid.UUID, category: DocumentCategory, max_chunks: int = 14
) -> list[RetrievedChunk]:
    seen: dict[int, RetrievedChunk] = {}
    for probe in CATEGORY_PROBES.get(category, CATEGORY_PROBES[DocumentCategory.OTHER]):
        result = await hybrid_search(session, deal_id=deal_id, query=probe, categories=[category], top_k=4)
        for chunk in result.chunks:
            seen.setdefault(chunk.chunk_id, chunk)
        await session.commit()
    ranked = sorted(seen.values(), key=lambda c: c.score, reverse=True)
    return ranked[:max_chunks]


class AnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = AnalysisRunRepository(session)

    async def start(self, user: User, deal: Deal, categories: list[DocumentCategory], replace: bool) -> AnalysisRun:
        if not settings.llm_configured:
            raise ServiceUnavailableError("AI analysis requires GEMINI_API_KEY to be configured.")
        if await self.runs.active_for_deal(deal.id):
            raise ConflictError("An analysis is already running for this deal.")
        present = await DocumentRepository(self.session).categories_present(deal.id)
        if not present:
            raise ValidationFailedError("Upload and process at least one document before running an analysis.")
        run = await self.runs.add(
            AnalysisRun(
                deal_id=deal.id,
                triggered_by_id=user.id,
                status=AnalysisStatus.QUEUED,
                categories=[c.value for c in categories],
            )
        )
        await AuditService(self.session).log(
            action="analysis.started", entity_type="analysis_run", entity_id=run.id, deal_id=deal.id, user=user,
            summary=f"{user.full_name} started an AI due-diligence analysis",
        )
        await self.session.commit()
        analysis_queue.submit(f"analysis:{run.id}", lambda: run_analysis(run.id, replace))
        return run

    async def list_runs(self, deal: Deal) -> list[AnalysisRun]:
        return list(await self.runs.list_for_deal(deal.id))

    async def get_run(self, deal: Deal, run_id: uuid.UUID) -> AnalysisRun | None:
        run = await self.runs.get(run_id)
        return run if run and run.deal_id == deal.id else None


async def run_analysis(run_id: uuid.UUID, replace_previous: bool) -> None:
    async with SessionLocal() as session:
        run = await session.get(AnalysisRun, run_id)
        if run is None:
            return
        deal = await session.get(Deal, run.deal_id)
        if deal is None:
            return
        run.status = AnalysisStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await session.commit()

        findings_repo = RiskFindingRepository(session)
        try:
            present = await DocumentRepository(session).categories_present(deal.id)
            requested = [DocumentCategory(c) for c in run.categories] or [DocumentCategory(c) for c in present]
            categories = [c for c in requested if c.value in present]
            if replace_previous:
                await findings_repo.delete_open_ai_findings(deal.id, requested)

            created: list[RiskFinding] = []
            # Deterministic gap detection: core workstreams with no documents at all.
            if not run.categories:
                for category in CORE_CATEGORIES:
                    if category.value not in present:
                        created.append(
                            await findings_repo.add(RiskFinding(
                                deal_id=deal.id, analysis_run_id=run.id, category=category,
                                finding_type=FindingType.MISSING_INFORMATION, severity=Severity.HIGH,
                                source=FindingSource.AI,
                                title=f"No {CATEGORY_LABELS[category].lower()} documents in the data room",
                                description=f"The data room contains no processed documents for the "
                                            f"{CATEGORY_LABELS[category].lower()} workstream, so it cannot be assessed.",
                                recommendation="Request the standard document set for this workstream from the seller.",
                            ))
                        )
            await session.commit()

            for position, category in enumerate(categories, start=1):
                chunks = await _gather_context(session, deal.id, category)
                if chunks:
                    result = await llm.generate_structured(
                        CATEGORY_ANALYSIS_PROMPT.format(
                            deal_name=deal.name, acquirer=deal.acquirer_name, target=deal.target_name,
                            deal_type=deal.deal_type.value.replace("_", " "),
                            category_label=CATEGORY_LABELS[category],
                            sources=format_sources(chunks, max_chars_per_source=1400),
                        ),
                        _FindingList,
                        system=ANALYSIS_SYSTEM_PROMPT,
                    )
                    for item in result.findings[:8]:
                        valid_ids = [i for i in dict.fromkeys(item.source_ids) if 1 <= i <= len(chunks)]
                        created.append(
                            await findings_repo.add(RiskFinding(
                                deal_id=deal.id, analysis_run_id=run.id, category=category,
                                finding_type=FindingType(item.finding_type), severity=Severity(item.severity),
                                source=FindingSource.AI, title=item.title[:255], description=item.description,
                                recommendation=item.recommendation, financial_impact=(item.financial_impact or None),
                                citations=[to_citation(i, chunks[i - 1]) for i in valid_ids],
                            ))
                        )
                run.progress = int(position / max(len(categories), 1) * 90)
                await session.commit()

            # Executive summary for the investment committee.
            severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            ordered = sorted(created, key=lambda f: severity_rank[f.severity.value])
            findings_text = "\n".join(
                f"- [{f.severity.value.upper()}] ({f.finding_type.value}, {f.category.value}) {f.title}: {f.description[:300]}"
                for f in ordered[:40]
            ) or "- No material findings were identified."
            summary = await llm.generate_text(
                EXECUTIVE_SUMMARY_PROMPT.format(
                    deal_name=deal.name, acquirer=deal.acquirer_name, target=deal.target_name,
                    deal_type=deal.deal_type.value.replace("_", " "), stage=deal.stage.value.replace("_", " "),
                    coverage=", ".join(f"{k}: {v}" for k, v in present.items()) or "none",
                    missing=", ".join(c.value for c in CORE_CATEGORIES if c.value not in present) or "none",
                    findings=findings_text,
                ),
                system=ANALYSIS_SYSTEM_PROMPT,
                max_tokens=1500,
            )
            run.summary = summary
            deal.executive_summary = summary
            run.findings_count = len(created)
            run.progress = 100
            run.status = AnalysisStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            await AuditService(session).log(
                action="analysis.completed", entity_type="analysis_run", entity_id=run.id, deal_id=deal.id,
                summary=f"AI analysis completed with {len(created)} finding(s)",
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analysis run %s failed", run_id)
            await session.rollback()
            run = await session.get(AnalysisRun, run_id)
            if run is not None:
                run.status = AnalysisStatus.FAILED
                run.error_message = exc.message if isinstance(exc, AppError) else "Analysis failed unexpectedly."
                run.completed_at = datetime.now(UTC)
                await session.commit()


async def review_checklist(session: AsyncSession, user: User, deal: Deal) -> dict[str, int]:
    """Check every open checklist item against the data room and record evidence coverage."""
    if not settings.llm_configured:
        raise ServiceUnavailableError("AI checklist review requires GEMINI_API_KEY to be configured.")
    repo = ChecklistRepository(session)
    present = await DocumentRepository(session).categories_present(deal.id)
    items = [i for i in await repo.list_for_deal(deal.id) if i.status != ChecklistStatus.NOT_APPLICABLE]
    counts = {"reviewed": 0, "found": 0, "partial": 0, "missing": 0}
    now = datetime.now(UTC)

    to_ask = []
    for item in items:
        if item.category.value not in present:
            item.ai_coverage = EvidenceCoverage.MISSING
            item.ai_note = "No documents uploaded for this workstream yet."
            item.ai_citations = []
            item.ai_reviewed_at = now
            counts["reviewed"] += 1
            counts["missing"] += 1
            continue
        result = await hybrid_search(
            session, deal_id=deal.id, query=f"{item.title}. {item.description or ''}", categories=[item.category], top_k=3
        )
        await session.commit()
        to_ask.append((item, result.chunks))

    for start in range(0, len(to_ask), 8):
        batch = to_ask[start : start + 8]
        sources: list[RetrievedChunk] = []
        blocks = []
        for number, (item, chunks) in enumerate(batch, start=1):
            first = len(sources) + 1
            sources.extend(chunks)
            ids = ", ".join(str(i) for i in range(first, first + len(chunks))) or "none"
            blocks.append(f"ITEM {number}: {item.title} — {item.description or ''} (candidate sources: {ids})")
        prompt = CHECKLIST_REVIEW_PROMPT.format(items="\n".join(blocks)) + "\n\nSOURCES:\n" + format_sources(sources, 900)
        review = await llm.generate_structured(prompt, _ChecklistReview, system=ANALYSIS_SYSTEM_PROMPT)
        by_number = {r.item_number: r for r in review.reviews}
        for number, (item, _) in enumerate(batch, start=1):
            verdict = by_number.get(number)
            if verdict is None:
                continue
            item.ai_coverage = EvidenceCoverage(verdict.coverage)
            item.ai_note = verdict.note
            item.ai_citations = [to_citation(i, sources[i - 1], 400) for i in dict.fromkeys(verdict.source_ids)
                                 if 1 <= i <= len(sources)]
            item.ai_reviewed_at = now
            counts["reviewed"] += 1
            counts[verdict.coverage] += 1
        await session.commit()

    await AuditService(session).log(
        action="checklist.ai_review", entity_type="deal", entity_id=deal.id, deal_id=deal.id, user=user,
        summary=f"{user.full_name} ran an AI evidence review: {counts['found']} found, "
                f"{counts['partial']} partial, {counts['missing']} missing",
    )
    await session.commit()
    return counts
