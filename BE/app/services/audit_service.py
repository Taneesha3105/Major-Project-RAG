import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.repositories.audit_repository import AuditRepository
from app.schemas.dashboard import AuditLogRead


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AuditRepository(session)

    async def log(
        self,
        *,
        action: str,
        entity_type: str,
        summary: str,
        user: User | None = None,
        user_id: uuid.UUID | None = None,
        deal_id: uuid.UUID | None = None,
        entity_id: Any = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None:
        await self.repo.add(
            AuditLog(
                user_id=user.id if user else user_id,
                deal_id=deal_id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                summary=summary[:500],
                details=details or {},
                ip_address=ip_address,
            )
        )

    async def recent(
        self, *, deal_ids: list[uuid.UUID] | None, limit: int = 50, include_global: bool = False
    ) -> list[AuditLogRead]:
        logs = await self.repo.recent(deal_ids=deal_ids, limit=limit, include_global=include_global)
        return [
            AuditLogRead.model_validate(log).model_copy(update={"user_name": log.user.full_name if log.user else None})
            for log in logs
        ]
