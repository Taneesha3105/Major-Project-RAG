import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models import ChecklistItem, Deal, DealMember, User
from app.models.enums import DealMemberRole, DealStage
from app.repositories.deal_repository import DealRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.deal import DealCreate, DealMemberCreate, DealRead, DealStats, DealUpdate
from app.services.audit_service import AuditService
from app.services.checklist_templates import CORE_CATEGORIES, DEFAULT_CHECKLIST
from app.services.storage_service import storage


def readiness_score(stats: dict[str, int], categories_present: set[str] | None = None) -> int:
    """0-100 composite: checklist completion (50%), core workstream coverage (30%), risk posture (20%)."""
    total = stats.get("checklist_total", 0)
    checklist_part = (stats.get("checklist_completed", 0) / total) if total else 0.0
    if categories_present is None:
        coverage_part = min(stats.get("ready_document_count", 0) / len(CORE_CATEGORIES), 1.0)
    else:
        coverage_part = sum(1 for c in CORE_CATEGORIES if c.value in categories_present) / len(CORE_CATEGORIES)
    open_risks = stats.get("open_risk_count", 0)
    critical = stats.get("critical_risk_count", 0)
    risk_part = max(0.0, 1.0 - 0.25 * critical - 0.04 * max(open_risks - critical, 0))
    if not stats.get("ready_document_count"):
        risk_part = 0.0
    return round(100 * (0.5 * checklist_part + 0.3 * coverage_part + 0.2 * risk_part))


class DealService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DealRepository(session)
        self.audit = AuditService(session)

    async def _to_read(self, deals: list[Deal]) -> list[DealRead]:
        stats_map = await self.repo.stats_for([deal.id for deal in deals])
        documents = DocumentRepository(self.session)
        result = []
        for deal in deals:
            stats = stats_map.get(deal.id, {})
            present = set((await documents.categories_present(deal.id)).keys()) if len(deals) == 1 else None
            result.append(
                DealRead.model_validate(deal).model_copy(
                    update={"stats": DealStats(**stats, readiness_score=readiness_score(stats, present))}
                )
            )
        return result

    async def list_deals(self, user: User, search: str | None, stage: DealStage | None) -> list[DealRead]:
        return await self._to_read(list(await self.repo.list_for_user(user, search=search, stage=stage)))

    async def read(self, deal: Deal) -> DealRead:
        return (await self._to_read([deal]))[0]

    async def create(self, user: User, payload: DealCreate) -> DealRead:
        data = payload.model_dump(exclude={"seed_checklist"})
        deal = await self.repo.add(Deal(**data, created_by_id=user.id))
        self.session.add(DealMember(deal_id=deal.id, user_id=user.id, member_role=DealMemberRole.LEAD))
        if payload.seed_checklist:
            self.session.add_all(
                ChecklistItem(deal_id=deal.id, category=category, title=title, description=description,
                              priority=priority, sort_order=index)
                for index, (category, title, description, priority) in enumerate(DEFAULT_CHECKLIST)
            )
        await self.audit.log(action="deal.created", entity_type="deal", entity_id=deal.id, deal_id=deal.id,
                             user=user, summary=f"{user.full_name} created deal '{deal.name}'")
        await self.session.commit()
        await self.session.refresh(deal)
        return await self.read(deal)

    async def update(self, user: User, deal: Deal, payload: DealUpdate) -> DealRead:
        changes = payload.model_dump(exclude_unset=True)
        if "currency" in changes and changes["currency"]:
            changes["currency"] = changes["currency"].upper()
        for required in ("name", "acquirer_name", "target_name", "deal_type", "stage", "currency"):
            if required in changes and changes[required] is None:
                raise ValidationFailedError(f"'{required}' cannot be empty.")
        previous_stage = deal.stage
        self.repo.apply_updates(deal, changes)
        summary = f"{user.full_name} updated deal details"
        if "stage" in changes and changes["stage"] != previous_stage:
            summary = f"{user.full_name} moved the deal from {previous_stage.value} to {deal.stage.value}"
        await self.audit.log(action="deal.updated", entity_type="deal", entity_id=deal.id, deal_id=deal.id,
                             user=user, summary=summary, details={k: str(v) for k, v in changes.items()})
        await self.session.commit()
        await self.session.refresh(deal)
        return await self.read(deal)

    async def delete(self, user: User, deal: Deal) -> None:
        name = deal.name
        deal_id = deal.id
        await self.repo.delete(deal)
        await self.audit.log(action="deal.deleted", entity_type="deal", entity_id=deal_id, user=user,
                             summary=f"{user.full_name} deleted deal '{name}'")
        await self.session.commit()
        await storage.delete_prefix(str(deal_id))

    # --- members ---
    async def list_members(self, deal: Deal) -> list[DealMember]:
        return list(await self.repo.list_members(deal.id))

    async def add_member(self, user: User, deal: Deal, payload: DealMemberCreate) -> DealMember:
        member_user = await UserRepository(self.session).get(payload.user_id)
        if member_user is None or not member_user.is_active:
            raise NotFoundError("User not found or inactive.")
        if await self.repo.get_membership(deal.id, member_user.id):
            raise ConflictError(f"{member_user.full_name} is already on this deal team.")
        member = await self.repo.add(DealMember(deal_id=deal.id, user_id=member_user.id, member_role=payload.member_role))
        await self.audit.log(action="deal.member_added", entity_type="deal_member", entity_id=member.id,
                             deal_id=deal.id, user=user,
                             summary=f"{user.full_name} added {member_user.full_name} as {payload.member_role.value}")
        await self.session.commit()
        members = await self.repo.list_members(deal.id)
        return next(m for m in members if m.id == member.id)

    async def remove_member(self, user: User, deal: Deal, member_id: uuid.UUID) -> None:
        members = await self.repo.list_members(deal.id)
        member = next((m for m in members if m.id == member_id), None)
        if member is None:
            raise NotFoundError("Team member not found.")
        leads = [m for m in members if m.member_role == DealMemberRole.LEAD]
        if member.member_role == DealMemberRole.LEAD and len(leads) == 1:
            raise ValidationFailedError("A deal must keep at least one lead.")
        await self.repo.delete(member)
        await self.audit.log(action="deal.member_removed", entity_type="deal_member", entity_id=member_id,
                             deal_id=deal.id, user=user,
                             summary=f"{user.full_name} removed {member.user.full_name} from the deal team")
        await self.session.commit()
