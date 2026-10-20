import uuid
from collections.abc import Sequence

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import selectinload

from app.models import ChecklistItem, Deal, DealMember, Document, RiskFinding, User
from app.models.enums import ChecklistStatus, DealStage, DocumentStatus, FindingStatus, Severity
from app.repositories.base import BaseRepository

OPEN_FINDING_STATUSES = (FindingStatus.OPEN, FindingStatus.UNDER_REVIEW)
DONE_CHECKLIST_STATUSES = (ChecklistStatus.COMPLETED, ChecklistStatus.NOT_APPLICABLE)


class DealRepository(BaseRepository[Deal]):
    model = Deal

    def _accessible(self, user: User):
        stmt = select(Deal)
        if not user.is_admin:
            stmt = stmt.join(DealMember, and_(DealMember.deal_id == Deal.id, DealMember.user_id == user.id))
        return stmt

    async def list_for_user(
        self, user: User, *, search: str | None = None, stage: DealStage | None = None
    ) -> Sequence[Deal]:
        stmt = self._accessible(user).order_by(Deal.updated_at.desc())
        if stage:
            stmt = stmt.where(Deal.stage == stage)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Deal.name).like(pattern),
                    func.lower(Deal.target_name).like(pattern),
                    func.lower(Deal.acquirer_name).like(pattern),
                    func.lower(func.coalesce(Deal.code_name, "")).like(pattern),
                )
            )
        return await self.list(stmt)

    async def accessible_ids(self, user: User) -> list[uuid.UUID]:
        stmt = self._accessible(user).with_only_columns(Deal.id)
        return list((await self.session.scalars(stmt)).all())

    async def get_membership(self, deal_id: uuid.UUID, user_id: uuid.UUID) -> DealMember | None:
        return await self.session.scalar(
            select(DealMember).where(DealMember.deal_id == deal_id, DealMember.user_id == user_id)
        )

    async def list_members(self, deal_id: uuid.UUID) -> Sequence[DealMember]:
        stmt = (
            select(DealMember)
            .where(DealMember.deal_id == deal_id)
            .options(selectinload(DealMember.user))
            .order_by(DealMember.added_at)
        )
        return await self.list(stmt)

    async def stats_for(self, deal_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
        """Aggregate per-deal counters in a handful of grouped queries (no N+1)."""
        stats: dict[uuid.UUID, dict[str, int]] = {deal_id: {} for deal_id in deal_ids}
        if not deal_ids:
            return stats

        doc_rows = await self.session.execute(
            select(
                Document.deal_id,
                func.count(),
                func.count().filter(Document.status == DocumentStatus.READY),
            )
            .where(Document.deal_id.in_(deal_ids))
            .group_by(Document.deal_id)
        )
        for deal_id, total, ready in doc_rows:
            stats[deal_id].update(document_count=total, ready_document_count=ready)

        risk_rows = await self.session.execute(
            select(
                RiskFinding.deal_id,
                func.count().filter(RiskFinding.status.in_(OPEN_FINDING_STATUSES)),
                func.count().filter(
                    and_(RiskFinding.status.in_(OPEN_FINDING_STATUSES), RiskFinding.severity == Severity.CRITICAL)
                ),
            )
            .where(RiskFinding.deal_id.in_(deal_ids))
            .group_by(RiskFinding.deal_id)
        )
        for deal_id, open_count, critical in risk_rows:
            stats[deal_id].update(open_risk_count=open_count, critical_risk_count=critical)

        checklist_rows = await self.session.execute(
            select(
                ChecklistItem.deal_id,
                func.count(),
                func.sum(case((ChecklistItem.status.in_(DONE_CHECKLIST_STATUSES), 1), else_=0)),
            )
            .where(ChecklistItem.deal_id.in_(deal_ids))
            .group_by(ChecklistItem.deal_id)
        )
        for deal_id, total, done in checklist_rows:
            stats[deal_id].update(checklist_total=total, checklist_completed=int(done or 0))

        member_rows = await self.session.execute(
            select(DealMember.deal_id, func.count()).where(DealMember.deal_id.in_(deal_ids)).group_by(DealMember.deal_id)
        )
        for deal_id, count in member_rows:
            stats[deal_id]["member_count"] = count

        return stats
