import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models import AnalysisRun, ChecklistItem, RiskFinding
from app.models.enums import (
    AnalysisStatus,
    DocumentCategory,
    FindingSource,
    FindingStatus,
    FindingType,
    Severity,
)
from app.repositories.base import BaseRepository


class ChecklistRepository(BaseRepository[ChecklistItem]):
    model = ChecklistItem

    async def list_for_deal(self, deal_id: uuid.UUID) -> Sequence[ChecklistItem]:
        stmt = (
            select(ChecklistItem)
            .where(ChecklistItem.deal_id == deal_id)
            .options(selectinload(ChecklistItem.assignee))
            .order_by(ChecklistItem.category, ChecklistItem.sort_order, ChecklistItem.created_at)
        )
        return await self.list(stmt)

    async def get_in_deal(self, deal_id: uuid.UUID, item_id: uuid.UUID) -> ChecklistItem | None:
        return await self.session.scalar(
            select(ChecklistItem)
            .where(ChecklistItem.id == item_id, ChecklistItem.deal_id == deal_id)
            .options(selectinload(ChecklistItem.assignee))
            .execution_options(populate_existing=True)
        )


class RiskFindingRepository(BaseRepository[RiskFinding]):
    model = RiskFinding

    async def list_for_deal(
        self,
        deal_id: uuid.UUID,
        *,
        severity: Severity | None = None,
        status: FindingStatus | None = None,
        finding_type: FindingType | None = None,
        category: DocumentCategory | None = None,
    ) -> Sequence[RiskFinding]:
        stmt = (
            select(RiskFinding)
            .where(RiskFinding.deal_id == deal_id)
            .options(selectinload(RiskFinding.owner))
            .order_by(RiskFinding.created_at.desc())
        )
        if severity:
            stmt = stmt.where(RiskFinding.severity == severity)
        if status:
            stmt = stmt.where(RiskFinding.status == status)
        if finding_type:
            stmt = stmt.where(RiskFinding.finding_type == finding_type)
        if category:
            stmt = stmt.where(RiskFinding.category == category)
        return await self.list(stmt)

    async def get_in_deal(self, deal_id: uuid.UUID, finding_id: uuid.UUID) -> RiskFinding | None:
        return await self.session.scalar(
            select(RiskFinding)
            .where(RiskFinding.id == finding_id, RiskFinding.deal_id == deal_id)
            .options(selectinload(RiskFinding.owner))
            .execution_options(populate_existing=True)
        )

    async def delete_open_ai_findings(self, deal_id: uuid.UUID, categories: list[DocumentCategory]) -> None:
        """Remove untouched AI findings before a re-run; anything a human triaged is kept."""
        stmt = delete(RiskFinding).where(
            RiskFinding.deal_id == deal_id,
            RiskFinding.source == FindingSource.AI,
            RiskFinding.status == FindingStatus.OPEN,
        )
        if categories:
            stmt = stmt.where(RiskFinding.category.in_(categories))
        await self.session.execute(stmt)


class AnalysisRunRepository(BaseRepository[AnalysisRun]):
    model = AnalysisRun

    async def list_for_deal(self, deal_id: uuid.UUID, limit: int = 20) -> Sequence[AnalysisRun]:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.deal_id == deal_id)
            .order_by(AnalysisRun.created_at.desc())
            .limit(limit)
        )
        return await self.list(stmt)

    async def active_for_deal(self, deal_id: uuid.UUID) -> AnalysisRun | None:
        return await self.session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.deal_id == deal_id,
                AnalysisRun.status.in_((AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)),
            )
        )
