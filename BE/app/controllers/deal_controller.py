import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.controllers.deps import CurrentUser, DealCtx, SessionDep, require
from app.core.permissions import Permission
from app.models import DealMember, User
from app.models.enums import DealStage
from app.schemas.dashboard import AuditLogRead
from app.schemas.deal import DealCreate, DealMemberCreate, DealMemberRead, DealRead, DealUpdate
from app.services.audit_service import AuditService
from app.services.deal_service import DealService

router = APIRouter(prefix="/deals", tags=["Deals"])


class DealDetail(DealRead):
    my_permissions: list[str]
    my_member_role: str | None


@router.get("", response_model=list[DealRead])
async def list_deals(
    session: SessionDep,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=100)] = None,
    stage: DealStage | None = None,
) -> list[DealRead]:
    return await DealService(session).list_deals(user, search, stage)


@router.post("", response_model=DealRead, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealCreate, session: SessionDep, user: Annotated[User, Depends(require(Permission.DEAL_CREATE))]
) -> DealRead:
    return await DealService(session).create(user, payload)


@router.get("/{deal_id}", response_model=DealDetail)
async def get_deal(ctx: DealCtx, session: SessionDep) -> DealDetail:
    deal = await DealService(session).read(ctx.deal)
    return DealDetail(
        **deal.model_dump(),
        my_permissions=sorted(p.value for p in ctx.permissions),
        my_member_role=ctx.membership.member_role.value if ctx.membership else None,
    )


@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal(payload: DealUpdate, ctx: DealCtx, session: SessionDep) -> DealRead:
    ctx.require(Permission.DEAL_EDIT)
    return await DealService(session).update(ctx.user, ctx.deal, payload)


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(ctx: DealCtx, session: SessionDep) -> Response:
    ctx.require(Permission.DEAL_DELETE)
    await DealService(session).delete(ctx.user, ctx.deal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{deal_id}/members", response_model=list[DealMemberRead])
async def list_members(ctx: DealCtx, session: SessionDep) -> list[DealMember]:
    return await DealService(session).list_members(ctx.deal)


@router.post("/{deal_id}/members", response_model=DealMemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(payload: DealMemberCreate, ctx: DealCtx, session: SessionDep) -> DealMember:
    ctx.require(Permission.MEMBERS_MANAGE)
    return await DealService(session).add_member(ctx.user, ctx.deal, payload)


@router.delete("/{deal_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> Response:
    ctx.require(Permission.MEMBERS_MANAGE)
    await DealService(session).remove_member(ctx.user, ctx.deal, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{deal_id}/activity", response_model=list[AuditLogRead])
async def deal_activity(
    ctx: DealCtx, session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[AuditLogRead]:
    ctx.require(Permission.AUDIT_VIEW)
    return await AuditService(session).recent(deal_ids=[ctx.deal.id], limit=limit)
