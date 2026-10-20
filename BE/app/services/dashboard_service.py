from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import embeddings
from app.core.config import settings
from app.models import ChecklistItem, Deal, Document, RiskFinding, User
from app.models.enums import ChecklistStatus, DealStage, DocumentStatus, FindingStatus
from app.repositories.deal_repository import DealRepository
from app.schemas.dashboard import CountBucket, DashboardSummary, SystemStatus
from app.services.audit_service import AuditService

INACTIVE_STAGES = (DealStage.CLOSED, DealStage.TERMINATED)
OPEN_STATUSES = (FindingStatus.OPEN, FindingStatus.UNDER_REVIEW)


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _buckets(self, column, *where) -> list[CountBucket]:
        rows = await self.session.execute(select(column, func.count()).where(*where).group_by(column))
        return [CountBucket(key=str(key), count=count) for key, count in rows]

    async def summary(self, user: User) -> DashboardSummary:
        deal_ids = await DealRepository(self.session).accessible_ids(user)
        if not deal_ids:
            return DashboardSummary(
                active_deals=0, total_deals=0, documents_total=0, documents_ready=0, documents_processing=0,
                open_risks=0, critical_risks=0, checklist_completion=0, deals_by_stage=[], risks_by_severity=[],
                documents_by_category=[], recent_activity=[],
            )

        deals_by_stage = await self._buckets(Deal.stage, Deal.id.in_(deal_ids))
        documents_by_status = {b.key: b.count for b in await self._buckets(Document.status, Document.deal_id.in_(deal_ids))}
        risks_by_severity = await self._buckets(
            RiskFinding.severity, RiskFinding.deal_id.in_(deal_ids), RiskFinding.status.in_(OPEN_STATUSES)
        )
        documents_by_category = await self._buckets(Document.category, Document.deal_id.in_(deal_ids))

        checklist = (
            await self.session.execute(
                select(
                    func.count(),
                    func.count().filter(ChecklistItem.status.in_((ChecklistStatus.COMPLETED, ChecklistStatus.NOT_APPLICABLE))),
                ).where(ChecklistItem.deal_id.in_(deal_ids))
            )
        ).one()

        severity_counts = {b.key: b.count for b in risks_by_severity}
        return DashboardSummary(
            active_deals=sum(b.count for b in deals_by_stage if b.key not in {s.value for s in INACTIVE_STAGES}),
            total_deals=len(deal_ids),
            documents_total=sum(documents_by_status.values()),
            documents_ready=documents_by_status.get(DocumentStatus.READY.value, 0),
            documents_processing=documents_by_status.get(DocumentStatus.PROCESSING.value, 0)
            + documents_by_status.get(DocumentStatus.QUEUED.value, 0),
            open_risks=sum(severity_counts.values()),
            critical_risks=severity_counts.get("critical", 0),
            checklist_completion=round(100 * checklist[1] / checklist[0]) if checklist[0] else 0,
            deals_by_stage=deals_by_stage,
            risks_by_severity=risks_by_severity,
            documents_by_category=sorted(documents_by_category, key=lambda b: b.count, reverse=True),
            recent_activity=await AuditService(self.session).recent(deal_ids=deal_ids, limit=12),
        )

    async def system_status(self) -> SystemStatus:
        try:
            await self.session.execute(text("SELECT 1"))
            database = True
        except Exception:  # noqa: BLE001
            database = False
        return SystemStatus(
            database=database,
            llm_configured=settings.llm_configured,
            llm_model=settings.gemini_chat_model,
            embedding_model=settings.embedding_model + ("" if embeddings.is_loaded() else " (loading on first use)"),
            reranker_model=settings.reranker_model if settings.reranker_enabled else None,
            ocr_engine=settings.ocr_engine if settings.ocr_enabled else None,
        )
