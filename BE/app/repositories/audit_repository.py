import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def recent(
        self, *, deal_ids: list[uuid.UUID] | None = None, limit: int = 50, include_global: bool = False
    ) -> Sequence[AuditLog]:
        stmt = select(AuditLog).options(selectinload(AuditLog.user)).order_by(AuditLog.created_at.desc()).limit(limit)
        if deal_ids is not None:
            condition = AuditLog.deal_id.in_(deal_ids)
            if include_global:
                condition = condition | AuditLog.deal_id.is_(None)
            stmt = stmt.where(condition)
        return await self.list(stmt)
