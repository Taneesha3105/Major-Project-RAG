"""CRUD workflows for the due-diligence checklist and the risk register."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.models import ChecklistItem, Deal, RiskFinding, User
from app.models.enums import DocumentCategory, FindingSource, FindingStatus, FindingType, Severity
from app.repositories.deal_repository import DealRepository
from app.repositories.diligence_repository import ChecklistRepository, RiskFindingRepository
from app.schemas.diligence import ChecklistItemCreate, ChecklistItemUpdate, RiskFindingCreate, RiskFindingUpdate
from app.services.audit_service import AuditService


async def _ensure_member(session: AsyncSession, deal: Deal, user_id: uuid.UUID | None) -> None:
    if user_id is not None and await DealRepository(session).get_membership(deal.id, user_id) is None:
        raise ValidationFailedError("The assignee must be a member of the deal team.")


class ChecklistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChecklistRepository(session)
        self.audit = AuditService(session)

    async def list(self, deal: Deal) -> list[ChecklistItem]:
        return list(await self.repo.list_for_deal(deal.id))

    async def _get(self, deal: Deal, item_id: uuid.UUID) -> ChecklistItem:
        item = await self.repo.get_in_deal(deal.id, item_id)
        if item is None:
            raise NotFoundError("Checklist item not found.")
        return item

    async def create(self, user: User, deal: Deal, payload: ChecklistItemCreate) -> ChecklistItem:
        await _ensure_member(self.session, deal, payload.assignee_id)
        item = await self.repo.add(ChecklistItem(deal_id=deal.id, sort_order=999, **payload.model_dump()))
        await self.audit.log(action="checklist.created", entity_type="checklist_item", entity_id=item.id,
                             deal_id=deal.id, user=user, summary=f"{user.full_name} added request '{item.title}'")
        await self.session.commit()
        return await self._get(deal, item.id)

    async def update(self, user: User, deal: Deal, item_id: uuid.UUID, payload: ChecklistItemUpdate) -> ChecklistItem:
        item = await self._get(deal, item_id)
        changes = payload.model_dump(exclude_unset=True)
        if "assignee_id" in changes:
            await _ensure_member(self.session, deal, changes["assignee_id"])
        for required in ("title", "status", "priority"):
            if required in changes and changes[required] is None:
                raise ValidationFailedError(f"'{required}' cannot be empty.")
        previous_status = item.status
        self.repo.apply_updates(item, changes)
        if "status" in changes and changes["status"] != previous_status:
            await self.audit.log(
                action="checklist.status_changed", entity_type="checklist_item", entity_id=item.id, deal_id=deal.id,
                user=user, summary=f"{user.full_name} marked '{item.title}' as {item.status.value.replace('_', ' ')}",
            )
        await self.session.commit()
        return await self._get(deal, item_id)

    async def delete(self, user: User, deal: Deal, item_id: uuid.UUID) -> None:
        item = await self._get(deal, item_id)
        await self.repo.delete(item)
        await self.audit.log(action="checklist.deleted", entity_type="checklist_item", entity_id=item_id,
                             deal_id=deal.id, user=user, summary=f"{user.full_name} removed request '{item.title}'")
        await self.session.commit()


class RiskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = RiskFindingRepository(session)
        self.audit = AuditService(session)

    async def list(
        self,
        deal: Deal,
        severity: Severity | None,
        status: FindingStatus | None,
        finding_type: FindingType | None,
        category: DocumentCategory | None,
    ) -> list[RiskFinding]:
        return list(
            await self.repo.list_for_deal(deal.id, severity=severity, status=status, finding_type=finding_type, category=category)
        )

    async def _get(self, deal: Deal, finding_id: uuid.UUID) -> RiskFinding:
        finding = await self.repo.get_in_deal(deal.id, finding_id)
        if finding is None:
            raise NotFoundError("Finding not found.")
        return finding

    async def create(self, user: User, deal: Deal, payload: RiskFindingCreate) -> RiskFinding:
        await _ensure_member(self.session, deal, payload.owner_id)
        finding = await self.repo.add(
            RiskFinding(deal_id=deal.id, source=FindingSource.MANUAL, created_by_id=user.id, **payload.model_dump())
        )
        await self.audit.log(
            action="finding.created", entity_type="risk_finding", entity_id=finding.id, deal_id=deal.id, user=user,
            summary=f"{user.full_name} logged a {finding.severity.value} {finding.finding_type.value.replace('_', ' ')}: {finding.title}",
        )
        await self.session.commit()
        return await self._get(deal, finding.id)

    async def update(self, user: User, deal: Deal, finding_id: uuid.UUID, payload: RiskFindingUpdate) -> RiskFinding:
        finding = await self._get(deal, finding_id)
        changes = payload.model_dump(exclude_unset=True)
        if "owner_id" in changes:
            await _ensure_member(self.session, deal, changes["owner_id"])
        for required in ("title", "description", "category", "finding_type", "severity", "status"):
            if required in changes and changes[required] is None:
                raise ValidationFailedError(f"'{required}' cannot be empty.")
        previous_status = finding.status
        self.repo.apply_updates(finding, changes)
        summary = f"{user.full_name} updated finding '{finding.title}'"
        if "status" in changes and changes["status"] != previous_status:
            summary = f"{user.full_name} set '{finding.title}' to {finding.status.value.replace('_', ' ')}"
        await self.audit.log(action="finding.updated", entity_type="risk_finding", entity_id=finding.id,
                             deal_id=deal.id, user=user, summary=summary)
        await self.session.commit()
        return await self._get(deal, finding_id)

    async def delete(self, user: User, deal: Deal, finding_id: uuid.UUID) -> None:
        finding = await self._get(deal, finding_id)
        await self.repo.delete(finding)
        await self.audit.log(action="finding.deleted", entity_type="risk_finding", entity_id=finding_id,
                             deal_id=deal.id, user=user, summary=f"{user.full_name} deleted finding '{finding.title}'")
        await self.session.commit()
